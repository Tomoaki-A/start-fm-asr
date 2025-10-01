import os
import tempfile
from pathlib import Path
from typing import List

import ffmpeg
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


class Request(BaseModel):
    file_url: str
    episode_id: str


OUTPUT_ROOT = Path(os.environ.get("OUTPUT_DIR", "./out")).resolve()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


@router.post("/ocr_capture")
async def ocr_endpoint(request: Request):
    file_url = request.file_url
    episode_id = request.episode_id
    fps = 4
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
