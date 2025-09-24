from fastapi import APIRouter
from pydantic import BaseModel
import os, tempfile, shutil, requests, ffmpeg
from google.cloud import speech

router = APIRouter()

class TranscribeReq(BaseModel):
    audio_url: str

# Google STT が処理できる LINEAR16/16kHz/WAV に変換する
def to_linear16_wav(src_path: str, dst_path: str):
    (
        ffmpeg
        .input(src_path, ss=20, t=40)
        .output(dst_path, ar=16000, ac=1, sample_fmt='s16', f='wav')
        .overwrite_output()
        .run(quiet=True)
    )

@router.post("/transcribe")
def transcribe(req: TranscribeReq):
    tmp = tempfile.mkdtemp(prefix="startfm_")
    try:
        src = os.path.join(tmp, "src.audio")
        r = requests.get(req.audio_url, timeout=60); r.raise_for_status()
        open(src, "wb").write(r.content)

        wav = os.path.join(tmp, "src.wav")
        to_linear16_wav(src, wav)

        client = speech.SpeechClient()
        content = open(wav, "rb").read()
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="ja-JP",
            enable_automatic_punctuation=True,
        )
        resp = client.recognize(config=config, audio=audio)
        text = " ".join(alt.transcript for r in resp.results for alt in r.alternatives).strip()
        return {"text": text}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
