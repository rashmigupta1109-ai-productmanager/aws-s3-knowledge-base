"""
rag_engine.py — RAG pipeline for the AWS S3 Knowledge Base.

Ingests LangChain Documents (sourced from S3), stores chunks in ChromaDB,
and answers questions using conversational retrieval.
"""

import os
import logging
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferWindowMemory

load_dotenv()
logger = logging.getLogger(__name__)

OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL          = os.getenv("LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
RETRIEVAL_TOP_K    = int(os.getenv("RETRIEVAL_TOP_K", "4"))
CHUNK_SIZE         = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP      = int(os.getenv("CHUNK_OVERLAP", "200"))
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")


class RAGEngine:
    """Manages document ingestion from S3, vector storage, and answer generation."""

    def __init__(self) -> None:
        if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
            raise EnvironmentError(
                "OPENAI_API_KEY is not set. Please edit backend/.env."
            )

        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            openai_api_key=OPENAI_API_KEY,
        )

        self.vectorstore = Chroma(
            collection_name="s3_kb_docs",
            embedding_function=self.embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )

        self.llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=0.2,
            openai_api_key=OPENAI_API_KEY,
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        self._memories: dict[str, ConversationBufferWindowMemory] = {}

    # ------------------------------------------------------------------
    # Ingestion (documents come pre-loaded from S3)
    # ------------------------------------------------------------------

    def ingest_documents(self, docs: list[Document], s3_key: str) -> dict:
        """
        Split and embed a list of LangChain Documents (already read from S3).
        Returns ingestion summary.
        """
        import uuid
        chunks = self.text_splitter.split_documents(docs)
        doc_id = str(uuid.uuid4())
        filename = docs[0].metadata.get("filename", s3_key) if docs else s3_key

        for chunk in chunks:
            chunk.metadata["doc_id"]   = doc_id
            chunk.metadata["s3_key"]   = s3_key
            chunk.metadata["filename"] = filename

        self.vectorstore.add_documents(chunks)
        logger.info("Ingested '%s' → %d chunks (doc_id=%s)", s3_key, len(chunks), doc_id)
        return {"doc_id": doc_id, "filename": filename, "s3_key": s3_key, "chunks": len(chunks)}

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def _get_memory(self, session_id: str) -> ConversationBufferWindowMemory:
        if session_id not in self._memories:
            self._memories[session_id] = ConversationBufferWindowMemory(
                k=10,
                memory_key="chat_history",
                return_messages=True,
                output_key="answer",
            )
        return self._memories[session_id]

    def chat(self, question: str, session_id: str) -> dict:
        has_docs = self.vectorstore._collection.count() > 0

        if has_docs:
            retriever = self.vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": RETRIEVAL_TOP_K},
            )
            memory = self._get_memory(session_id)
            chain  = ConversationalRetrievalChain.from_llm(
                llm=self.llm,
                retriever=retriever,
                memory=memory,
                return_source_documents=True,
                output_key="answer",
            )
            result      = chain.invoke({"question": question})
            answer      = result["answer"]
            source_docs = result.get("source_documents", [])
            sources     = self._dedupe_sources(source_docs)
        else:
            from langchain.schema import HumanMessage, SystemMessage
            messages = [
                SystemMessage(content=(
                    "You are a helpful AI assistant connected to an AWS S3 knowledge base. "
                    "No documents have been ingested yet. Answer using your general knowledge "
                    "and remind the user to sync documents from S3 first."
                )),
                HumanMessage(content=question),
            ]
            response = self.llm.invoke(messages)
            answer   = response.content
            sources  = []

        return {"answer": answer, "sources": sources, "session_id": session_id}

    def _dedupe_sources(self, docs: list) -> list[dict]:
        seen, sources = set(), []
        for doc in docs:
            fname  = doc.metadata.get("filename", "unknown")
            s3_key = doc.metadata.get("s3_key", "")
            page   = doc.metadata.get("page", "")
            key    = f"{s3_key}:{page}"
            if key not in seen:
                seen.add(key)
                sources.append({"filename": fname, "s3_key": s3_key, "page": page})
        return sources

    # ------------------------------------------------------------------
    # Document management
    # ------------------------------------------------------------------

    def list_documents(self) -> list[dict]:
        try:
            data = self.vectorstore._collection.get(include=["metadatas"])
            seen, docs = set(), []
            for meta in data["metadatas"]:
                doc_id = meta.get("doc_id")
                if doc_id and doc_id not in seen:
                    seen.add(doc_id)
                    docs.append({
                        "doc_id":   doc_id,
                        "filename": meta.get("filename", "unknown"),
                        "s3_key":   meta.get("s3_key", ""),
                    })
            return docs
        except Exception as exc:
            logger.warning("Could not list documents: %s", exc)
            return []

    def is_already_ingested(self, s3_key: str) -> bool:
        """Check if a given S3 key is already in the vector store."""
        try:
            data = self.vectorstore._collection.get(
                where={"s3_key": s3_key},
                include=["metadatas"],
                limit=1,
            )
            return len(data.get("ids", [])) > 0
        except Exception:
            return False

    def delete_document(self, doc_id: str) -> bool:
        try:
            self.vectorstore._collection.delete(where={"doc_id": doc_id})
            return True
        except Exception as exc:
            logger.error("Delete failed for doc_id=%s: %s", doc_id, exc)
            return False

    def clear_all_documents(self) -> int:
        try:
            data  = self.vectorstore._collection.get()
            ids   = data.get("ids", [])
            count = len(ids)
            if count:
                self.vectorstore._collection.delete(ids=ids)
            logger.info("Cleared all documents (%d chunks).", count)
            return count
        except Exception as exc:
            logger.error("Failed to clear all documents: %s", exc)
            raise

    def clear_session(self, session_id: str) -> None:
        self._memories.pop(session_id, None)
