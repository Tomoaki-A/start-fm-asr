# 🎙️ START/FM 音声文字起こしフロー設計

## 方針のポイント
- **DB の単一ライターは Next.js**（Supabase に書き込むのは Next.js のみ）  
- **Python (FastAPI)** は以下の責務に限定  
  - 音声を GCS にアップロード  
  - Google Speech-to-Text (LongRunningRecognize; LRR) を起動  
  - 状態と結果を **GCS 上の JSON** として管理  
- **Next.js** は  
  - ユーザーの操作（「文字起こし開始」「最新情報取得」）をトリガー  
  - Python API を呼び出して状態を取得  
  - 完了済みなら Supabase に保存  

---

## 処理フロー

### 1. 文字起こし開始
1. Next.js → Python  
   - `POST /transcriptions { episodeId, audio_url }`
2. Python 側の処理
   - 音声を GCS に保存（`gs://bucket/uploads/...`）
   - `long_running_recognize` を起動し、`operationName` を取得
   - **ジョブ JSON** を GCS に保存（`status=RUNNING`）
   - レスポンス: `202 { transcriptionId }`

---

### 2. 最新情報取得（ユーザー操作）
1. Next.js → Python  
   - `GET /transcriptions/{id}`
2. Python 側の処理
   - GCS のジョブ JSON を読み込む
   - `status=RUNNING` の場合  
     - Google STT の `operationName` を照会  
     - 完了していれば結果を取得 → JSON を更新（`status=SUCCEEDED` + `result.text`）
   - JSON をそのまま返す
3. Next.js 側
   - `status=SUCCEEDED` なら結果テキストを Supabase に保存（`Transcript` / `TranscriptChunk`）
   - 以降の「最新情報取得」でも同じ JSON が返る（残しっぱなし）

---

## GCS 上の構造

```
gs://start-fm-audio/
  uploads/YYYY/MM/DD/<episodeId>.mp3
  transcriptions/<transcriptionId>.json
```

### ジョブ JSON の例
```json
{
  "version": "1.0",
  "episodeId": "ep_123",
  "audioUrl": "https://example.com/ep_123.mp3",
  "gcsUri": "gs://start-fm-audio/uploads/ep_123.mp3",
  "operationName": "projects/.../operations/...",
  "status": "SUCCEEDED",
  "engine": "google-stt:v1",
  "startedAt": "2025-09-25T01:23:45Z",
  "finishedAt": "2025-09-25T01:26:10Z",
  "result": {
    "text": "全文テキスト",
    "avgConfidence": 0.93
  },
  "error": null
}
```

---

## Supabase 側の設計（Prisma）

```prisma
model Transcript {
  id            String   @id @default(cuid())
  episodeId     String
  text          String
  engine        String   // "google-stt:v1"
  status        String   @default("SUCCEEDED")
  avgConfidence Float?
  createdAt     DateTime @default(now())
  updatedAt     DateTime @updatedAt

  @@unique([episodeId, engine])
}
```

- **Next.js** が upsert して保存  
- 一意制約で二重保存を防ぐ

---

## メリット
- ✅ **DB は Supabase だけ**（単一ライターを Next.js に統一）  
- ✅ **Python は API + GCS 状態管理だけ**（スケールや再起動に強い）  
- ✅ **ポーリング不要**。ユーザーが「最新情報取得」したタイミングでのみ STT の完了を確認  
- ✅ 結果 JSON を消さなくても良い（必要なら GCS ライフサイクルで数日後自動削除）

---

## 注意点
- **完了していてもユーザーが「最新情報取得」しない限り Supabase に保存されない**（手動取得方針）  
- **GCS に結果が溜まる** → 後でライフサイクルルール（例: 30日で削除）を設定するのがベター  
- エラー時は JSON に `status=FAILED` と `error` を記録して返す  

---

👉 このフローなら **シンプルで運用容易**、かつ **Supabase を唯一のDB** として一貫性を保てます。
