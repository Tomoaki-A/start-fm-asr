import os
import re
import tempfile
from pathlib import Path
from typing import List

import ffmpeg
import pytesseract
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.app.api.ocr.preprocess import preprocess

router = APIRouter()


class Request(BaseModel):
    file_url: str
    episode_id: str


OUTPUT_ROOT = Path(os.environ.get("OUTPUT_DIR", "./out")).resolve()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
fps = 4


# 動画URLを受け取り、フレームを抽出して画像として保存するエンドポイント
@router.post("/ocr/capture")
async def ocr_endpoint(request: Request):
    file_url = request.file_url
    episode_id = request.episode_id
    suffix = ".mp4"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with requests.get(file_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        tmp.write(chunk)
        except Exception as e:
            raise HTTPException(
                status_code=422, detail=f"動画を取得できませんでした: {e}"
            )
    job_id = episode_id
    out_dir = OUTPUT_ROOT / job_id / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        (
            ffmpeg.input(str(tmp_path))
            .output(str(out_dir / "frame_%06d.png"), vf=f"fps={fps}", vsync="vfr")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg failed: {e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)}",
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
    frames: List[str] = sorted(p.name for p in out_dir.glob("frame_*.png"))
    if not frames:
        raise HTTPException(
            status_code=422,
            detail="フレームが抽出できませんでした。fpsや入力動画を確認してください。",
        )
    payload = {
        "job_id": job_id,
        "frame_count": len(frames),
        "fps": fps,
        "out_dir": str(
            (Path(os.environ.get("OUTPUT_DIR", "./out")) / job_id / "frames").as_posix()
        ),
    }
    return JSONResponse(content=payload)


@router.post("/ocr/text")
async def ocr_text(
    job_id: str,
):
    frames_dir = OUTPUT_ROOT / job_id / "frames"
    if not frames_dir.exists():
        raise HTTPException(
            status_code=404, detail=f"frames dir not found: {frames_dir}"
        )
    frames: List[Path] = sorted(frames_dir.glob("frame_*.png"))
    if not frames:
        raise HTTPException(status_code=404, detail="no frames in the job")

    results = []
    for f in frames:
        # OCRの精度向上のために前処理を行う
        img = preprocess(f)
        # 日本語OCRを実行
        text = pytesseract.image_to_string(img, lang="jpn").strip()
        if text:
            results.append({"frame": f.name, "text": re.sub(r"\s+", "", text).strip()})

    seen = set()
    data = []
    pattern = re.compile(
        r"(\d{2}:\d{2})・[話語]者(\d+)(.*?)(?=\d{2}:\d{2}・[話語]者\d+|$)", re.DOTALL
    )

    for item in results:
        for match in pattern.finditer(item["text"]):
            time, speaker_id, body = match.groups()
            key = (time, speaker_id)
            if key not in seen:
                seen.add(key)
                text = re.sub(r"\s+", " ", body).strip()
                data.append({"time": time, "speaker": int(speaker_id), "text": text})

    if not results:
        raise HTTPException(status_code=422, detail="OCR結果が空でした")
    return JSONResponse(
        content={
            "job_id": job_id,
            "data": data,
        }
    )
