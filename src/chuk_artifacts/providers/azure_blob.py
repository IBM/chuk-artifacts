# -*- coding: utf-8 -*-
# chuk_artifacts/providers/azure_blob.py
"""
Azure Blob Storage provider for artifact storage.

Uses azure-storage-blob to provide Azure Blob Storage with S3-compatible interface.
Supports connection string or account name/key authentication.
"""

from __future__ import annotations

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Callable, AsyncContextManager, Dict
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class AzureBlobAdapter:
    """
    Adapter that makes Azure Blob Storage look like an S3 client.

    This adapter bridges the gap between:
    - S3-style API (put_object, get_object, etc.)
    - Azure Blob Storage API (upload_blob, download_blob, etc.)
    """

    def __init__(
        self,
        blob_service_client,
        account_name: Optional[str] = None,
        account_key: Optional[str] = None,
    ):
        """
        Initialize adapter with Azure BlobServiceClient.

        Parameters
        ----------
        blob_service_client : BlobServiceClient
            The Azure blob service client to wrap
        account_name : str, optional
            Storage account name (for SAS token generation)
        account_key : str, optional
            Storage account key (for SAS token generation)
        """
        self._client = blob_service_client
        self._account_name = account_name
        self._account_key = account_key
        self._closed = False
        self._lock = asyncio.Lock()

    async def put_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        Body: bytes,  # noqa: N803
        ContentType: str,  # noqa: N803
        Metadata: Dict[str, str],  # noqa: N803
    ):
        """Store object in Azure Blob Storage."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        async with self._lock:
            # Get container client (S3 Bucket → Azure Container)
            container_client = self._client.get_container_client(Bucket)

            # Ensure container exists
            try:
                await container_client.create_container()
            except ResourceExistsError:
                pass  # Container already exists
            except Exception as e:
                logger.debug(f"Container creation check failed: {e}")
                # Continue anyway - might have read-only access

            # Get blob client (S3 Key → Azure Blob Name)
            blob_client = container_client.get_blob_client(Key)

            # Upload blob with metadata
            await blob_client.upload_blob(
                Body,
                overwrite=True,
                content_settings=ContentSettings(content_type=ContentType),
                metadata=Metadata,
            )

            # Get properties for ETag
            properties = await blob_client.get_blob_properties()

            return {
                "ResponseMetadata": {"HTTPStatusCode": 200},
                # Azure SDK returns ETags with quotes, normalize by stripping and re-adding
                "ETag": f'"{properties.etag.strip(chr(34))}"',
            }

    async def get_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Retrieve object from Azure Blob Storage."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceNotFoundError

        # Get container and blob clients
        container_client = self._client.get_container_client(Bucket)
        blob_client = container_client.get_blob_client(Key)

        # Check if blob exists
        try:
            # Download blob
            download_stream = await blob_client.download_blob()
            data = await download_stream.readall()

            # Get properties for metadata
            properties = await blob_client.get_blob_properties()

            return {
                "Body": data,
                "ContentType": (
                    properties.content_settings.content_type
                    if properties.content_settings
                    else "application/octet-stream"
                ),
                "Metadata": properties.metadata or {},
                "ContentLength": properties.size,
                "LastModified": properties.last_modified,
                # Normalize ETag quoting
                "ETag": f'"{properties.etag.strip(chr(34))}"',
            }

        except ResourceNotFoundError:
            # Mimic S3 NoSuchKey error
            error = {
                "Error": {
                    "Code": "NoSuchKey",
                    "Message": "The specified key does not exist.",
                    "Key": Key,
                    "BucketName": Bucket,
                }
            }
            raise Exception(f"NoSuchKey: {error}")

    async def head_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Get object metadata without body."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceNotFoundError

        # Get container and blob clients
        container_client = self._client.get_container_client(Bucket)
        blob_client = container_client.get_blob_client(Key)

        try:
            # Get properties without downloading
            properties = await blob_client.get_blob_properties()

            return {
                "ContentType": (
                    properties.content_settings.content_type
                    if properties.content_settings
                    else "application/octet-stream"
                ),
                "Metadata": properties.metadata or {},
                "ContentLength": properties.size,
                "LastModified": properties.last_modified,
                # Normalize ETag quoting
                "ETag": f'"{properties.etag.strip(chr(34))}"',
            }

        except ResourceNotFoundError:
            raise Exception(f"NoSuchKey: {Key}")

    async def head_bucket(self, *, Bucket: str):  # noqa: N803
        """Check if container exists."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceNotFoundError

        container_client = self._client.get_container_client(Bucket)

        try:
            await container_client.get_container_properties()
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}
        except ResourceNotFoundError:
            return {"ResponseMetadata": {"HTTPStatusCode": 404}}

    async def delete_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Delete object from Azure Blob Storage."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceNotFoundError

        # Get container and blob clients
        container_client = self._client.get_container_client(Bucket)
        blob_client = container_client.get_blob_client(Key)

        # Delete blob (don't error if doesn't exist - S3 behavior)
        try:
            await blob_client.delete_blob()
        except ResourceNotFoundError:
            pass  # S3 delete is idempotent - blob not found is OK

        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    async def list_objects_v2(
        self,
        *,
        Bucket: str,  # noqa: N803
        Prefix: str = "",  # noqa: N803
        MaxKeys: int = 1000,  # noqa: N803
    ):
        """List objects with optional prefix filtering."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        from azure.core.exceptions import ResourceNotFoundError

        # Get container client
        container_client = self._client.get_container_client(Bucket)

        try:
            # List blobs with prefix
            contents = []

            async for blob in container_client.list_blobs(
                name_starts_with=Prefix if Prefix else None
            ):
                contents.append(
                    {
                        "Key": blob.name,
                        "Size": blob.size,
                        "LastModified": blob.last_modified,
                        # Normalize ETag quoting
                        "ETag": f'"{blob.etag.strip(chr(34))}"',
                    }
                )

                # Limit results
                if len(contents) >= MaxKeys:
                    break

            return {
                "Contents": contents,
                "KeyCount": len(contents),
                "IsTruncated": len(contents) >= MaxKeys,
            }

        except ResourceNotFoundError:
            # Container doesn't exist - return empty
            return {
                "Contents": [],
                "KeyCount": 0,
                "IsTruncated": False,
            }

    async def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: Dict[str, str],  # noqa: N803
        ExpiresIn: int,  # noqa: N803
    ) -> str:
        """
        Generate presigned URL using Azure SAS token.

        Note: Requires account_name and account_key to be set.
        """
        if self._closed:
            raise RuntimeError("Client has been closed")

        if not (self._account_name and self._account_key):
            raise RuntimeError(
                "Presigned URL generation requires AZURE_STORAGE_ACCOUNT_NAME "
                "and AZURE_STORAGE_ACCOUNT_KEY to be set"
            )

        from azure.storage.blob import generate_blob_sas, BlobSasPermissions

        bucket = Params["Bucket"]
        key = Params["Key"]

        # Map S3 operations to Azure permissions
        if operation in ("get_object", "head_object"):
            permission = BlobSasPermissions(read=True)
        elif operation == "put_object":
            permission = BlobSasPermissions(write=True, create=True)
        else:
            raise ValueError(f"Unsupported operation: {operation}")

        # Generate SAS token
        sas_token = generate_blob_sas(
            account_name=self._account_name,
            container_name=bucket,
            blob_name=key,
            account_key=self._account_key,
            permission=permission,
            expiry=datetime.now(timezone.utc) + timedelta(seconds=ExpiresIn),
        )

        # Construct full URL
        blob_url = (
            f"https://{self._account_name}.blob.core.windows.net/{bucket}/{key}"
        )
        return f"{blob_url}?{sas_token}"

    async def close(self):
        """Clean up resources."""
        if not self._closed:
            self._closed = True
            await self._client.close()


def factory(
    *,
    connection_string: Optional[str] = None,
    account_name: Optional[str] = None,
    account_key: Optional[str] = None,
) -> Callable[[], AsyncContextManager]:
    """
    Create Azure Blob Storage client factory.

    Parameters
    ----------
    connection_string : str, optional
        Azure storage connection string (preferred method)
    account_name : str, optional
        Storage account name (alternative to connection_string)
    account_key : str, optional
        Storage account key (alternative to connection_string)

    Returns
    -------
    Callable[[], AsyncContextManager]
        Factory function that returns Azure Blob client context managers

    Environment Variables
    ---------------------
    - AZURE_STORAGE_CONNECTION_STRING: Full connection string
    - AZURE_STORAGE_ACCOUNT_NAME: Storage account name
    - AZURE_STORAGE_ACCOUNT_KEY: Storage account key
    """
    # Get configuration from parameters or environment
    connection_string = connection_string or os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )
    account_name = account_name or os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    account_key = account_key or os.getenv("AZURE_STORAGE_ACCOUNT_KEY")

    # Validate credentials
    if not connection_string and not (account_name and account_key):
        raise RuntimeError(
            "Azure credentials missing. Set AZURE_STORAGE_CONNECTION_STRING "
            "or AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY "
            "environment variables."
        )

    @asynccontextmanager
    async def _ctx():
        from azure.storage.blob.aio import BlobServiceClient

        # Create client based on credential type
        if connection_string:
            client = BlobServiceClient.from_connection_string(connection_string)
            # Extract account name from connection string if needed
            if not account_name:
                try:
                    for part in connection_string.split(";"):
                        if part.startswith("AccountName="):
                            extracted_name = part.split("=", 1)[1]
                            break
                    else:
                        extracted_name = None
                except Exception:
                    extracted_name = None
            else:
                extracted_name = account_name
        else:
            account_url = f"https://{account_name}.blob.core.windows.net"
            client = BlobServiceClient(
                account_url=account_url, credential=account_key
            )
            extracted_name = account_name

        # Wrap in adapter
        adapter = AzureBlobAdapter(
            client, account_name=extracted_name, account_key=account_key
        )

        try:
            yield adapter
        finally:
            await adapter.close()

    return _ctx
