# -*- coding: utf-8 -*-
# chuk_artifacts/presigned.py
"""
Presigned URL operations: download URLs, upload URLs, and upload registration.
Now uses chuk_sessions for session management.
"""

from __future__ import annotations

import uuid
import time
import logging
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .store import ArtifactStore

from .exceptions import (
    ArtifactStoreError,
    ArtifactNotFoundError,
    ArtifactExpiredError,
    ProviderError,
    SessionError,
)
from .models import (
    ArtifactMetadata,
    MultipartUploadInitRequest,
    MultipartUploadCompleteRequest,
)

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 900
_DEFAULT_PRESIGN_EXPIRES = 3600


class PresignedURLOperations:
    """Handles all presigned URL operations."""

    def __init__(self, artifact_store: "ArtifactStore"):
        self.artifact_store = artifact_store

    async def presign(
        self, artifact_id: str, expires: int = _DEFAULT_PRESIGN_EXPIRES
    ) -> str:
        """Generate a presigned URL for artifact download."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()

        try:
            record = await self._get_record(artifact_id)

            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.artifact_store.bucket, "Key": record.key},
                    ExpiresIn=expires,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "Presigned URL generated",
                    extra={
                        "artifact_id": artifact_id,
                        "expires_in": expires,
                        "duration_ms": duration_ms,
                    },
                )

                return url

        except (ArtifactNotFoundError, ArtifactExpiredError):
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Presigned URL generation failed",
                extra={
                    "artifact_id": artifact_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            if "oauth" in str(e).lower() or "credential" in str(e).lower():
                raise NotImplementedError(
                    "This provider cannot generate presigned URLs with the "
                    "current credential type (e.g. OAuth). Use HMAC creds instead."
                ) from e
            else:
                raise ProviderError(f"Presigned URL generation failed: {e}") from e

    async def presign_short(self, artifact_id: str) -> str:
        """Generate a short-lived presigned URL (15 minutes)."""
        return await self.presign(artifact_id, expires=900)

    async def presign_medium(self, artifact_id: str) -> str:
        """Generate a medium-lived presigned URL (1 hour)."""
        return await self.presign(artifact_id, expires=3600)

    async def presign_long(self, artifact_id: str) -> str:
        """Generate a long-lived presigned URL (24 hours)."""
        return await self.presign(artifact_id, expires=86400)

    async def presign_upload(
        self,
        session_id: str | None = None,
        filename: str | None = None,
        mime_type: str = "application/octet-stream",
        expires: int = _DEFAULT_PRESIGN_EXPIRES,
    ) -> tuple[str, str]:
        """Generate a presigned URL for uploading a new artifact."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()

        # Ensure session is allocated using chuk_sessions
        if session_id is None:
            session_id = await self.artifact_store._session_manager.allocate_session()
        else:
            session_id = await self.artifact_store._session_manager.allocate_session(
                session_id=session_id
            )

        # Generate artifact ID and key path
        artifact_id = uuid.uuid4().hex
        key = self.artifact_store.generate_artifact_key(
            session_id, artifact_id, mime_type=mime_type, filename=filename
        )

        try:
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                url = await s3.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self.artifact_store.bucket,
                        "Key": key,
                        "ContentType": mime_type,
                    },
                    ExpiresIn=expires,
                )

                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "Upload presigned URL generated",
                    extra={
                        "artifact_id": artifact_id,
                        "key": key,
                        "mime_type": mime_type,
                        "expires_in": expires,
                        "duration_ms": duration_ms,
                    },
                )

                return url, artifact_id

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Upload presigned URL generation failed",
                extra={
                    "artifact_id": artifact_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            if "oauth" in str(e).lower() or "credential" in str(e).lower():
                raise NotImplementedError(
                    "This provider cannot generate presigned URLs with the "
                    "current credential type (e.g. OAuth). Use HMAC creds instead."
                ) from e
            else:
                raise ProviderError(
                    f"Upload presigned URL generation failed: {e}"
                ) from e

    async def register_uploaded_artifact(
        self,
        artifact_id: str,
        *,
        mime: str,
        summary: str,
        meta: Dict[str, Any] | None = None,
        filename: str | None = None,
        session_id: str | None = None,
        ttl: int = _DEFAULT_TTL,
    ) -> bool:
        """Register metadata for an artifact uploaded via presigned URL."""
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()

        # Ensure session is allocated using chuk_sessions
        if session_id is None:
            session_id = await self.artifact_store._session_manager.allocate_session()
        else:
            session_id = await self.artifact_store._session_manager.allocate_session(
                session_id=session_id
            )

        # Try to get existing metadata first (in case artifact was already registered)
        try:
            existing_metadata = await self.artifact_store.metadata(artifact_id)
            key = existing_metadata.key  # Use existing key
            logger.debug(f"Using existing key for artifact {artifact_id}: {key}")
        except Exception:
            # No existing metadata, construct key from provided info
            key = self.artifact_store.generate_artifact_key(
                session_id, artifact_id, mime_type=mime, filename=filename
            )

        try:
            # Verify the object exists and get its size
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                try:
                    response = await s3.head_object(
                        Bucket=self.artifact_store.bucket, Key=key
                    )
                    file_size = response.get("ContentLength", 0)
                except Exception:
                    logger.warning(
                        f"Artifact {artifact_id} not found in storage at key {key}"
                    )
                    return False

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
                bytes=file_size,
                sha256=None,  # We don't have the hash since we didn't upload it directly
                stored_at=datetime.utcnow().isoformat() + "Z",
                ttl=ttl,
                storage_provider=self.artifact_store._storage_provider_name,
                session_provider=self.artifact_store._session_provider_name,
                owner_id=None,
                uploaded_via_presigned=True,  # Flag to indicate upload method
            )

            # Cache metadata using session provider
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, ttl, record.model_dump_json())

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Artifact metadata registered after presigned upload",
                extra={
                    "artifact_id": artifact_id,
                    "bytes": file_size,
                    "mime": mime,
                    "duration_ms": duration_ms,
                },
            )

            return True

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Artifact metadata registration failed",
                extra={
                    "artifact_id": artifact_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )

            if "session" in str(e).lower() or "redis" in str(e).lower():
                raise SessionError(f"Metadata registration failed: {e}") from e
            else:
                raise ProviderError(f"Metadata registration failed: {e}") from e

    async def presign_upload_and_register(
        self,
        *,
        mime: str,
        summary: str,
        meta: Dict[str, Any] | None = None,
        filename: str | None = None,
        session_id: str | None = None,
        ttl: int = _DEFAULT_TTL,
        expires: int = _DEFAULT_PRESIGN_EXPIRES,
    ) -> tuple[str, str]:
        """Convenience method combining presign_upload and pre-register metadata."""
        # Generate presigned URL
        upload_url, artifact_id = await self.presign_upload(
            session_id=session_id, filename=filename, mime_type=mime, expires=expires
        )

        # Pre-register metadata (with unknown file size)
        await self.register_uploaded_artifact(
            artifact_id,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id=session_id,
            ttl=ttl,
        )

        return upload_url, artifact_id

    async def initiate_multipart_upload(
        self,
        request: MultipartUploadInitRequest,
    ) -> Dict[str, Any]:
        """
        Initiate a multipart upload for large files.

        Returns upload info with upload_id, artifact_id, and key for tracking.
        Client should upload parts using get_part_upload_url(), then call
        complete_multipart_upload() with ETags.

        Minimum part size: 5MB (except last part)
        Maximum parts: 10,000

        Args:
            request: MultipartUploadInitRequest with upload parameters

        Returns:
            Dictionary with upload_id, artifact_id, key, and session_id

        Examples:
            >>> request = MultipartUploadInitRequest(
            ...     filename="video.mp4",
            ...     mime_type="video/mp4",
            ...     user_id="alice",
            ...     scope="user"
            ... )
            >>> result = await presigned.initiate_multipart_upload(request)
            >>> upload_id = result["upload_id"]
        """
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()

        # Validate scope requirements
        if request.scope == "user" and not request.user_id:
            raise ValueError("user_id is required for user-scoped artifacts")

        # Ensure session is allocated
        if request.session_id is None and request.user_id:
            session_id = await self.artifact_store._session_manager.allocate_session(
                user_id=request.user_id
            )
        elif request.session_id is None:
            session_id = await self.artifact_store._session_manager.allocate_session()
        else:
            session_id = await self.artifact_store._session_manager.allocate_session(
                session_id=request.session_id
            )

        # Generate artifact ID and key path
        artifact_id = uuid.uuid4().hex

        # Use scope-based key generation with file extensions
        from .grid import artifact_key

        key = artifact_key(
            sandbox_id=self.artifact_store.sandbox_id,
            session_id=session_id,
            artifact_id=artifact_id,
            scope=request.scope,
            owner_id=request.user_id,
            mime_type=request.mime_type,
            filename=request.filename,
        )

        try:
            # Initiate multipart upload with storage provider
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                # Check if provider supports native multipart
                if hasattr(s3, "create_multipart_upload"):
                    response = await s3.create_multipart_upload(
                        Bucket=self.artifact_store.bucket,
                        Key=key,
                        ContentType=request.mime_type,
                    )
                    upload_id = response["UploadId"]
                else:
                    # Fallback: generate pseudo upload_id for providers without multipart
                    upload_id = f"upload-{uuid.uuid4().hex}"

            # Store multipart upload metadata (temporary, until completion)
            multipart_meta = {
                "upload_id": upload_id,
                "artifact_id": artifact_id,
                "key": key,
                "session_id": session_id,
                "filename": request.filename,
                "mime_type": request.mime_type,
                "user_id": request.user_id,
                "scope": request.scope.value
                if hasattr(request.scope, "value")
                else request.scope,  # Convert enum to string
                "ttl": request.ttl,
                "meta": request.meta or {},
                "status": "uploading",
                "initiated_at": datetime.utcnow().isoformat() + "Z",
            }

            # Store in session provider with short TTL (24 hours for upload window)
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(
                    f"multipart:{upload_id}",
                    86400,  # 24 hour window to complete upload
                    str(multipart_meta),  # Simple dict storage
                )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Multipart upload initiated",
                extra={
                    "upload_id": upload_id,
                    "artifact_id": artifact_id,
                    "key": key,
                    "filename": request.filename,
                    "mime_type": request.mime_type,
                    "duration_ms": duration_ms,
                },
            )

            return {
                "upload_id": upload_id,
                "artifact_id": artifact_id,
                "key": key,
                "session_id": session_id,
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Multipart upload initiation failed",
                extra={
                    "artifact_id": artifact_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )
            raise ProviderError(f"Multipart upload initiation failed: {e}") from e

    async def get_part_upload_url(
        self,
        upload_id: str,
        part_number: int,
        expires: int = _DEFAULT_PRESIGN_EXPIRES,
    ) -> str:
        """
        Generate presigned URL for uploading a specific part.

        Args:
            upload_id: Upload ID from initiate_multipart_upload()
            part_number: Part number (1-10000)
            expires: URL expiration in seconds

        Returns:
            Presigned PUT URL for the part

        Raises:
            ArtifactNotFoundError: If upload_id doesn't exist
            ValueError: If part_number is invalid
        """
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        if part_number < 1 or part_number > 10000:
            raise ValueError("Part number must be between 1 and 10,000")

        start_time = time.time()

        try:
            # Get multipart upload metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                raw = await session.get(f"multipart:{upload_id}")

            if raw is None:
                raise ArtifactNotFoundError(f"Multipart upload {upload_id} not found")

            import ast

            multipart_meta = ast.literal_eval(raw)
            key = multipart_meta["key"]

            # Generate presigned URL for part
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                if hasattr(s3, "generate_presigned_url"):
                    # S3-style multipart part upload
                    url = await s3.generate_presigned_url(
                        "upload_part",
                        Params={
                            "Bucket": self.artifact_store.bucket,
                            "Key": key,
                            "UploadId": upload_id,
                            "PartNumber": part_number,
                        },
                        ExpiresIn=expires,
                    )
                else:
                    # Fallback: generate regular presigned PUT URL with part suffix
                    part_key = f"{key}.part{part_number}"
                    url = await s3.generate_presigned_url(
                        "put_object",
                        Params={
                            "Bucket": self.artifact_store.bucket,
                            "Key": part_key,
                            "ContentType": multipart_meta.get(
                                "mime_type", "application/octet-stream"
                            ),
                        },
                        ExpiresIn=expires,
                    )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Part upload URL generated",
                extra={
                    "upload_id": upload_id,
                    "part_number": part_number,
                    "expires_in": expires,
                    "duration_ms": duration_ms,
                },
            )

            return url

        except ArtifactNotFoundError:
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Part upload URL generation failed",
                extra={
                    "upload_id": upload_id,
                    "part_number": part_number,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )
            raise ProviderError(f"Part upload URL generation failed: {e}") from e

    async def complete_multipart_upload(
        self,
        request: MultipartUploadCompleteRequest,
    ) -> str:
        """
        Complete a multipart upload and register the artifact.

        Args:
            request: MultipartUploadCompleteRequest with upload_id, parts, and summary

        Returns:
            artifact_id of the completed upload

        Raises:
            ArtifactNotFoundError: If upload_id doesn't exist
            ValueError: If parts list is invalid

        Examples:
            >>> request = MultipartUploadCompleteRequest(
            ...     upload_id="upload-abc123",
            ...     parts=[
            ...         MultipartUploadPart(PartNumber=1, ETag="etag1"),
            ...         MultipartUploadPart(PartNumber=2, ETag="etag2"),
            ...     ],
            ...     summary="Large video upload"
            ... )
            >>> artifact_id = await presigned.complete_multipart_upload(request)
        """
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        if not request.parts:
            raise ValueError("Parts list cannot be empty")

        start_time = time.time()

        try:
            # Get multipart upload metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                raw = await session.get(f"multipart:{request.upload_id}")

            if raw is None:
                raise ArtifactNotFoundError(
                    f"Multipart upload {request.upload_id} not found"
                )

            import ast

            multipart_meta = ast.literal_eval(raw)

            artifact_id = multipart_meta["artifact_id"]
            key = multipart_meta["key"]
            session_id = multipart_meta["session_id"]

            # Convert Pydantic parts to dict format for S3
            parts_dict = [
                {"PartNumber": part.PartNumber, "ETag": part.ETag}
                for part in request.parts
            ]

            # Complete multipart upload with storage provider
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                if hasattr(s3, "complete_multipart_upload"):
                    # Native S3 multipart completion
                    await s3.complete_multipart_upload(
                        Bucket=self.artifact_store.bucket,
                        Key=key,
                        UploadId=request.upload_id,
                        MultipartUpload={"Parts": parts_dict},
                    )
                else:
                    # Fallback: combine part files
                    # This is a simplified implementation for providers without multipart
                    all_data = b""
                    for part in sorted(request.parts, key=lambda p: p.PartNumber):
                        part_key = f"{key}.part{part.PartNumber}"
                        try:
                            part_response = await s3.get_object(
                                Bucket=self.artifact_store.bucket,
                                Key=part_key,
                            )
                            part_data = part_response.get("Body", b"")
                            if hasattr(part_data, "read"):
                                part_data = await part_data.read()
                            all_data += part_data
                        except Exception:
                            pass  # Skip missing parts

                    # Write combined data
                    await s3.put_object(
                        Bucket=self.artifact_store.bucket,
                        Key=key,
                        Body=all_data,
                        ContentType=multipart_meta.get(
                            "mime_type", "application/octet-stream"
                        ),
                        Metadata={},
                    )

                    # Clean up part files
                    for part in request.parts:
                        part_key = f"{key}.part{part.PartNumber}"
                        try:
                            await s3.delete_object(
                                Bucket=self.artifact_store.bucket,
                                Key=part_key,
                            )
                        except Exception:
                            pass  # Ignore cleanup errors

                # Get final object size
                try:
                    head_response = await s3.head_object(
                        Bucket=self.artifact_store.bucket,
                        Key=key,
                    )
                    file_size = head_response.get("ContentLength", 0)
                except Exception:
                    file_size = 0

            # Register artifact metadata
            record = ArtifactMetadata(
                artifact_id=artifact_id,
                session_id=session_id,
                sandbox_id=self.artifact_store.sandbox_id,
                key=key,
                mime=multipart_meta.get("mime_type", "application/octet-stream"),
                summary=request.summary,
                meta=multipart_meta.get("meta", {}),
                filename=multipart_meta.get("filename"),
                bytes=file_size,
                sha256=None,  # Don't have hash for multipart uploads
                stored_at=datetime.utcnow().isoformat() + "Z",
                ttl=multipart_meta.get("ttl", _DEFAULT_TTL),
                storage_provider=self.artifact_store._storage_provider_name,
                session_provider=self.artifact_store._session_provider_name,
                scope=multipart_meta.get("scope", "session"),
                owner_id=multipart_meta.get("user_id"),
                uploaded_via_presigned=True,
            )

            # Cache metadata
            session_ctx_mgr2 = self.artifact_store._session_factory()
            async with session_ctx_mgr2 as session:
                await session.setex(artifact_id, record.ttl, record.model_dump_json())

                # Clean up multipart metadata
                await session.delete(f"multipart:{request.upload_id}")

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Multipart upload completed",
                extra={
                    "upload_id": request.upload_id,
                    "artifact_id": artifact_id,
                    "bytes": file_size,
                    "parts_count": len(request.parts),
                    "duration_ms": duration_ms,
                },
            )

            return artifact_id

        except ArtifactNotFoundError:
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Multipart upload completion failed",
                extra={
                    "upload_id": request.upload_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )
            raise ProviderError(f"Multipart upload completion failed: {e}") from e

    async def abort_multipart_upload(self, upload_id: str) -> bool:
        """
        Abort an incomplete multipart upload and clean up resources.

        Args:
            upload_id: Upload ID from initiate_multipart_upload()

        Returns:
            True if aborted successfully
        """
        if self.artifact_store._closed:
            raise ArtifactStoreError("Store is closed")

        start_time = time.time()

        try:
            # Get multipart upload metadata
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                raw = await session.get(f"multipart:{upload_id}")

            if raw is None:
                # Already cleaned up or doesn't exist
                return True

            import ast

            multipart_meta = ast.literal_eval(raw)
            key = multipart_meta["key"]

            # Abort multipart upload with storage provider
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                if hasattr(s3, "abort_multipart_upload"):
                    try:
                        await s3.abort_multipart_upload(
                            Bucket=self.artifact_store.bucket,
                            Key=key,
                            UploadId=upload_id,
                        )
                    except Exception:
                        pass  # Ignore errors if already aborted

            # Clean up metadata
            session_ctx_mgr2 = self.artifact_store._session_factory()
            async with session_ctx_mgr2 as session:
                await session.delete(f"multipart:{upload_id}")

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Multipart upload aborted",
                extra={
                    "upload_id": upload_id,
                    "duration_ms": duration_ms,
                },
            )

            return True

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Multipart upload abort failed",
                extra={
                    "upload_id": upload_id,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )
            return False

    async def _get_record(self, artifact_id: str) -> ArtifactMetadata:
        """Get artifact metadata record."""
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
