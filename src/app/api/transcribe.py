import os
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
    # GCSの保存パスを決定
    today = datetime.utcnow().strftime("%Y/%m/%d")
    object_name = f"uploads/{episode_id}.mp3"
    gcs_uri = f"gs://{BUCKET_NAME}/{object_name}"

    # 3. GCSにアップロード
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(object_name)

    # resp.raw はファイルライクオブジェクトなのでそのまま渡せる
    blob.upload_from_file(resp.raw, content_type="audio/mpeg")

    return gcs_uri


# Google STT が処理できる LINEAR16/16kHz/WAV に変換する
def to_linear16_wav(src_path: str, dst_path: str):
    try:
        (
            ffmpeg.input(src_path, ss=0, t=80)
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
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        language_code="ja-JP",  # 言語を日本語に設定
        enable_automatic_punctuation=True,
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
        data=str(job_json),
        content_type="application/json",
    )

    return {"transcriptionId": transcription_id, "status": "RUNNING"}
