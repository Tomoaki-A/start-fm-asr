from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os, tempfile, shutil, requests, ffmpeg
from google.cloud import speech
from typing import Optional, List

router = APIRouter()

# ====== I/O Models ======
# リクエストボディの型
class TranscribeReq(BaseModel):
    audio_url: str

# デバッグ用
class RequestEcho(BaseModel):
    audioUrl: str

# 全文レベルの結果
class ResultSummary(BaseModel):
    text: str
    confidence: Optional[float] = None

# セグメントレベルの結果
class Segment(BaseModel):
    startSec: Optional[float] = None
    endSec: Optional[float] = None
    speaker: Optional[str] = None
    text: str
    confidence: Optional[float] = None

# メタ情報
class MetaInfo(BaseModel):
    jobId: Optional[str] = None
    engine: str

# レスポンスボディの型
class TranscribeResp(BaseModel):
    version: str = "1.0"
    request: RequestEcho
    result: ResultSummary
    segments: List[Segment]
    words: Optional[List[dict]] = None
    meta: MetaInfo


# Google STT が処理できる LINEAR16/16kHz/WAV に変換する
def to_linear16_wav(src_path: str, dst_path: str):
  try:
    (
        ffmpeg
        .input(src_path, ss=0, t=80)
        .output(dst_path, ar=16000, ac=1, sample_fmt='s16', f='wav')
        .overwrite_output()
        .run(quiet=True)
    )
  except ffmpeg.Error:
    raise HTTPException(status_code=400, detail="ffmpeg failed (trim/convert)")

@router.post("/transcribe")
def transcribe(req: TranscribeReq):
    tmp = tempfile.mkdtemp(prefix="startfm_")
    src = os.path.join(tmp, "src.audio")  # 元ファイル（一時）
    wav = os.path.join(tmp, "src.wav")    # 変換後ファイル（一時）
    try:
     # --- 1) ダウンロード ---
     try:
       with requests.get(req.audio_url, stream=True, timeout=30) as r:
         r.raise_for_status()
         with open(src, "wb") as f:
           for chunk in r.iter_content(chunk_size=8192):
             if chunk:
               f.write(chunk)
     except requests.RequestException as e:
       raise HTTPException(status_code=400, detail=f"download failed: {e}")

     # --- 2) 変換 ---
     to_linear16_wav(src, wav)

     # --- 3) Google STT（同期）---
     try:
       client = speech.SpeechClient()
     except Exception as e:
       # 環境変数/認証鍵の不備など
       raise HTTPException(status_code=500, detail=f"SpeechClient init failed: {e}")
     with open(wav, "rb") as f:
       content = f.read()
       audio = speech.RecognitionAudio(content=content)
       config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="ja-JP",
        enable_automatic_punctuation=True,
     )

     try:
       stt_resp = client.recognize(config=config, audio=audio)
     except Exception as e:
       # STT バックエンド側のエラーは 502 相当で扱う
       raise HTTPException(status_code=502, detail=f"STT recognize failed: {e}")

     # --- 4) レスポンス整形 ---
     alts = [r.alternatives[0] for r in stt_resp.results if r.alternatives]
     full_text = " ".join(a.transcript for a in alts).strip()
     confidences = [a.confidence for a in alts if getattr(a, "confidence", None) not in (None, 0.0)]
     avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else None

     # --- 5) レスポンス構築（新スキーマ）---
     request_echo = RequestEcho(
       audioUrl=req.audio_url,
     )
     result = ResultSummary(
       text=full_text,
       confidence=avg_conf,
     )
     segments: List[Segment] = []
     meta = MetaInfo(
       jobId=None,
       engine="google-stt:v1",
     )

     return TranscribeResp(
       request=request_echo,
       result=result,
       segments=segments,
       meta=meta,
     )
    finally:
      shutil.rmtree(tmp, ignore_errors=True)
