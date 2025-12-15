# -*- coding: utf-8 -*-
# chuk_artifacts/metadata.py
"""
Clean metadata operations for grid architecture.
Now uses chuk_sessions for session management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .store import ArtifactStore

from .exceptions import ProviderError, SessionError, ArtifactNotFoundError
from .models import ArtifactMetadata

logger = logging.getLogger(__name__)


class MetadataOperations:
    """Clean metadata operations for grid architecture using chuk_sessions."""

    def __init__(self, artifact_store: "ArtifactStore"):
        self.artifact_store = artifact_store

    async def get_metadata(self, artifact_id: str) -> ArtifactMetadata:
        """Get artifact metadata."""
        return await self._get_record(artifact_id)

    async def exists(self, artifact_id: str) -> bool:
        """Check if artifact exists."""
        try:
            await self._get_record(artifact_id)
            return True
        except Exception:
            return False

    async def delete(self, artifact_id: str) -> bool:
        """Delete artifact and metadata."""
        try:
            record = await self._get_record(artifact_id)

            # Delete from storage
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                await s3.delete_object(
                    Bucket=self.artifact_store.bucket, Key=record.key
                )

            # Delete metadata from session provider
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                # Fix: hasattr is not async, don't await it
                if hasattr(session, "delete"):
                    await session.delete(artifact_id)

            logger.info(f"Deleted artifact: {artifact_id}")
            return True

        except Exception as e:
            logger.error(f"Delete failed for {artifact_id}: {e}")
            return False

    async def list_by_session(
        self, session_id: str, limit: int = 100
    ) -> List[ArtifactMetadata]:
        """List artifacts in a session using grid prefix from chuk_sessions."""
        try:
            artifacts = []
            # Use the session manager's canonical prefix instead of building our own
            prefix = self.artifact_store.get_canonical_prefix(session_id)

            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                if hasattr(s3, "list_objects_v2"):
                    response = await s3.list_objects_v2(
                        Bucket=self.artifact_store.bucket, Prefix=prefix, MaxKeys=limit
                    )

                    for obj in response.get("Contents", []):
                        key = obj["Key"]
                        # Parse the grid key using chuk_sessions
                        parsed = self.artifact_store.parse_grid_key(key)
                        if parsed:
                            # Strip file extension from artifact_id (metadata is stored by UUID only)
                            import os

                            artifact_id_with_ext = parsed.artifact_id
                            artifact_id = os.path.splitext(artifact_id_with_ext)[0]
                            try:
                                record = await self._get_record(artifact_id)
                                artifacts.append(record)
                            except Exception:
                                continue  # Skip if metadata missing

                    return artifacts[:limit]

            logger.warning("Storage provider doesn't support listing")
            return []

        except Exception as e:
            logger.error(f"Session listing failed for {session_id}: {e}")
            return []

    async def list_by_prefix(
        self, session_id: str, prefix: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List artifacts with filename prefix filtering."""
        try:
            all_files = await self.list_by_session(session_id, limit * 2)

            if not prefix:
                return all_files[:limit]

            # Filter by filename prefix
            filtered = []
            for file_meta in all_files:
                filename = file_meta.get("filename", "")
                if filename.startswith(prefix):
                    filtered.append(file_meta)
                    if len(filtered) >= limit:
                        break

            return filtered

        except Exception as e:
            logger.error(f"Prefix listing failed for session {session_id}: {e}")
            return []

    async def update_metadata(
        self,
        artifact_id: str,
        *,
        summary: str = None,
        meta: Dict[str, Any] = None,
        merge: bool = True,
        **kwargs,
    ) -> ArtifactMetadata:
        """Update artifact metadata."""
        try:
            # Get current record
            record = await self._get_record(artifact_id)

            # Update fields
            if summary is not None:
                record.summary = summary

            if meta is not None:
                if merge and record.meta:
                    record.meta.update(meta)
                else:
                    record.meta = meta

            # Update any other fields
            for key, value in kwargs.items():
                if key not in ["summary", "meta"] and value is not None:
                    setattr(record, key, value)

            # Store updated record using session provider
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, record.ttl, record.model_dump_json())

            return record

        except Exception as e:
            logger.error(f"Metadata update failed for {artifact_id}: {e}")
            raise ProviderError(f"Metadata update failed: {e}") from e

    async def extend_ttl(
        self, artifact_id: str, additional_seconds: int
    ) -> ArtifactMetadata:
        """Extend artifact TTL."""
        try:
            # Get current record
            record = await self._get_record(artifact_id)

            # Update TTL
            new_ttl = record.ttl + additional_seconds
            record.ttl = new_ttl

            # Store updated record with new TTL using session provider
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                await session.setex(artifact_id, new_ttl, record.model_dump_json())

            return record

        except Exception as e:
            logger.error(f"TTL extension failed for {artifact_id}: {e}")
            raise ProviderError(f"TTL extension failed: {e}") from e

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
