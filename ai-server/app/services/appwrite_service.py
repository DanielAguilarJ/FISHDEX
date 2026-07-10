"""
Appwrite client service for FishDex AI Server.
Handles file storage operations and database document CRUD.
"""

import logging
from pathlib import Path
from typing import Optional

from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.services.storage import Storage
from appwrite.input_file import InputFile
from appwrite.id import ID

from app.config import settings

logger = logging.getLogger(__name__)

_instance: Optional["AppwriteService"] = None


class AppwriteService:
    """Singleton service wrapping the Appwrite Python SDK."""

    def __init__(self):
        self.client = Client()
        self.client.set_endpoint(settings.appwrite_endpoint)
        self.client.set_project(settings.appwrite_project_id)
        self.client.set_key(settings.appwrite_api_key)

        self.databases = Databases(self.client)
        self.storage = Storage(self.client)
        self.database_id = settings.appwrite_database_id

        logger.info(
            "AppwriteService initialized (endpoint=%s, project=%s)",
            settings.appwrite_endpoint,
            settings.appwrite_project_id,
        )

    # ─── Storage ───────────────────────────────────────────────────────────────

    def download_file(self, bucket_id: str, file_id: str, output_path: str | Path) -> Path:
        """Download a file from Appwrite storage to a local path."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            result = self.storage.get_file_download(bucket_id, file_id)
            output_path.write_bytes(result)
            logger.debug("Downloaded file %s/%s -> %s", bucket_id, file_id, output_path)
            return output_path
        except Exception as e:
            logger.error("Failed to download file %s/%s: %s", bucket_id, file_id, e)
            raise

    def upload_file(
        self,
        bucket_id: str,
        local_path: str | Path,
        filename: str,
        permissions: Optional[list[str]] = None,
    ) -> str:
        """Upload a local file to Appwrite storage. Returns the new file ID."""
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"Cannot upload, file not found: {local_path}")

        try:
            file_id = ID.unique()
            input_file = InputFile.from_path(str(local_path))

            kwargs = {
                "bucket_id": bucket_id,
                "file_id": file_id,
                "file": input_file,
            }
            if permissions is not None:
                kwargs["permissions"] = permissions

            result = self.storage.create_file(**kwargs)
            created_id = result["$id"]
            logger.debug("Uploaded file %s -> %s/%s", filename, bucket_id, created_id)
            return created_id
        except Exception as e:
            logger.error("Failed to upload file %s to bucket %s: %s", filename, bucket_id, e)
            raise

    # ─── Database ──────────────────────────────────────────────────────────────

    def create_document(
        self, collection_id: str, document_id: str, data: dict
    ) -> dict:
        """Create a new document in the database."""
        try:
            result = self.databases.create_document(
                database_id=self.database_id,
                collection_id=collection_id,
                document_id=document_id,
                data=data,
            )
            logger.debug("Created document %s in %s", document_id, collection_id)
            return result
        except Exception as e:
            logger.error(
                "Failed to create document %s in %s: %s",
                document_id, collection_id, e,
            )
            raise

    def update_document(
        self, collection_id: str, document_id: str, data: dict
    ) -> dict:
        """Update an existing document."""
        try:
            result = self.databases.update_document(
                database_id=self.database_id,
                collection_id=collection_id,
                document_id=document_id,
                data=data,
            )
            logger.debug("Updated document %s in %s", document_id, collection_id)
            return result
        except Exception as e:
            logger.error(
                "Failed to update document %s in %s: %s",
                document_id, collection_id, e,
            )
            raise

    def get_document(self, collection_id: str, document_id: str) -> dict:
        """Retrieve a single document by ID."""
        try:
            result = self.databases.get_document(
                database_id=self.database_id,
                collection_id=collection_id,
                document_id=document_id,
            )
            return result
        except Exception as e:
            logger.error(
                "Failed to get document %s from %s: %s",
                document_id, collection_id, e,
            )
            raise

    def list_documents(
        self, collection_id: str, queries: Optional[list[str]] = None
    ) -> list[dict]:
        """List documents in a collection, optionally filtered by queries."""
        try:
            kwargs = {
                "database_id": self.database_id,
                "collection_id": collection_id,
            }
            if queries is not None:
                kwargs["queries"] = queries

            result = self.databases.list_documents(**kwargs)
            return result.get("documents", [])
        except Exception as e:
            logger.error(
                "Failed to list documents in %s: %s", collection_id, e
            )
            raise


def get_appwrite_service() -> AppwriteService:
    """Return the singleton AppwriteService instance."""
    global _instance
    if _instance is None:
        _instance = AppwriteService()
    return _instance
