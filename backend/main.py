"""
main.py — FastAPI server for AWS S3 Knowledge Base.

Endpoints:
  GET    /api/health              — health + S3 connection check
  GET    /api/s3/files            — list all supported files in S3 bucket
  POST   /api/s3/ingest           — ingest selected S3 files into knowledge base
  POST   /api/s3/ingest-all       — ingest every supported file in the bucket
  POST   /api/chat                — ask a question (RAG-grounded answer)
  GET    /api/documents           — list ingested documents
  DELETE /api/documents           — clear entire knowledge base
  DELETE /api/documents/{doc_id}  — remove one document
  POST   /api/session/clear       — clear chat history for a session
"""

import os
import logging
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_engine import RAGEngine
from s3_connector import S3Connector

# ---------------------------------------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AWS S3 Knowledge Base API",
    description="RAG chatbot backed by documents stored in AWS S3",
    version="1.0.0",
)
 allow_origins=["*"],
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise engines
try:
    rag = RAGEngine()
    logger.info("RAG engine initialised.")
except EnvironmentError as e:
    rag = None
    logger.error("RAG engine failed: %s", e)

try:
    s3 = S3Connector()
    logger.info("S3 connector initialised (bucket: %s).", s3.bucket)
except EnvironmentError as e:
    s3 = None
    logger.error("S3 connector failed: %s", e)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message:    str
    session_id: str = ""

class IngestRequest(BaseModel):
    keys: list[str]           # list of S3 object keys to ingest

class SessionClearRequest(BaseModel):
    session_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    s3_status = s3.test_connection() if s3 else {"connected": False, "error": "S3 not configured"}
    return {
        "status":    "ok" if (rag and s3_status.get("connected")) else "degraded",
        "rag_ready": rag is not None,
        "s3":        s3_status,
    }


@app.get("/api/s3/files")
def list_s3_files(prefix: str = ""):
    if not s3:
        raise HTTPException(status_code=503, detail="S3 connector not available. Check AWS env vars.")
    try:
        files = s3.list_files(prefix=prefix)
        # Mark which files are already ingested
        if rag:
            for f in files:
                f["ingested"] = rag.is_already_ingested(f["key"])
        return {"files": files, "count": len(files), "bucket": s3.bucket}
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/s3/ingest")
def ingest_files(req: IngestRequest):
    if not s3:
        raise HTTPException(status_code=503, detail="S3 connector not available.")
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    if not req.keys:
        raise HTTPException(status_code=400, detail="No keys provided.")

    results, errors = [], []

    for key in req.keys:
        try:
            docs = s3.read_file_as_documents(key)
            info = rag.ingest_documents(docs, key)
            results.append(info)
        except Exception as exc:
            logger.error("Failed to ingest '%s': %s", key, exc)
            errors.append({"key": key, "error": str(exc)})

    return {
        "ingested": results,
        "errors":   errors,
        "message":  f"{len(results)} file(s) ingested, {len(errors)} failed.",
    }


@app.post("/api/s3/ingest-all")
def ingest_all(prefix: str = ""):
    if not s3:
        raise HTTPException(status_code=503, detail="S3 connector not available.")
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")

    try:
        files = s3.list_files(prefix=prefix)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not files:
        return {"ingested": [], "errors": [], "message": "No supported files found in bucket."}

    keys = [f["key"] for f in files]
    results, errors = [], []

    for key in keys:
        try:
            docs = s3.read_file_as_documents(key)
            info = rag.ingest_documents(docs, key)
            results.append(info)
        except Exception as exc:
            logger.error("Failed to ingest '%s': %s", key, exc)
            errors.append({"key": key, "error": str(exc)})

    return {
        "ingested": results,
        "errors":   errors,
        "message":  f"{len(results)} file(s) ingested, {len(errors)} failed.",
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    import uuid
    session_id = req.session_id or str(uuid.uuid4())

    try:
        result = rag.chat(req.message.strip(), session_id)
        return {
            "answer":     result["answer"],
            "sources":    result["sources"],
            "session_id": session_id,
        }
    except Exception as exc:
        logger.exception("Chat error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/documents")
def list_documents():
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    docs = rag.list_documents()
    return {"documents": docs, "count": len(docs)}


@app.delete("/api/documents")
def clear_all_documents():
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    try:
        count = rag.clear_all_documents()
        return {"success": True, "message": f"Knowledge base cleared ({count} chunks removed)."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    if not rag.delete_document(doc_id):
        raise HTTPException(status_code=500, detail="Failed to delete document.")
    return {"success": True, "message": f"Document {doc_id} deleted."}


@app.post("/api/session/clear")
def clear_session(req: SessionClearRequest):
    if not rag:
        raise HTTPException(status_code=503, detail="RAG engine not available.")
    rag.clear_session(req.session_id)
    return {"success": True, "message": "Conversation history cleared."}


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
