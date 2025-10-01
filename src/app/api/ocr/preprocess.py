from pathlib import Path

import cv2
import numpy
from PIL import Image, ImageDraw


def debug(img: numpy.ndarray, step_name: str) -> None:
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True, parents=True)
    out_path = debug_dir / f"{step_name}.png"
    cv2.imwrite(str(out_path), img)
    print(f"[debug] {step_name}: {out_path}")


def preprocess(img_path: Path) -> Image.Image:
    im = Image.open(img_path)
    im = crop_and_mask_ui(im)
    im = unify_black_and_white_text(im)

    return im


# UIのトリミングとマスク
def crop_and_mask_ui(img: Image.Image) -> Image.Image:
    _, h = img.size
    # トリミングようにnumpy配列に変換
    arr = numpy.array(img)

    # 上部のタイトル帯をトリミング（例: 高さの10%）
    top_crop = int(h * 0.1)
    # 下部のプレイヤーUIをトリミング（例: 高さの12%）
    bottom_crop = int(h * 0.88)
    arr = arr[top_crop:bottom_crop, :, :]

    # numpy配列をPIL画像に戻す
    mask_img = Image.fromarray(arr)

    #    # 右下の丸ボタンを白で塗る（マスク）
    h2, w2, _ = arr.shape
    draw = ImageDraw.Draw(mask_img)
    radius = int(40)
    center_x = w2 / 2
    center_y = h2 - 40 - radius
    draw.ellipse(
        [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
        fill=(255, 255, 255),
    )

    return mask_img


# 白黒テキストを統一
def unify_black_and_white_text(pil_img: Image.Image) -> Image.Image:
    g = numpy.array(pil_img)
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY)

    # 2値化して黒文字と白文字のマスクを作成
    _, bin_dark = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    g_inv = 255 - g

    # 2値化して白文字のマスクを作成
    _, bin_bright = cv2.threshold(g_inv, 60, 255, cv2.THRESH_BINARY_INV)

    bin_bright_inv = cv2.bitwise_not(bin_bright)
    fused = cv2.min(bin_dark, bin_bright_inv)

    return Image.fromarray(fused)
