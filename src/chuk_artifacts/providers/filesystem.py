# ===========================================================================
# chuk_artifacts/providers/filesystem.py
# ===========================================================================
"""Local-filesystem artefact store.

Objects are written relative to $ARTIFACT_FS_ROOT (default ./artifacts).
Presigned URLs use the *file://* scheme so callers can still download.
Includes comprehensive S3-compatible methods and proper error handling.
"""

from __future__ import annotations

import os
import json
import asyncio
import time
import uuid
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict, Callable, AsyncContextManager, List, Optional
from datetime import datetime, timezone

_ROOT = Path(os.getenv("ARTIFACT_FS_ROOT", "./artifacts")).expanduser()


class _FilesystemClient:
    """Mimics the S3 surface ArtifactStore depends on with filesystem backend."""

    def __init__(self, root: Path = _ROOT):
        self._root = Path(root).expanduser().resolve()
        self._closed = False
        self._lock = asyncio.Lock()

        # Ensure root directory exists
        self._root.mkdir(parents=True, exist_ok=True)

    def _get_object_path(self, bucket: str, key: str) -> Path:
        """Get the filesystem path for an object, incorporating bucket as subdirectory."""
        # Use bucket as a subdirectory to maintain some S3-like organization
        return self._root / bucket / key

    def _get_metadata_path(self, object_path: Path) -> Path:
        """Get the metadata file path for an object."""
        return object_path.with_suffix(object_path.suffix + ".meta.json")

    async def _ensure_parent_dir(self, path: Path):
        """Ensure parent directory exists."""
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)

    async def _write_metadata(
        self,
        meta_path: Path,
        content_type: str,
        metadata: Dict[str, str],
        size: int,
        etag: str,
    ):
        """Write metadata file."""
        meta_data = {
            "content_type": content_type,
            "metadata": metadata,
            "size": size,
            "etag": etag,
            "last_modified": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        meta_json = json.dumps(meta_data, indent=2)
        await asyncio.to_thread(meta_path.write_text, meta_json, encoding="utf-8")

    async def _write_bytes_to_file(
        self, meta_path: Path, Body: bytes, metadata: Dict[str, str]
    ):
        """
        Asynchronously write byte data to a file using pathlib.

        Args:
            meta_path: The base directory where the file should be saved.
            Body: The byte content to write.
            metadata: Dictionary containing at least the 'filename' key.
        """
        if "filename" not in metadata:
            raise ValueError("metadata must include a 'filename' key")
        target_dir = meta_path.parent
        file_path = target_dir / metadata["filename"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_bytes, Body)

    async def _read_metadata(self, meta_path: Path) -> Dict[str, Any]:
        """Read metadata file."""
        try:
            content = await asyncio.to_thread(meta_path.read_text, encoding="utf-8")
            return json.loads(content)  # type: ignore[no-any-return]
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    # ------------------------------------------------------------
    # Core S3-compatible methods
    # ------------------------------------------------------------

    async def put_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        Body: bytes,  # noqa: N803
        ContentType: str,
        Metadata: Dict[str, str],  # noqa: N803
    ):
        """Store object in filesystem with metadata."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        object_path = self._get_object_path(Bucket, Key)
        meta_path = self._get_metadata_path(object_path)

        # Generate ETag (MD5 hash like S3)
        etag = hashlib.md5(Body, usedforsecurity=False).hexdigest()

        async with self._lock:
            await self._ensure_parent_dir(object_path)
            # Write the main object file
            await asyncio.to_thread(object_path.write_bytes, Body)
            # Write the bytes object to file based on metadata info
            await self._write_bytes_to_file(
                meta_path=object_path, Body=Body, metadata=Metadata
            )
            # Write the metadata file
            await self._write_metadata(
                meta_path, ContentType, Metadata, len(Body), etag
            )

        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "ETag": f'"{etag}"'}

    async def get_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Retrieve object from filesystem."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        object_path = self._get_object_path(Bucket, Key)
        meta_path = self._get_metadata_path(object_path)

        if not object_path.exists():
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

        async with self._lock:
            body = await asyncio.to_thread(object_path.read_bytes)
            metadata = await self._read_metadata(meta_path)

        # Get file stats
        stat_info = await asyncio.to_thread(object_path.stat)

        return {
            "Body": body,
            "ContentType": metadata.get("content_type", "application/octet-stream"),
            "Metadata": metadata.get("metadata", {}),
            "ContentLength": len(body),
            "LastModified": datetime.fromtimestamp(stat_info.st_mtime),
            "ETag": metadata.get("etag", ""),
        }

    async def head_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Get object metadata without body."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        object_path = self._get_object_path(Bucket, Key)
        meta_path = self._get_metadata_path(object_path)

        if not object_path.exists():
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

        async with self._lock:
            metadata = await self._read_metadata(meta_path)
            stat_info = await asyncio.to_thread(object_path.stat)

        return {
            "ContentType": metadata.get("content_type", "application/octet-stream"),
            "Metadata": metadata.get("metadata", {}),
            "ContentLength": stat_info.st_size,
            "LastModified": datetime.fromtimestamp(stat_info.st_mtime),
            "ETag": metadata.get("etag", ""),
        }

    async def head_bucket(self, *, Bucket: str):  # noqa: N803
        """Check if bucket (directory) exists."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        bucket_path = self._root / Bucket
        if not bucket_path.exists():
            bucket_path.mkdir(parents=True, exist_ok=True)

        return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    async def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: Dict[str, str],  # noqa: N803
        ExpiresIn: int,  # noqa: N803
    ) -> str:
        """
        Generate file:// URLs for filesystem objects.

        Note: file:// URLs don't have real expiration, but we include
        expiry info for compatibility.
        """
        if self._closed:
            raise RuntimeError("Client has been closed")

        bucket, key = Params["Bucket"], Params["Key"]
        object_path = self._get_object_path(bucket, key)

        if not object_path.exists():
            raise FileNotFoundError(f"Object not found: {bucket}/{key}")

        # Create file:// URL with query parameters for compatibility
        return (
            f"file://{object_path.as_posix()}"
            f"?operation={operation}"
            f"&token={uuid.uuid4().hex}"
            f"&expires={int(time.time()) + ExpiresIn}"
        )

    async def list_objects_v2(
        self,
        *,
        Bucket: str,  # noqa: N803
        Prefix: str = "",  # noqa: N803
        MaxKeys: int = 1000,  # noqa: N803
        ContinuationToken: Optional[str] = None,  # noqa: N803
    ):
        """List objects in bucket with optional prefix filtering."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        bucket_path = self._root / Bucket
        if not bucket_path.exists():
            return {
                "Contents": [],
                "KeyCount": 0,
                "IsTruncated": False,
            }

        contents: list[dict[str, Any]] = []
        total_found = 0

        async with self._lock:
            # Walk the directory tree
            for item in bucket_path.rglob("*"):
                if item.is_file() and not item.name.endswith(".meta.json"):
                    # Get relative path from bucket root as the key
                    relative_path = item.relative_to(bucket_path)
                    key = relative_path.as_posix()

                    # Apply prefix filter
                    if not key.startswith(Prefix):
                        continue

                    total_found += 1

                    # Apply pagination
                    if len(contents) >= MaxKeys:
                        break

                    # Get file stats and metadata
                    stat_info = await asyncio.to_thread(item.stat)
                    meta_path = self._get_metadata_path(item)
                    metadata = await self._read_metadata(meta_path)

                    contents.append(
                        {
                            "Key": key,
                            "Size": stat_info.st_size,
                            "LastModified": datetime.fromtimestamp(stat_info.st_mtime),
                            "ETag": f'"{metadata.get("etag", "")}"',
                            "StorageClass": "STANDARD",
                        }
                    )

        return {
            "Contents": contents,
            "KeyCount": len(contents),
            "IsTruncated": total_found > MaxKeys,
            "MaxKeys": MaxKeys,
            "Prefix": Prefix,
        }

    async def delete_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
    ):
        """Delete object and its metadata from filesystem."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        object_path = self._get_object_path(Bucket, Key)
        meta_path = self._get_metadata_path(object_path)

        async with self._lock:
            # Remove object file
            try:
                await asyncio.to_thread(object_path.unlink)
            except FileNotFoundError:
                pass  # S3 doesn't error if object doesn't exist

            # Remove metadata file
            try:
                await asyncio.to_thread(meta_path.unlink)
            except FileNotFoundError:
                pass

            # Clean up empty directories
            try:
                await asyncio.to_thread(object_path.parent.rmdir)
            except OSError:
                pass  # Directory not empty or other issue

        return {"ResponseMetadata": {"HTTPStatusCode": 204}}

    async def delete_objects(
        self,
        *,
        Bucket: str,  # noqa: N803
        Delete: Dict[str, List[Dict[str, str]]],  # noqa: N803
    ):
        """Delete multiple objects (batch operation)."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        deleted = []
        errors = []

        for obj in Delete.get("Objects", []):
            key = obj["Key"]
            try:
                await self.delete_object(Bucket=Bucket, Key=key)
                deleted.append({"Key": key})
            except Exception as e:
                errors.append({"Key": key, "Code": "InternalError", "Message": str(e)})

        return {
            "Deleted": deleted,
            "Errors": errors,
        }

    async def copy_object(
        self,
        *,
        Bucket: str,  # noqa: N803
        Key: str,  # noqa: N803
        CopySource: Dict[str, str],  # noqa: N803
    ):
        """Copy object within filesystem."""
        if self._closed:
            raise RuntimeError("Client has been closed")

        source_bucket = CopySource["Bucket"]
        source_key = CopySource["Key"]

        # Read source object
        source_obj = await self.get_object(Bucket=source_bucket, Key=source_key)

        # Write to destination
        result = await self.put_object(
            Bucket=Bucket,
            Key=Key,
            Body=source_obj["Body"],
            ContentType=source_obj["ContentType"],
            Metadata=source_obj["Metadata"],
        )

        return {
            "CopyObjectResult": {
                "ETag": result["ETag"],
                "LastModified": datetime.now(timezone.utc),
            }
        }

    async def close(self):
        """Mark client as closed."""
        self._closed = True

    # ------------------------------------------------------------
    # Utility/debugging methods
    # ------------------------------------------------------------

    async def _debug_get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        if self._closed:
            return {"error": "Client closed"}

        total_objects = 0
        total_bytes = 0

        for item in self._root.rglob("*"):
            if item.is_file() and not item.name.endswith(".meta.json"):
                total_objects += 1
                total_bytes += item.stat().st_size

        return {
            "root_path": str(self._root),
            "total_objects": total_objects,
            "total_bytes": total_bytes,
            "closed": self._closed,
        }

    async def _debug_cleanup_empty_dirs(self):
        """Remove empty directories (cleanup utility)."""
        async with self._lock:
            for item in reversed(sorted(self._root.rglob("*"))):
                if item.is_dir():
                    try:
                        await asyncio.to_thread(item.rmdir)
                    except OSError:
                        pass  # Directory not empty


# ---- public factory -------------------------------------------------------


def factory(root: Optional[Path] = None) -> Callable[[], AsyncContextManager]:
    """
    Create a filesystem client factory.

    Parameters
    ----------
    root : Path, optional
        Root directory for storage. If None, uses $ARTIFACT_FS_ROOT or ./artifacts
    """
    if root is None:
        root = _ROOT
    else:
        root = Path(root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def _ctx():
        client = _FilesystemClient(root)
        try:
            yield client
        finally:
            await client.close()

    return _ctx


# ---- convenience functions ------------------------------------------------


def create_temp_filesystem_factory() -> tuple[Callable[[], AsyncContextManager], Path]:
    """
    Create a factory using a temporary directory.

    Returns
    -------
    tuple
        (factory_function, temp_directory_path)
    """
    import tempfile

    temp_dir = Path(tempfile.mkdtemp(prefix="artifacts_"))
    return factory(temp_dir), temp_dir


async def cleanup_filesystem_store(root: Path):
    """
    Clean up a filesystem store directory.

    Parameters
    ----------
    root : Path
        Directory to clean up
    """
    import shutil

    if root.exists():
        await asyncio.to_thread(shutil.rmtree, root)
