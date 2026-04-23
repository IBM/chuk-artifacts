# -*- coding: utf-8 -*-
# chuk_artifacts/admin.py
"""
Administrative and debugging operations.
Now includes chuk_sessions integration.
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .store import ArtifactStore

from .types import (
    ValidationResponse,
    ProviderStatus,
    OperationStatus,
)

logger = logging.getLogger(__name__)


class AdminOperations:
    """Handles administrative and debugging operations."""

    def __init__(self, artifact_store: "ArtifactStore") -> None:
        self.artifact_store = artifact_store
        self.store = artifact_store

    async def validate_configuration(self) -> ValidationResponse:
        """Validate store configuration and connectivity."""
        # Test session provider
        session_status = OperationStatus.UNKNOWN
        session_message = None
        try:
            session_ctx_mgr = self.artifact_store._session_factory()
            async with session_ctx_mgr as session:
                # Test basic operations
                test_key = f"test_{uuid.uuid4().hex}"
                await session.setex(test_key, 10, "test_value")
                value = await session.get(test_key)

                if value == "test_value":
                    session_status = OperationStatus.OK  # Use OK for backward compat
                else:
                    session_status = (
                        OperationStatus.ERROR
                    )  # Use ERROR for backward compat
                    session_message = "Session store test failed"
        except (
            Exception
        ) as e:  # intentional: catch any connectivity failure during health check
            session_status = OperationStatus.ERROR
            session_message = str(e)

        # Test storage provider
        storage_status = OperationStatus.UNKNOWN
        storage_message = None
        storage_details = {}
        try:
            storage_ctx_mgr = self.artifact_store._s3_factory()
            async with storage_ctx_mgr as s3:
                await s3.head_bucket(Bucket=self.artifact_store.bucket)
            storage_status = OperationStatus.OK  # Use OK for backward compat
            storage_details["bucket"] = self.artifact_store.bucket
        except (
            Exception
        ) as e:  # intentional: catch any connectivity failure during health check
            storage_status = OperationStatus.ERROR
            storage_message = str(e)

        # Test session manager (chuk_sessions) - backward compat
        session_manager_status = {}
        try:
            # Try to allocate a test session
            test_session = await self.artifact_store._session_manager.allocate_session(
                user_id="test_admin_user"
            )
            # Validate it
            is_valid = await self.artifact_store._session_manager.validate_session(
                test_session
            )
            # Clean up
            await self.artifact_store._session_manager.delete_session(test_session)

            if is_valid:
                session_manager_status = {
                    "status": "ok",
                    "sandbox_id": self.artifact_store.sandbox_id,
                    "test_session": test_session,
                }
            else:
                session_manager_status = {
                    "status": "error",
                    "message": "Session validation failed",
                }
        except (
            Exception
        ) as e:  # intentional: catch any connectivity failure during health check
            session_manager_status = {"status": "error", "message": str(e)}

        # Determine overall status
        if (
            session_status == OperationStatus.OK
            and storage_status == OperationStatus.OK
        ):
            overall = OperationStatus.SUCCESS
        elif (
            session_status == OperationStatus.ERROR
            or storage_status == OperationStatus.ERROR
        ):
            overall = OperationStatus.ERROR
        else:
            overall = OperationStatus.UNKNOWN

        return ValidationResponse(
            storage=ProviderStatus(
                status=storage_status,
                provider=self.artifact_store._storage_provider_name,
                message=storage_message,
                details=storage_details,
            ),
            session=ProviderStatus(
                status=session_status,
                provider=self.artifact_store._session_provider_name,
                message=session_message,
            ),
            overall=overall,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            session_manager=session_manager_status,
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        base_stats = {
            "storage_provider": self.artifact_store._storage_provider_name,
            "session_provider": self.artifact_store._session_provider_name,
            "bucket": self.artifact_store.bucket,
            "max_retries": self.artifact_store.max_retries,
            "closed": self.artifact_store._closed,
            "sandbox_id": self.artifact_store.sandbox_id,
            "session_ttl_hours": self.artifact_store.session_ttl_hours,
        }

        # Add session manager stats from chuk_sessions
        try:
            session_stats = self.artifact_store._session_manager.get_cache_stats()
            base_stats["session_manager"] = session_stats
        except Exception as e:
            base_stats["session_manager"] = {"error": str(e), "status": "unavailable"}

        return base_stats

    async def cleanup_all_expired(self) -> Dict[str, Any]:
        """Clean up all expired resources."""
        results: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }

        # Clean up expired sessions using chuk_sessions
        try:
            expired_sessions = (
                await self.artifact_store._session_manager.cleanup_expired_sessions()
            )
            results["expired_sessions_cleaned"] = expired_sessions
        except Exception as e:
            results["session_cleanup_error"] = str(e)
            results["expired_sessions_cleaned"] = 0

        # Artifact metadata TTLs are enforced by the session provider (Redis/memory setex),
        # so expired entries are evicted automatically. Blob objects in S3/filesystem
        # should be managed via provider-level lifecycle policies (e.g., S3 object expiry).
        results["expired_artifacts_cleaned"] = 0

        return results

    async def get_sandbox_info(self) -> Dict[str, Any]:
        """Get information about the current sandbox."""
        return {
            "sandbox_id": self.artifact_store.sandbox_id,
            "session_prefix_pattern": self.artifact_store.get_session_prefix_pattern(),
            "grid_architecture": {
                "enabled": True,
                "pattern": "grid/{sandbox_id}/{session_id}/{artifact_id}",
                "mandatory_sessions": True,
                "federation_ready": True,
            },
        }
