# AWS S3 Knowledge Base

A **RAG (Retrieval-Augmented Generation) chatbot** that reads documents directly from an **AWS S3 bucket** — no local file uploads needed. Browse your bucket, select files to ingest on-demand, and ask questions with source-cited answers.

Styled with the **LinkedIn** visual identity.

---

## What We Built

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Backend API | Python 3 + FastAPI |
| S3 Integration | AWS boto3 — reads files into memory, no local disk writes |
| RAG Pipeline | LangChain |
| Vector Store | ChromaDB (persistent, local) |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | OpenAI `gpt-4o-mini` |
| Document Parsing | PyPDF (PDF, in-memory), UTF-8 decode (TXT/MD) |

---

## Key Features

- **S3 file browser** — lists all PDF/TXT/MD files in your bucket with size and last-modified info
- **On-demand ingestion** — select individual files or ingest the entire bucket with one click
- **Already-ingested badges** — files already in the KB are marked so you don't duplicate them
- **Folder prefix filter** — filter S3 files by folder path (e.g. `reports/2024/`)
- **Zero local storage** — documents are streamed from S3 into memory; nothing is written to disk
- **RAG answers with citations** — answers reference the source S3 file and page number
- **Conversation memory** — 10-turn chat history per session
- **Knowledge base management** — remove individual documents or clear everything
- **LinkedIn theme** — navy `#1D2226`, blue `#0A66C2`, background `#F3F2EF`

---

## Project Structure

```
AWS S3 Knowledge Base/
├── backend/
│   ├── main.py           # FastAPI server — all REST endpoints
│   ├── rag_engine.py     # RAG pipeline: chunking, embeddings, retrieval, chat
│   ├── s3_connector.py   # AWS S3: list files, stream docs into memory
│   ├── requirements.txt  # Python dependencies
│   ├── env.txt           # Visible environment variable template
│   └── .env              # Your actual keys (git-ignored)
├── frontend/
│   ├── index.html        # UI layout
│   ├── style.css         # LinkedIn-themed styles
│   └── app.js            # All frontend logic
├── setup.sh              # One-shot install script
├── .gitignore
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Server health + S3 connection check |
| `GET` | `/api/s3/files` | List supported files in S3 bucket |
| `POST` | `/api/s3/ingest` | Ingest selected S3 files (by key list) |
| `POST` | `/api/s3/ingest-all` | Ingest all supported files in bucket |
| `POST` | `/api/chat` | Send a message, receive a RAG answer |
| `GET` | `/api/documents` | List ingested documents |
| `DELETE` | `/api/documents` | Clear entire knowledge base |
| `DELETE` | `/api/documents/{doc_id}` | Remove one document |
| `POST` | `/api/session/clear` | Clear chat history for a session |

---

## AWS Setup (Required)

You need an **IAM user** with S3 read access. Here's how:

1. Sign in to **AWS Console** → **IAM** → **Users** → **Create user**
2. On the permissions step, attach the managed policy: **`AmazonS3ReadOnlyAccess`**
3. Once the user is created, go to **Security credentials** → **Create access key**
4. Choose **"Local code"** as the use case
5. Copy the **Access Key ID** and **Secret Access Key** into `backend/.env`

> Free tier note: S3 GET requests and data transfer are within free tier limits for typical document workloads.

---

## Setup & Running

### Prerequisites
- Python 3.9+
- OpenAI API key — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- AWS IAM user with S3ReadOnly access (see above)
- An S3 bucket containing PDF or TXT files

### 1. Install dependencies

```bash
cd "AWS S3 Knowledge Base"
bash setup.sh
```

### 2. Configure environment variables

Open `backend/env.txt`, fill in all values, then rename it to `.env`:

```
OPENAI_API_KEY=sk-proj-...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET_NAME=my-bucket-name
```

> On Mac: press `Cmd + Shift + .` in Finder to reveal hidden `.env` file.

### 3. Start the backend

```bash
cd backend
source .venv/bin/activate
python3 main.py
```

API starts at `http://localhost:8000`.

### 4. Open the frontend

Open `frontend/index.html` in your browser (or use VS Code Live Server).

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key |
| `AWS_ACCESS_KEY_ID` | ✅ | — | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | ✅ | — | IAM user secret key |
| `AWS_REGION` | ✅ | `us-east-1` | Region of your S3 bucket |
| `S3_BUCKET_NAME` | ✅ | — | Name of the S3 bucket |
| `LLM_MODEL` | | `gpt-4o-mini` | OpenAI model for answers |
| `EMBEDDING_MODEL` | | `text-embedding-3-small` | OpenAI model for embeddings |
| `RETRIEVAL_TOP_K` | | `4` | Chunks retrieved per query |
| `CHUNK_SIZE` | | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | | `200` | Overlap between chunks |
| `CHROMA_PERSIST_DIR` | | `./chroma_db` | ChromaDB storage path |

---

## How It Works

```
S3 Bucket (PDF/TXT/MD)
        │
        │  boto3 — streamed into memory (BytesIO), no disk writes
        ▼
  Text extraction
  (PyPDF / UTF-8 decode)
        │
        ▼
  LangChain text splitter
  (chunks with overlap)
        │
        ▼
  OpenAI embeddings  ──►  ChromaDB vector store
                                  │
                          on user question:
                          similarity search (top-K chunks)
                                  │
                                  ▼
                    GPT-4o-mini + chat history
                                  │
                                  ▼
                       Grounded answer + S3 source citations
```

---

## Brand & Design

LinkedIn visual identity:

| Element | Colour |
|---|---|
| Sidebar | Dark navy `#1D2226` |
| Primary buttons / user bubbles | LinkedIn blue `#0A66C2` |
| Button hover | Deep blue `#004182` |
| Page background | Off-white `#F3F2EF` |
| Chat cards | White `#FFFFFF` |
| Success indicators | LinkedIn green `#057642` |
| Font | Roboto / system-ui |
