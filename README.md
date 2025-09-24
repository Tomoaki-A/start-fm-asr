## docker起動
```
docker run --rm -p 8081:8081 \
  --env-file .env \
  -e WATCHFILES_FORCE_POLLING=1 \
  -v "$(pwd)":/app \
  -v "$(pwd)/gcp-key.json":/app/gcp-key.json:ro \
  --name start-fm-asr \
  start-fm-asr \
  uvicorn main:app --host 0.0.0.0 --port 8081 \
  --reload --reload-dir /app
```
