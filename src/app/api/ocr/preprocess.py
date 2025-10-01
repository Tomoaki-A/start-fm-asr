from pathlib import Path
from typing import Union

import cv2
import numpy
from PIL import Image


def debug(
    img: numpy.ndarray, step_name: str, debug_dir: Union[str, Path] = "debug_out"
) -> None:
    debug_dir = Path(debug_dir)
    debug_dir.mkdir(exist_ok=True, parents=True)
    out_path = debug_dir / f"{step_name}.png"
    cv2.imwrite(str(out_path), img)
    print(f"[debug] {step_name}: {out_path}")


def preprocess(img_path: Path) -> Image.Image:
    im = Image.open(img_path)
    # debug(numpy.array(im), "01_original")

    return im


def crop_top_bottom_ui(bgr: numpy.ndarray) -> numpy.ndarray:
    h, w = bgr.shape[:2]
    top = int(h * 0.07)
    bottom = int(h * 0.14)
    cropped = bgr[top : h - bottom, :]
    return cropped
