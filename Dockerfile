# syntax=docker/dockerfile:1
FROM python:3.11-slim

# ffmpegインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-jpn \
 && rm -rf /var/lib/apt/lists/*

# アプリ実行用の作業ディレクトリ
WORKDIR /app

# 依存ライブラリをコピー & インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリコードをコピー
COPY src ./src

# FastAPIを8081ポートで起動
EXPOSE 8081
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8081"]
