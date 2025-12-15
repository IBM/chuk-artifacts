# -*- coding: utf-8 -*-
# chuk_artifacts/core.py
"""
Clean core storage operations - grid architecture only.
Now uses chuk_sessions for session management.
"""

from __future__ import annotations

import uuid
import hashlib
import time
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, TYPE_CHECKING, AsyncIterator, Callable

if TYPE_CHECKING:
    from .store import ArtifactStore

from .exceptions import (
    ArtifactStoreError,
    ProviderError,
    SessionError,
    ArtifactNotFoundError,
)
from .models import ArtifactMetadata

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 900


class CoreStorageOperations:
    """Clean core storage operations with grid architecture."""

    def __init__(self, artifact_store: "ArtifactStore"):
        self.artifact_store = artifact_store

    async def store(
        self,
        data: bytes,
        *,
        mime: str,
        summary: str,
        meta: Dict[str, Any] | None = None,
        filename: str | None = None,
        session_id: str,  # Required - no more optional sessions
        ttl: int = _DEFAULT_TTL,
        scope: str = "session",  # "session", "user", or "sandbox"
        owner_id: str | None = None,  # user_id for user-scoped artifacts
    ) -> str:
        """Store artifact with grid key generation and scope support."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()
        artifact_id = uuid.uuid4().hex

        # Generate grid key based on scope (uses new format by default)
        from .grid import artifact_key

        key = artifact_key(
            sandbox_id=self.artifact_store.sandbox_id,
            session_id=session_id,
            artifact_id=artifact_id,
            scope=scope,
            owner_id=owner_id,
            mime_type=mime,
            filename=filename,
            # use_legacy_session_format defaults to False (new format)
            # parse() handles reading both legacy and new formats
        )

        try:
            # Store in object storage
            await self._store_with_retry(data, key, mime, filename, session_id)

            # Build metadata record using Pydantic model
            record = ArtifactMetadata(
                artifact_id=artifact_id,
                session_id=session_id,
                sandbox_id=self.artifact_store.sandbox_id,
                key=key,
                mime=mime,
                summary=summary,
                meta=meta or {},
                filename=filename,
                bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                stored_at=datetime.utcnow().isoformat() + "Z",
                ttl=ttl,
                storage_provider=self.artifact_store._storage_provider_name,
                session_provider=self.artifact_store._session_provider_name,
                scope=scope,
                owner_id=owner_id,
            )

            # Store metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, ttl, record.model_dump_json())

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Artifact stored",
                extra={
                    "artifact_id": artifact_id,
                    "session_id": session_id,
                    "key": key,
                    "bytes": len(data),
                    "duration_ms": duration_ms,
                },
            )

            return artifact_id

        except Exception as e:
            logger.error(f"Storage failed for {artifact_id}: {e}")
            if "session" in str(e).lower():
                raise SessionError(f"Metadata storage failed: {e}") from e
            else:
                raise ProviderError(f"Storage failed: {e}") from e

    async def update_file(
        self,
        artifact_id: str,
        new_data: Optional[bytes] = None,
        *,
        mime: Optional[str] = None,
        summary: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Update an artifact's content, metadata, filename, summary, or mime type.

        Parameters
        ----------
        artifact_id : str
            ID of the artifact to update
        new_data : bytes, optional
            New data to overwrite the existing artifact
        mime : str, optional
            New MIME type
        summary : str, optional
            New summary
        meta : dict, optional
            Updated metadata
        filename : str, optional
            New filename
        ttl : int, optional
            New TTL

        Returns
        -------
        bool
            True if update was successful
        """
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        if not any(
            [
                new_data is not None,
                meta is not None,
                filename is not None,
                summary is not None,
                mime is not None,
                ttl is not None,
            ]
        ):
            raise ValueError("At least one update parameter must be provided.")

        try:
            record = await self._get_record(artifact_id)
            key = record.key
            session_id = record.session_id

            # Update data if provided
            if new_data is not None:
                # Overwrite in object storage
                await self._store_with_retry(
                    new_data,
                    key,
                    mime or record.mime,
                    filename or record.filename,
                    session_id,
                )

                # Update size and hash in metadata
                record.bytes = len(new_data)
                record.sha256 = hashlib.sha256(new_data).hexdigest()

            # Update metadata fields
            if mime is not None:
                record.mime = mime
            if summary is not None:
                record.summary = summary
            if filename is not None:
                record.filename = filename
            if meta is not None:
                record.meta = meta
            if ttl is not None:
                record.ttl = ttl

            # Add update timestamp
            record.updated_at = datetime.utcnow().isoformat() + "Z"

            # Store updated metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, record.ttl, record.model_dump_json())

            logger.info(
                "Artifact updated successfully", extra={"artifact_id": artifact_id}
            )
            return True

        except Exception as e:
            logger.error(f"Update failed for artifact {artifact_id}: {e}")
            raise ProviderError(f"Artifact update failed: {e}") from e

    async def retrieve(self, artifact_id: str) -> bytes:
        """Retrieve artifact data."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        try:
            record = await self._get_record(artifact_id)

            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                response = await s3.get_object(
                    Bucket=self.artifact_store.bucket, Key=record.key
                )

                # Handle different response formats
                if hasattr(response["Body"], "read"):
                    data = await response["Body"].read()
                elif isinstance(response["Body"], bytes):
                    data = response["Body"]
                else:
                    data = bytes(response["Body"])

                # Verify integrity
                if record.sha256:
                    computed = hashlib.sha256(data).hexdigest()
                    if computed != record.sha256:
                        raise ProviderError(
                            f"SHA256 mismatch: {record.sha256} != {computed}"
                        )

                return data

        except Exception as e:
            logger.error(f"Retrieval failed for {artifact_id}: {e}")
            raise ProviderError(f"Retrieval failed: {e}") from e

    async def stream_upload(
        self,
        data_stream: AsyncIterator[bytes],
        *,
        mime: str,
        summary: str,
        meta: Dict[str, Any] | None = None,
        filename: str | None = None,
        session_id: str,
        ttl: int = _DEFAULT_TTL,
        scope: str = "session",
        owner_id: str | None = None,
        content_length: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> str:
        """Store artifact using streaming upload with progress callbacks."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()
        artifact_id = uuid.uuid4().hex

        # Generate grid key based on scope
        from .grid import artifact_key

        key = artifact_key(
            sandbox_id=self.artifact_store.sandbox_id,
            session_id=session_id,
            artifact_id=artifact_id,
            scope=scope,
            owner_id=owner_id,
            mime_type=mime,
            filename=filename,
        )

        try:
            # Store using streaming with retry
            sha256_hash, bytes_written = await self._stream_upload_with_retry(
                data_stream,
                key,
                mime,
                filename,
                session_id,
                content_length,
                progress_callback,
            )

            # Build metadata record
            record = ArtifactMetadata(
                artifact_id=artifact_id,
                session_id=session_id,
                sandbox_id=self.artifact_store.sandbox_id,
                key=key,
                mime=mime,
                summary=summary,
                meta=meta or {},
                filename=filename,
                bytes=bytes_written,
                sha256=sha256_hash,
                stored_at=datetime.utcnow().isoformat() + "Z",
                ttl=ttl,
                storage_provider=self.artifact_store._storage_provider_name,
                session_provider=self.artifact_store._session_provider_name,
                scope=scope,
                owner_id=owner_id,
            )

            # Store metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, ttl, record.model_dump_json())

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Artifact streamed and stored",
                extra={
                    "artifact_id": artifact_id,
                    "session_id": session_id,
                    "key": key,
                    "bytes": bytes_written,
                    "duration_ms": duration_ms,
                },
            )

            return artifact_id

        except Exception as e:
            logger.error(f"Streaming storage failed for {artifact_id}: {e}")
            if "session" in str(e).lower():
                raise SessionError(f"Metadata storage failed: {e}") from e
            else:
                raise ProviderError(f"Streaming storage failed: {e}") from e

    async def stream_download(
        self,
        artifact_id: str,
        *,
        chunk_size: int = 65536,  # 64KB default
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> AsyncIterator[bytes]:
        """Stream download artifact data with progress callbacks."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        try:
            record = await self._get_record(artifact_id)

            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                # Check if provider supports streaming
                if hasattr(s3, "get_object_stream"):
                    # Use native streaming
                    sha256_hasher = hashlib.sha256()
                    async for chunk in s3.get_object_stream(
                        Bucket=self.artifact_store.bucket,
                        Key=record.key,
                        ChunkSize=chunk_size,
                        ProgressCallback=progress_callback,
                    ):
                        sha256_hasher.update(chunk)
                        yield chunk

                    # Verify integrity after streaming
                    if record.sha256:
                        computed = sha256_hasher.hexdigest()
                        if computed != record.sha256:
                            raise ProviderError(
                                f"SHA256 mismatch: {record.sha256} != {computed}"
                            )
                else:
                    # Fallback: read entire file and chunk it
                    response = await s3.get_object(
                        Bucket=self.artifact_store.bucket, Key=record.key
                    )

                    if hasattr(response["Body"], "read"):
                        data = await response["Body"].read()
                    elif isinstance(response["Body"], bytes):
                        data = response["Body"]
                    else:
                        data = bytes(response["Body"])

                    # Verify integrity
                    if record.sha256:
                        computed = hashlib.sha256(data).hexdigest()
                        if computed != record.sha256:
                            raise ProviderError(
                                f"SHA256 mismatch: {record.sha256} != {computed}"
                            )

                    # Chunk and yield with progress
                    total_size = len(data)
                    bytes_sent = 0
                    for i in range(0, total_size, chunk_size):
                        chunk = data[i : i + chunk_size]
                        bytes_sent += len(chunk)
                        if progress_callback:
                            progress_callback(bytes_sent, total_size)
                        yield chunk

        except Exception as e:
            logger.error(f"Streaming retrieval failed for {artifact_id}: {e}")
            raise ProviderError(f"Streaming retrieval failed: {e}") from e

    async def _stream_upload_with_retry(
        self,
        data_stream: AsyncIterator[bytes],
        key: str,
        mime: str,
        filename: str,
        session_id: str,
        content_length: Optional[int],
        progress_callback: Optional[Callable[[int, Optional[int]], None]],
    ) -> tuple[str, int]:
        """Stream upload with retry logic - returns (sha256, bytes_written)."""
        last_exception = None

        for attempt in range(self.artifact_store.max_retries):
            try:
                storage_ctx_mgr = self.artifact_store._s3_factory()
                async with storage_ctx_mgr as s3:
                    # Check if provider supports streaming
                    if hasattr(s3, "put_object_stream"):
                        # Use native streaming
                        sha256_hasher = hashlib.sha256()

                        # Create a wrapper to compute hash while streaming
                        async def hash_wrapper():
                            async for chunk in data_stream:
                                sha256_hasher.update(chunk)
                                yield chunk

                        result = await s3.put_object_stream(
                            Bucket=self.artifact_store.bucket,
                            Key=key,
                            Body=hash_wrapper(),
                            ContentType=mime,
                            Metadata={
                                "filename": filename or "",
                                "session_id": session_id,
                                "sandbox_id": self.artifact_store.sandbox_id,
                            },
                            ContentLength=content_length,
                            ProgressCallback=progress_callback,
                        )

                        bytes_written = result.get("ContentLength", 0)
                        return sha256_hasher.hexdigest(), bytes_written
                    else:
                        # Fallback: collect chunks and use regular put_object
                        chunks = []
                        sha256_hasher = hashlib.sha256()
                        bytes_written = 0

                        async for chunk in data_stream:
                            chunks.append(chunk)
                            sha256_hasher.update(chunk)
                            bytes_written += len(chunk)
                            if progress_callback:
                                progress_callback(bytes_written, content_length)

                        data = b"".join(chunks)
                        await s3.put_object(
                            Bucket=self.artifact_store.bucket,
                            Key=key,
                            Body=data,
                            ContentType=mime,
                            Metadata={
                                "filename": filename or "",
                                "session_id": session_id,
                                "sandbox_id": self.artifact_store.sandbox_id,
                            },
                        )

                        return sha256_hasher.hexdigest(), bytes_written

            except Exception as e:
                last_exception = e
                if attempt < self.artifact_store.max_retries - 1:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        raise last_exception

    async def _store_with_retry(
        self, data: bytes, key: str, mime: str, filename: str, session_id: str
    ):
        """Store with retry logic."""
        last_exception = None

        for attempt in range(self.artifact_store.max_retries):
            try:
                storage_ctx_mgr = self.artifact_store._s3_factory()
                async with storage_ctx_mgr as s3:
                    await s3.put_object(
                        Bucket=self.artifact_store.bucket,
                        Key=key,
                        Body=data,
                        ContentType=mime,
                        Metadata={
                            "filename": filename or "",
                            "session_id": session_id,
                            "sandbox_id": self.artifact_store.sandbox_id,
                        },
                    )
                return  # Success

            except Exception as e:
                last_exception = e
                if attempt < self.artifact_store.max_retries - 1:
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)

        raise last_exception

    async def _get_record(self, artifact_id: str) -> ArtifactMetadata:
        """Get artifact metadata record from session provider."""
        try:
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                raw = await session.get(artifact_id)
        except Exception as e:
            raise SessionError(f"Session error for {artifact_id}: {e}") from e

        if raw is None:
            raise ArtifactNotFoundError(f"Artifact {artifact_id} not found")

        try:
            return ArtifactMetadata.model_validate_json(raw)
        except Exception as e:
            raise ProviderError(f"Corrupted metadata for {artifact_id}") from e
