"""
s3_connector.py — AWS S3 integration.

Reads documents directly from S3 into memory (no local temp files).
Supports PDF, TXT, and Markdown files.
"""

import os
import logging
from io import BytesIO
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from pypdf import PdfReader
from langchain.schema import Document

load_dotenv()
logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class S3Connector:
    """Handles listing and reading documents from an S3 bucket."""

    def __init__(self) -> None:
        self.bucket     = os.getenv("S3_BUCKET_NAME", "")
        self.region     = os.getenv("AWS_REGION", "us-east-1")
        access_key      = os.getenv("AWS_ACCESS_KEY_ID", "")
        secret_key      = os.getenv("AWS_SECRET_ACCESS_KEY", "")

        if not self.bucket:
            raise EnvironmentError("S3_BUCKET_NAME is not set in .env")
        if not access_key or access_key == "your_aws_access_key_id_here":
            raise EnvironmentError("AWS_ACCESS_KEY_ID is not set in .env")
        if not secret_key or secret_key == "your_aws_secret_access_key_here":
            raise EnvironmentError("AWS_SECRET_ACCESS_KEY is not set in .env")

        self.client = boto3.client(
            "s3",
            region_name=self.region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_files(self, prefix: str = "") -> list[dict]:
        """
        Return all supported files in the bucket (optionally filtered by prefix/folder).
        Each entry: {key, size_kb, last_modified, extension}
        """
        files = []
        paginator = self.client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    ext = os.path.splitext(key)[1].lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        files.append({
                            "key":           key,
                            "size_kb":       round(obj["Size"] / 1024, 1),
                            "last_modified": obj["LastModified"].isoformat(),
                            "extension":     ext,
                        })
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "NoSuchBucket":
                raise ValueError(f"Bucket '{self.bucket}' does not exist.")
            elif code in ("AccessDenied", "403"):
                raise PermissionError(f"Access denied to bucket '{self.bucket}'. Check IAM permissions.")
            raise

        logger.info("Listed %d supported files from s3://%s/%s", len(files), self.bucket, prefix)
        return files

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_file_as_documents(self, key: str) -> list[Document]:
        """
        Download a file from S3 into memory and return a list of LangChain Documents.
        No files are written to disk.
        """
        ext = os.path.splitext(key)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext}")

        logger.info("Reading s3://%s/%s", self.bucket, key)

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            raw_bytes = response["Body"].read()
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            raise RuntimeError(f"Could not read '{key}' from S3: {code}")

        filename = os.path.basename(key)

        if ext == ".pdf":
            return self._parse_pdf(raw_bytes, key, filename)
        else:
            return self._parse_text(raw_bytes, key, filename)

    def _parse_pdf(self, data: bytes, key: str, filename: str) -> list[Document]:
        reader = PdfReader(BytesIO(data))
        docs   = []
        for page_num, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                docs.append(Document(
                    page_content=text,
                    metadata={"source": key, "filename": filename, "page": page_num},
                ))
        if not docs:
            raise ValueError(f"No extractable text found in '{filename}'. The PDF may be scanned/image-based.")
        return docs

    def _parse_text(self, data: bytes, key: str, filename: str) -> list[Document]:
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError(f"File '{filename}' is empty.")
        return [Document(
            page_content=text,
            metadata={"source": key, "filename": filename, "page": 0},
        )]

    # ------------------------------------------------------------------
    # Connection test
    # ------------------------------------------------------------------

    def test_connection(self) -> dict:
        """Verify credentials and bucket access. Returns status dict."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            files = self.list_files()
            return {
                "connected":  True,
                "bucket":     self.bucket,
                "region":     self.region,
                "file_count": len(files),
            }
        except PermissionError as exc:
            return {"connected": False, "error": str(exc)}
        except ValueError as exc:
            return {"connected": False, "error": str(exc)}
        except NoCredentialsError:
            return {"connected": False, "error": "Invalid or missing AWS credentials."}
        except Exception as exc:
            return {"connected": False, "error": str(exc)}
