from fastapi import FastAPI
from src.app.api.transcribe import router as transcribe_router

app = FastAPI()
app.include_router(transcribe_router)

@app.get("/health")
def health_check():
    return {"ok": True}
