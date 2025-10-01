from pathlib import Path

import numpy
from PIL import Image, ImageFilter, ImageOps


def preprocess(img_path: Path) -> Image.Image:
    im = Image.open(img_path).convert("L")  # グレースケール
    im = ImageOps.autocontrast(im)  # 自動コントラスト
    im = im.filter(ImageFilter.MedianFilter(size=3))  # ノイズ軽減

    threshold = 175
    lut = [0 if i <= threshold else 255 for i in range(256)]  # 0-255のテーブル
    im = im.point(lut)  # ← lambdaではなくLUTを渡す

    # TesseractはL(8bit)か二値(1bit)どちらでもOK。二値にしたいなら:
    # im = im.point(lut, mode="1").convert("L")
    return im


def crop_top_bottom_ui(bgr: numpy.ndarray) -> numpy.ndarray:
    h, w = bgr.shape[:2]
    top = int(h * 0.07)
    bottom = int(h * 0.14)
    cropped = bgr[top : h - bottom, :]
    return cropped
