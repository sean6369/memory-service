"""
BlobStore interface + local filesystem implementation.

This is the MVP substitute for S3/GCS. Only used for raw KB documents (pdf/docx/pptx).
The interface seam allows swapping in cloud storage later.
"""

import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.config import settings


class BlobStore(ABC):
    """Abstract blob storage interface — S3/GCS-ready seam."""

    @abstractmethod
    def put(self, data: bytes, filename: str) -> str:
        """Store a blob and return its URI."""
        ...

    @abstractmethod
    def get(self, uri: str) -> bytes:
        """Retrieve a blob by URI."""
        ...

    @abstractmethod
    def delete(self, uri: str) -> None:
        """Delete a blob by URI."""
        ...


class LocalFSBlobStore(BlobStore):
    """Local filesystem blob store for the MVP."""

    def __init__(self, base_path: str | None = None):
        self._base = Path(base_path or settings.blob_storage_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, filename: str) -> str:
        blob_id = f"{uuid.uuid4().hex}_{filename}"
        path = self._base / blob_id
        path.write_bytes(data)
        return f"local://{blob_id}"

    def get(self, uri: str) -> bytes:
        blob_id = uri.replace("local://", "")
        path = self._base / blob_id
        if not path.exists():
            raise FileNotFoundError(f"Blob not found: {uri}")
        return path.read_bytes()

    def delete(self, uri: str) -> None:
        blob_id = uri.replace("local://", "")
        path = self._base / blob_id
        if path.exists():
            os.remove(path)


# Singleton for the application
blob_store = LocalFSBlobStore()
