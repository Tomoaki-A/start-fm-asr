import json
import os
import tempfile
import uuid
from datetime import datetime

import ffmpeg
import requests
from fastapi import APIRouter, HTTPException
from google.cloud import speech, storage
from pydantic import BaseModel

router = APIRouter()


# ====== I/O Models ======
class TranscriptionRequest(BaseModel):
    episodeId: str
    audioUrl: str


BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "start-fm-audio")


# GCSに保存する
def save_audio_to_gcs(audio_url: str, episode_id: str) -> str:
    # 1. 音声をダウンロード
    resp = requests.get(audio_url, stream=True)
    # ダウンロード失敗時は例外を投げる
    resp.raise_for_status()

    tmp_in = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp_out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)

    try:
        tmp_in.write(resp.content)
        tmp_in.flush()

        to_linear16_wav(tmp_in.name, tmp_out.name)

        # GCSの保存パスを決定
        object_name = f"uploads/{episode_id}.wav"
        gcs_uri = f"gs://{BUCKET_NAME}/{object_name}"

        # 3. GCSにアップロード
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"uploads/{episode_id}.wav")

        blob.upload_from_filename(tmp_out.name, content_type="audio/wav")

    finally:
        tmp_in.close()
        tmp_out.close()

    return gcs_uri


# Google STT が処理できる LINEAR16/16kHz/WAV に変換する
def to_linear16_wav(src_path: str, dst_path: str):
    try:
        (
            ffmpeg.input(src_path)
            .output(dst_path, ar=16000, ac=1, sample_fmt="s16", f="wav")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error:
        raise HTTPException(status_code=400, detail="ffmpeg failed (trim/convert)")


@router.post("/transcribe")
def transcribe(req: TranscriptionRequest):
    gcs_uri = save_audio_to_gcs(req.audioUrl, req.episodeId)
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(uri=gcs_uri)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ja-JP",  # 言語を日本語に設定
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,  # 単語ごとの開始・終了時刻
        diarization_config=speech.SpeakerDiarizationConfig(
            enable_speaker_diarization=True,
            min_speaker_count=2,
            max_speaker_count=2,
        ),
    )
    operation = client.long_running_recognize(config=config, audio=audio)
    transcription_id = str(uuid.uuid4())
    job_json = {
        "version": "1.0",
        "episodeId": req.episodeId,
        "audioUrl": req.audioUrl,
        "gcsUri": gcs_uri,
        "operationName": operation.operation.name,
        "status": "RUNNING",
        "engine": "google-stt:v1",
        "startedAt": datetime.utcnow().isoformat() + "Z",
    }

    from google.cloud import storage

    bucket_name = "start-fm-audio"
    client_storage = storage.Client()
    bucket = client_storage.bucket(bucket_name)
    blob = bucket.blob(f"transcriptions/{transcription_id}.json")
    blob.upload_from_string(
        data=json.dumps(job_json),
        content_type="application/json",
    )

    return {"transcriptionId": transcription_id, "status": "RUNNING"}


@router.get("/transcribe/{transcribe_id}")
def get_transcription(transcribe_id: str):
    # 1. GCS から JSON を読み込み
    storage_client = storage.Client()
    bucket = storage_client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"transcriptions/{transcribe_id}.json")

    if not blob.exists():
        return {"error": "transcription not found"}

    job_json = json.loads(blob.download_as_text())

    if job_json.get("status") == "SUCCEEDED":
        client = speech.SpeechClient()
        operation_name = job_json["operationName"]
        operation = client._transport.operations_client.get_operation(operation_name)

        from google.protobuf.json_format import MessageToDict

        op_dict = MessageToDict(operation)
        print("operation dict:", op_dict)

        if operation.done:
            response = speech.LongRunningRecognizeResponse.deserialize(
                operation.response.value
            )
            final_result = response.results[-1]
            words = final_result.alternatives[0].words
            segments = []
            for w in words:
                tag = getattr(w, "speaker_tag", 0)
                if tag >= 1:
                    segments.append(
                        {
                            "word": w.word,
                            "startTime": w.start_time.total_seconds(),
                            "endTime": w.end_time.total_seconds(),
                            "speaker": w.speaker_tag,
                        }
                    )

            dialogue = {}
            for seg in segments:
                spk = seg["speaker"]
                if spk not in dialogue:
                    dialogue[spk] = []
                dialogue[spk].append(
                    f"[{seg['startTime']}s-{seg['endTime']}s] {seg['word']}"
                )
            text = "\n".join([r.alternatives[0].transcript for r in response.results])
            avg_conf = (
                sum([r.alternatives[0].confidence for r in response.results])
                / len(response.results)
                if response.results
                else None
            )

            job_json.update(
                {
                    "status": "SUCCEEDED",
                    "finishedAt": datetime.utcnow().isoformat() + "Z",
                    "result": {
                        "text": text,
                        "segments": segments,
                        "dialogue": dialogue,
                        "avgConfidence": avg_conf,
                    },
                }
            )
            blob.upload_from_string(
                data=json.dumps(job_json),
                content_type="application/json",
            )

    return job_json
