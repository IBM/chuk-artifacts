# -*- coding: utf-8 -*-
# chuk_artifacts/store.py
"""
Clean ArtifactStore with mandatory sessions and grid architecture.

Grid Architecture:
- Mandatory session allocation (no anonymous artifacts)
- Grid paths: grid/{sandbox_id}/{session_id}/{artifact_id}
- Clean, focused implementation
- Now uses chuk_sessions for session management
"""

from __future__ import annotations

import os
import logging
import uuid
from datetime import datetime
from typing import (
    Any,
    Dict,
    List,
    Callable,
    AsyncContextManager,
    Optional,
    Union,
    AsyncIterator,
)
from importlib.util import find_spec
from chuk_sessions.session_manager import SessionManager
from .grid import canonical_prefix, artifact_key, parse
from .models import (
    ArtifactMetadata,
    GridKeyComponents,
    StreamUploadRequest,
    StreamDownloadRequest,
    MultipartUploadInitRequest,
    MultipartUploadCompleteRequest,
)
from .types import (
    StorageScope,
    DEFAULT_TTL,
    DEFAULT_PRESIGN_EXPIRES,
    SessionInfo,
    SandboxInfo,
    ValidationResponse,
    StatsResponse,
    SessionStats,
    StorageStats,
)

# Check for required dependencies
if not find_spec("aioboto3"):
    raise ImportError(
        "Required dependency missing: aioboto3. Install with: pip install aioboto3"
    )

# Auto-load .env files if python-dotenv is available
try:
    from dotenv import load_dotenv

    load_dotenv()
    logger = logging.getLogger(__name__)
    logger.debug("Loaded environment variables from .env file")
except ImportError:
    logger = logging.getLogger(__name__)
    logger.debug("python-dotenv not available, skipping .env file loading")

# Import exceptions
from .exceptions import ArtifactStoreError, ProviderError

# Import chuk_sessions instead of local session manager

# Configure structured logging
logger = logging.getLogger(__name__)

# Legacy constants for backward compatibility
_DEFAULT_TTL = DEFAULT_TTL  # seconds (15 minutes for metadata)
_DEFAULT_PRESIGN_EXPIRES = (
    DEFAULT_PRESIGN_EXPIRES  # seconds (1 hour for presigned URLs)
)


# ─────────────────────────────────────────────────────────────────────
# Default factories
# ─────────────────────────────────────────────────────────────────────
def _default_storage_factory() -> Callable[[], AsyncContextManager]:
    """Return a zero-arg callable that yields an async ctx-mgr S3 client."""
    from .provider_factory import factory_for_env

    return factory_for_env()  # Defaults to memory provider


def _default_session_factory() -> Callable[[], AsyncContextManager]:
    """Return a zero-arg callable that yields an async ctx-mgr session store."""
    from chuk_sessions.provider_factory import factory_for_env

    return factory_for_env()  # Defaults to memory provider


# ─────────────────────────────────────────────────────────────────────
class ArtifactStore:
    """
    Clean ArtifactStore with grid architecture and mandatory sessions.

    Simple rules:
    - Always allocate a session (no anonymous artifacts)
    - Grid paths only: grid/{sandbox_id}/{session_id}/{artifact_id}
    - Clean, focused implementation
    - Uses chuk_sessions for session management
    """

    def __init__(
        self,
        *,
        bucket: Optional[str] = None,
        storage_provider: Optional[str] = None,
        session_provider: Optional[str] = None,
        sandbox_id: Optional[str] = None,
        session_ttl_hours: int = 24,
        max_retries: int = 3,
    ):
        # Configuration
        self.bucket = bucket or os.getenv("ARTIFACT_BUCKET", "artifacts")
        self.sandbox_id = sandbox_id or self._detect_sandbox_id()
        self.session_ttl_hours = session_ttl_hours
        self.max_retries = max_retries
        self._closed = False

        # Storage provider
        storage_provider = storage_provider or os.getenv("ARTIFACT_PROVIDER", "memory")
        self._s3_factory = self._load_storage_provider(storage_provider)
        self._storage_provider_name = storage_provider

        # Session provider
        session_provider = session_provider or os.getenv("SESSION_PROVIDER", "memory")
        self._session_factory = self._load_session_provider(session_provider)
        self._session_provider_name = session_provider

        # Session manager (now using chuk_sessions)
        self._session_manager = SessionManager(
            sandbox_id=self.sandbox_id,
            default_ttl_hours=session_ttl_hours,
        )

        # Operation modules
        from .core import CoreStorageOperations as CoreOps
        from .metadata import MetadataOperations as MetaOps
        from .presigned import PresignedURLOperations as PresignedOps
        from .batch import BatchOperations as BatchOps
        from .admin import AdminOperations as AdminOps
        from .namespace import NamespaceOperations

        self._core = CoreOps(self)
        self._metadata = MetaOps(self)
        self._presigned = PresignedOps(self)
        self._batch = BatchOps(self)
        self._admin = AdminOps(self)
        self._namespace = NamespaceOperations(self)

        logger.info(
            "ArtifactStore initialized",
            extra={
                "bucket": self.bucket,
                "sandbox_id": self.sandbox_id,
                "storage_provider": storage_provider,
                "session_provider": session_provider,
            },
        )

    # ─────────────────────────────────────────────────────────────────
    # Core operations
    # ─────────────────────────────────────────────────────────────────

    async def store(
        self,
        data: bytes,
        *,
        mime: str,
        summary: str,
        meta: Dict[str, Any] | None = None,
        filename: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        ttl: int = DEFAULT_TTL,
        scope: StorageScope
        | str = StorageScope.SESSION,  # Support both enum and string for backward compat
    ) -> str:
        """
        Store artifact with scope-based storage support.

        Args:
            data: Artifact data bytes
            mime: MIME type
            summary: Human-readable description
            meta: Optional custom metadata
            filename: Optional filename
            session_id: Session ID (auto-allocated if not provided)
            user_id: User ID (used for session allocation and user scope)
            ttl: Time-to-live in seconds (default 900 = 15 min)
            scope: Storage scope - "session" (ephemeral), "user" (persistent), or "sandbox" (shared)

        Returns:
            Artifact ID

        Examples:
            >>> # Session-scoped (default, ephemeral)
            >>> artifact_id = await store.store(data, mime="...", summary="...")

            >>> # User-scoped (persistent across sessions)
            >>> artifact_id = await store.store(
            ...     data, mime="...", summary="...",
            ...     user_id="alice", scope="user", ttl=None
            ... )

            >>> # Sandbox-scoped (shared by all users)
            >>> artifact_id = await store.store(
            ...     data, mime="...", summary="...",
            ...     scope="sandbox"
            ... )
        """
        # Normalize scope to enum if string passed (backward compatibility)
        if isinstance(scope, str):
            scope = StorageScope(scope)

        # For user-scoped artifacts, user_id is required
        if scope == StorageScope.USER and not user_id:
            raise ValueError("user_id is required for user-scoped artifacts")

        # Always allocate/validate session using chuk_sessions
        # (even for user/sandbox scope, we track which session created it)
        session_id = await self._session_manager.allocate_session(
            session_id=session_id,
            user_id=user_id,
        )

        # Store using core operations with scope
        return await self._core.store(
            data=data,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id=session_id,
            ttl=ttl,
            scope=scope,
            owner_id=user_id if scope == StorageScope.USER else None,
        )

    async def update_file(
        self,
        artifact_id: str,
        *,
        data: Optional[bytes] = None,
        meta: Optional[Dict[str, Any]] = None,
        filename: Optional[str] = None,
        summary: Optional[str] = None,
        mime: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Update an artifact's content, metadata, filename, summary, or mime type.
        All parameters are optional. At least one must be provided.
        """
        if not any(
            [
                data is not None,
                meta is not None,
                filename is not None,
                summary is not None,
                mime is not None,
                ttl is not None,
            ]
        ):
            raise ValueError("At least one update parameter must be provided.")

        return await self._core.update_file(
            artifact_id=artifact_id,
            new_data=data,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            ttl=ttl,
        )

    async def retrieve(
        self,
        artifact_id: str,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bytes:
        """
        Retrieve artifact data with optional access control.

        Args:
            artifact_id: ID of artifact to retrieve
            user_id: User ID for access control (required for user-scoped artifacts)
            session_id: Session ID for access control (optional for session-scoped artifacts)

        Returns:
            Artifact data bytes

        Raises:
            AccessDeniedError: If access is denied (only for user/sandbox scoped artifacts)
            ArtifactNotFoundError: If artifact not found

        Examples:
            >>> # Legacy usage (backward compatible, no access check)
            >>> data = await store.retrieve(artifact_id)

            >>> # Session-scoped artifact with access control
            >>> data = await store.retrieve(artifact_id, session_id="sess123")

            >>> # User-scoped artifact
            >>> data = await store.retrieve(artifact_id, user_id="alice")

            >>> # Sandbox-scoped artifact (anyone in sandbox can read)
            >>> data = await store.retrieve(artifact_id)

        Note:
            Access control is enforced for user-scoped and sandbox-scoped artifacts.
            For session-scoped artifacts (default), access control is only enforced
            if session_id is explicitly provided (opt-in for new security model).
        """
        # Get metadata to check if access control is needed
        metadata = await self.metadata(artifact_id)

        # Only enforce access control for:
        # 1. User-scoped artifacts (always)
        # 2. Sandbox-scoped artifacts (always)
        # 3. Session-scoped artifacts when session_id is explicitly provided (opt-in)
        # Handle both ArtifactMetadata objects and dict-style metadata (backward compat)
        metadata_scope = (
            getattr(metadata, "scope", None)
            or metadata.get("scope", StorageScope.SESSION)
            if isinstance(metadata, dict)
            else metadata.scope
        )

        # Normalize scope to enum for comparison
        if isinstance(metadata_scope, str):
            metadata_scope = StorageScope(metadata_scope)

        should_check_access = metadata_scope in (
            StorageScope.USER,
            StorageScope.SANDBOX,
        ) or (metadata_scope == StorageScope.SESSION and session_id is not None)

        if should_check_access:
            from .access_control import check_access, build_context

            context = build_context(
                user_id=user_id, session_id=session_id, sandbox_id=self.sandbox_id
            )
            check_access(metadata, context)

        # Access granted (or no check needed), retrieve data
        return await self._core.retrieve(artifact_id)

    async def stream_upload(self, request: StreamUploadRequest) -> str:
        """
        Stream upload large artifact with progress tracking.

        Supports streaming uploads for large files (videos, datasets, etc.) with
        optional progress callbacks to track upload status.

        Args:
            request: StreamUploadRequest containing all upload parameters

        Returns:
            Artifact ID

        Examples:
            >>> # Basic streaming upload
            >>> async def file_chunks():
            ...     with open("large_video.mp4", "rb") as f:
            ...         while chunk := f.read(65536):  # 64KB chunks
            ...             yield chunk
            >>>
            >>> request = StreamUploadRequest(
            ...     data_stream=file_chunks(),
            ...     mime="video/mp4",
            ...     summary="Large video file",
            ...     filename="video.mp4",
            ...     user_id="alice",
            ...     content_length=1024*1024*100  # 100MB
            ... )
            >>> artifact_id = await store.stream_upload(request)

            >>> # With progress callback
            >>> def progress(bytes_sent, total_bytes):
            ...     if total_bytes:
            ...         pct = (bytes_sent / total_bytes) * 100
            ...         print(f"Upload: {pct:.1f}% ({bytes_sent}/{total_bytes})")
            >>>
            >>> request = StreamUploadRequest(
            ...     data_stream=file_chunks(),
            ...     mime="video/mp4",
            ...     summary="Video with progress",
            ...     progress_callback=progress,
            ...     content_length=file_size
            ... )
            >>> artifact_id = await store.stream_upload(request)
        """
        # Normalize scope (backward compatibility)
        scope = (
            request.scope
            if isinstance(request.scope, StorageScope)
            else StorageScope(request.scope)
        )

        # For user-scoped artifacts, user_id is required
        if scope == StorageScope.USER and not request.user_id:
            raise ValueError("user_id is required for user-scoped artifacts")

        # Allocate/validate session
        session_id = await self._session_manager.allocate_session(
            session_id=request.session_id,
            user_id=request.user_id,
        )

        # Stream upload using core operations
        return await self._core.stream_upload(
            data_stream=request.data_stream,
            mime=request.mime,
            summary=request.summary,
            meta=request.meta,
            filename=request.filename,
            session_id=session_id,
            ttl=request.ttl,
            scope=scope,
            owner_id=request.user_id if scope == StorageScope.USER else None,
            content_length=request.content_length,
            progress_callback=request.progress_callback,
        )

    async def stream_download(
        self, request: StreamDownloadRequest
    ) -> AsyncIterator[bytes]:
        """
        Stream download artifact data with progress tracking.

        Supports streaming downloads for large files with optional progress
        callbacks to track download status.

        Args:
            request: StreamDownloadRequest containing all download parameters

        Yields:
            Bytes chunks

        Examples:
            >>> # Basic streaming download
            >>> request = StreamDownloadRequest(
            ...     artifact_id="abc123",
            ...     chunk_size=65536  # 64KB chunks
            ... )
            >>> async for chunk in store.stream_download(request):
            ...     # Process chunk (write to file, network, etc.)
            ...     await output_file.write(chunk)

            >>> # With progress callback
            >>> def progress(bytes_received, total_bytes):
            ...     if total_bytes:
            ...         pct = (bytes_received / total_bytes) * 100
            ...         print(f"Download: {pct:.1f}%")
            >>>
            >>> request = StreamDownloadRequest(
            ...     artifact_id="abc123",
            ...     progress_callback=progress,
            ...     user_id="alice"  # For access control
            ... )
            >>> async for chunk in store.stream_download(request):
            ...     process_chunk(chunk)

            >>> # User-scoped artifact with access control
            >>> request = StreamDownloadRequest(
            ...     artifact_id="user-doc-123",
            ...     user_id="alice",
            ...     chunk_size=131072  # 128KB chunks
            ... )
            >>> async for chunk in store.stream_download(request):
            ...     await save_chunk(chunk)
        """
        # Get metadata to check if access control is needed
        metadata = await self.metadata(request.artifact_id)

        # Enforce access control (same logic as retrieve)
        metadata_scope = (
            getattr(metadata, "scope", None)
            or metadata.get("scope", StorageScope.SESSION)
            if isinstance(metadata, dict)
            else metadata.scope
        )

        # Normalize scope to enum for comparison
        if isinstance(metadata_scope, str):
            metadata_scope = StorageScope(metadata_scope)

        should_check_access = metadata_scope in (
            StorageScope.USER,
            StorageScope.SANDBOX,
        ) or (metadata_scope == StorageScope.SESSION and request.session_id is not None)

        if should_check_access:
            from .access_control import check_access, build_context

            context = build_context(
                user_id=request.user_id,
                session_id=request.session_id,
                sandbox_id=self.sandbox_id,
            )
            check_access(metadata, context)

        # Access granted, stream download
        async for chunk in self._core.stream_download(
            artifact_id=request.artifact_id,
            chunk_size=request.chunk_size,
            progress_callback=request.progress_callback,
        ):
            yield chunk

    async def metadata(self, artifact_id: str) -> ArtifactMetadata:
        """Get artifact metadata."""
        return await self._metadata.get_metadata(artifact_id)

    async def exists(self, artifact_id: str) -> bool:
        """Check if artifact exists."""
        return await self._metadata.exists(artifact_id)

    async def delete(
        self,
        artifact_id: str,
        *,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Delete artifact with optional access control.

        Args:
            artifact_id: ID of artifact to delete
            user_id: User ID for access control (required for user-scoped artifacts)
            session_id: Session ID for access control (optional for session-scoped artifacts)

        Returns:
            True if deleted successfully

        Raises:
            AccessDeniedError: If modification is denied
            ArtifactNotFoundError: If artifact not found

        Note:
            Access control is enforced for user-scoped and sandbox-scoped artifacts.
            For session-scoped artifacts (default), access control is only enforced
            if session_id is explicitly provided (opt-in for new security model).
            Sandbox-scoped artifacts cannot be deleted via this method - use admin
            endpoints for sandbox artifact management.
        """
        # Get metadata to check if access control is needed
        metadata = await self.metadata(artifact_id)

        # Only enforce access control for:
        # 1. User-scoped artifacts (always)
        # 2. Sandbox-scoped artifacts (always)
        # 3. Session-scoped artifacts when session_id is explicitly provided (opt-in)
        # Handle both ArtifactMetadata objects and dict-style metadata (backward compat)
        metadata_scope = (
            getattr(metadata, "scope", None)
            or metadata.get("scope", StorageScope.SESSION)
            if isinstance(metadata, dict)
            else metadata.scope
        )

        # Normalize scope to enum for comparison
        if isinstance(metadata_scope, str):
            metadata_scope = StorageScope(metadata_scope)

        should_check_access = metadata_scope in (
            StorageScope.USER,
            StorageScope.SANDBOX,
        ) or (metadata_scope == StorageScope.SESSION and session_id is not None)

        if should_check_access:
            from .access_control import can_modify, build_context

            context = build_context(
                user_id=user_id, session_id=session_id, sandbox_id=self.sandbox_id
            )

            # Check modification permission
            if not can_modify(metadata, context):
                from .exceptions import AccessDeniedError

                owner_id = (
                    getattr(metadata, "owner_id", None) or metadata.get("owner_id")
                    if isinstance(metadata, dict)
                    else None
                )
                session_id_from_meta = (
                    getattr(metadata, "session_id", None) or metadata.get("session_id")
                    if isinstance(metadata, dict)
                    else None
                )
                raise AccessDeniedError(
                    f"Cannot delete artifact {artifact_id}: insufficient permissions. "
                    f"Scope: {metadata_scope.value if isinstance(metadata_scope, StorageScope) else metadata_scope}, Owner: {owner_id or session_id_from_meta}"
                )

        # Permission granted (or no check needed), delete
        return await self._metadata.delete(artifact_id)

    async def list_by_session(
        self, session_id: str, limit: int = 100
    ) -> List[ArtifactMetadata]:
        """List artifacts in session."""
        return await self._metadata.list_by_session(session_id, limit)

    async def search(
        self,
        *,
        user_id: Optional[str] = None,
        scope: Optional[str] = None,
        mime_prefix: Optional[str] = None,
        meta_filter: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[ArtifactMetadata]:
        """
        Search artifacts by scope, user, MIME type, and metadata.

        This is useful for finding user artifacts across all sessions, or searching
        within specific scopes.

        Args:
            user_id: Filter by owner (user-scoped artifacts only)
            scope: Filter by scope ("session", "user", or "sandbox")
            mime_prefix: Filter by MIME type prefix (e.g., "image/" for all images)
            meta_filter: Filter by custom metadata (exact match)
            limit: Maximum number of results

        Returns:
            List of matching artifacts

        Examples:
            >>> # Find all user's artifacts across sessions
            >>> artifacts = await store.search(user_id="alice", scope="user")

            >>> # Find all images for a user
            >>> images = await store.search(
            ...     user_id="alice",
            ...     scope="user",
            ...     mime_prefix="image/"
            ... )

            >>> # Find by custom metadata
            >>> artifacts = await store.search(
            ...     user_id="alice",
            ...     meta_filter={"project": "Q4-deck"}
            ... )

        Note:
            This method requires iterating through storage keys. For large datasets,
            consider using a proper search index (Elasticsearch, Typesense, etc.).
        """
        results = []

        try:
            # Normalize scope to enum if provided as string
            scope_enum = (
                StorageScope(scope)
                if isinstance(scope, str)
                else scope
                if scope
                else None
            )

            # Build prefix based on scope and user
            if scope_enum == StorageScope.USER and user_id:
                prefix = f"grid/{self.sandbox_id}/users/{user_id}/"
            elif scope_enum == StorageScope.SESSION:
                # Can't search all sessions efficiently without index
                logger.warning(
                    "Searching session scope requires session_id, use list_by_session() instead"
                )
                return []
            elif scope_enum == StorageScope.SANDBOX:
                prefix = f"grid/{self.sandbox_id}/shared/"
            elif user_id:
                # Search user artifacts specifically
                prefix = f"grid/{self.sandbox_id}/users/{user_id}/"
            else:
                # Search entire sandbox (expensive!)
                prefix = f"grid/{self.sandbox_id}/"

            storage_ctx_mgr = self._s3_factory()
            async with storage_ctx_mgr as s3:
                if not hasattr(s3, "list_objects_v2"):
                    logger.warning("Storage provider doesn't support listing")
                    return []

                response = await s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    MaxKeys=limit * 2,  # Get more to account for filtering
                )

                for obj in response.get("Contents", []):
                    key = obj["Key"]
                    parsed = self.parse_grid_key(key)

                    if not parsed:
                        continue

                    # Strip file extension from artifact_id (if present)
                    # The artifact_id in the key may have an extension, but metadata is stored by UUID only
                    artifact_id_with_ext = parsed.artifact_id
                    artifact_id = os.path.splitext(artifact_id_with_ext)[0]

                    try:
                        metadata = await self.metadata(artifact_id)

                        # Apply filters
                        if scope and metadata.scope != scope:
                            continue

                        if user_id and metadata.owner_id != user_id:
                            continue

                        if mime_prefix and not metadata.mime.startswith(mime_prefix):
                            continue

                        if meta_filter:
                            # Check if all filter items match
                            matches = all(
                                metadata.meta.get(k) == v
                                for k, v in meta_filter.items()
                            )
                            if not matches:
                                continue

                        results.append(metadata)

                        if len(results) >= limit:
                            break

                    except Exception as e:
                        logger.debug(f"Skipping artifact {artifact_id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise ProviderError(f"Search operation failed: {e}") from e

        return results

    # ─────────────────────────────────────────────────────────────────
    # Session operations - now delegated to chuk_sessions
    # ─────────────────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: Optional[str] = None,
        ttl_hours: Optional[int] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new session."""
        return await self._session_manager.allocate_session(
            user_id=user_id,
            ttl_hours=ttl_hours,
            custom_metadata=custom_metadata,
        )

    async def validate_session(self, session_id: str) -> bool:
        """Validate session."""
        return await self._session_manager.validate_session(session_id)

    async def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """Get session information."""
        info_dict = await self._session_manager.get_session_info(session_id)
        if info_dict is None:
            return None
        # Convert dict to SessionInfo model
        return SessionInfo(
            session_id=info_dict.get("session_id", session_id),
            sandbox_id=info_dict.get("sandbox_id", self.sandbox_id),
            user_id=info_dict.get("user_id"),
            created_at=info_dict.get("created_at"),
            expires_at=info_dict.get("expires_at"),
            ttl_hours=info_dict.get("ttl_hours"),
            metadata=info_dict.get("metadata", {}),
        )

    async def update_session_metadata(
        self, session_id: str, metadata: Dict[str, Any]
    ) -> bool:
        """Update session metadata."""
        return await self._session_manager.update_session_metadata(session_id, metadata)

    async def extend_session_ttl(self, session_id: str, additional_hours: int) -> bool:
        """Extend session TTL."""
        return await self._session_manager.extend_session_ttl(
            session_id, additional_hours
        )

    async def delete_session(self, session_id: str) -> bool:
        """Delete session."""
        return await self._session_manager.delete_session(session_id)

    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions."""
        return await self._session_manager.cleanup_expired_sessions()

    # ─────────────────────────────────────────────────────────────────
    # Grid operations - now delegated to chuk_sessions
    # ─────────────────────────────────────────────────────────────────

    def get_canonical_prefix(self, session_id: str) -> str:
        """Get grid path prefix for session."""
        return canonical_prefix(self.sandbox_id, session_id)

    def generate_artifact_key(
        self,
        session_id: str,
        artifact_id: str,
        mime_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Generate grid artifact key with optional file extension."""
        return artifact_key(
            self.sandbox_id,
            session_id,
            artifact_id,
            mime_type=mime_type,
            filename=filename,
        )

    def parse_grid_key(self, grid_key: str) -> Optional[GridKeyComponents]:
        """Parse grid key to extract components."""
        return parse(grid_key)

    def get_session_prefix_pattern(self) -> str:
        """Get session prefix pattern for this sandbox."""
        return f"grid/{self.sandbox_id}/"

    # ─────────────────────────────────────────────────────────────────
    # File operations
    # ─────────────────────────────────────────────────────────────────

    async def write_file(
        self,
        content: Union[str, bytes],
        *,
        filename: str,
        mime: str = "text/plain",
        summary: str = "",
        session_id: str = None,
        user_id: str = None,
        meta: Dict[str, Any] = None,
        encoding: str = "utf-8",
        scope: str = "session",
        ttl: int = _DEFAULT_TTL,
    ) -> str:
        """Write content to file."""
        # Normalize scope
        if isinstance(scope, str):
            scope = StorageScope(scope)

        if isinstance(content, str):
            data = content.encode(encoding)
        else:
            data = content

        return await self.store(
            data=data,
            mime=mime,
            summary=summary or f"File: {filename}",
            filename=filename,
            session_id=session_id,
            user_id=user_id,
            meta=meta,
            scope=scope,
            ttl=ttl,
        )

    async def read_file(
        self, artifact_id: str, *, encoding: str = "utf-8", as_text: bool = True
    ) -> Union[str, bytes]:
        """Read file content."""
        data = await self.retrieve(artifact_id)

        if as_text:
            return data.decode(encoding)
        return data

    async def list_files(
        self, session_id: str, prefix: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List files in session with optional prefix filter."""
        return await self._metadata.list_by_prefix(session_id, prefix, limit)

    async def get_directory_contents(
        self, session_id: str, directory_prefix: str = "", limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List files in a directory-like structure within a session.
        """
        try:
            return await self._metadata.list_by_prefix(
                session_id, directory_prefix, limit
            )
        except Exception as e:
            logger.error(
                "Directory listing failed for session %s: %s",
                session_id,
                str(e),
                extra={
                    "session_id": session_id,
                    "directory_prefix": directory_prefix,
                    "operation": "get_directory_contents",
                },
            )
            raise ProviderError(f"Directory listing failed: {e}") from e

    async def copy_file(
        self,
        artifact_id: str,
        *,
        new_filename: str = None,
        target_session_id: str = None,
        new_meta: Dict[str, Any] = None,
        summary: str = None,
    ) -> str:
        """Copy a file WITHIN THE SAME SESSION only (security enforced)."""
        # Get original metadata to check session
        original_meta = await self.metadata(artifact_id)
        original_session = original_meta.session_id

        # STRICT SECURITY: Block ALL cross-session copies
        if target_session_id and target_session_id != original_session:
            raise ArtifactStoreError(
                f"Cross-session copies are not permitted for security reasons. "
                f"Artifact {artifact_id} belongs to session '{original_session}', "
                f"cannot copy to session '{target_session_id}'. Files can only be "
                f"copied within the same session."
            )

        # Get original data
        original_data = await self.retrieve(artifact_id)

        # Prepare copy metadata
        copy_filename = new_filename or ((original_meta.filename or "file") + "_copy")
        copy_summary = summary or f"Copy of {original_meta.summary}"

        # Merge metadata
        copy_meta = {**original_meta.meta}
        if new_meta:
            copy_meta.update(new_meta)

        # Add copy tracking
        copy_meta["copied_from"] = artifact_id
        copy_meta["copy_timestamp"] = datetime.utcnow().isoformat() + "Z"

        # Store the copy in the same session
        return await self.store(
            data=original_data,
            mime=original_meta.mime,
            summary=copy_summary,
            filename=copy_filename,
            session_id=original_session,  # Always same session
            meta=copy_meta,
        )

    async def move_file(
        self,
        artifact_id: str,
        *,
        new_filename: str = None,
        new_session_id: str = None,
        new_meta: Dict[str, Any] = None,
    ) -> ArtifactMetadata:
        """Move/rename a file WITHIN THE SAME SESSION only (security enforced)."""
        # Get current metadata
        record = await self.metadata(artifact_id)
        current_session = record.session_id

        # STRICT SECURITY: Block ALL cross-session moves
        if new_session_id and new_session_id != current_session:
            raise ArtifactStoreError(
                f"Cross-session moves are not permitted for security reasons. "
                f"Artifact {artifact_id} belongs to session '{current_session}', "
                f"cannot move to session '{new_session_id}'. Use copy operations within "
                f"the same session only."
            )

        # For now, just simulate a move by updating metadata
        # A full implementation would update the metadata record
        if new_filename:
            # This is a simplified move - just return updated record
            record.filename = new_filename
        if new_meta:
            record.meta.update(new_meta)

        return record

    # ─────────────────────────────────────────────────────────────────
    # Presigned URL operations
    # ─────────────────────────────────────────────────────────────────

    async def presign(
        self, artifact_id: str, expires: int = _DEFAULT_PRESIGN_EXPIRES
    ) -> str:
        """Generate a presigned URL for artifact download."""
        return await self._presigned.presign(artifact_id, expires)

    async def presign_short(self, artifact_id: str) -> str:
        """Generate a short-lived presigned URL (15 minutes)."""
        return await self._presigned.presign_short(artifact_id)

    async def presign_medium(self, artifact_id: str) -> str:
        """Generate a medium-lived presigned URL (1 hour)."""
        return await self._presigned.presign_medium(artifact_id)

    async def presign_long(self, artifact_id: str) -> str:
        """Generate a long-lived presigned URL (24 hours)."""
        return await self._presigned.presign_long(artifact_id)

    async def presign_upload(
        self,
        session_id: str | None = None,
        filename: str | None = None,
        mime_type: str = "application/octet-stream",
        expires: int = _DEFAULT_PRESIGN_EXPIRES,
    ) -> tuple[str, str]:
        """Generate a presigned URL for uploading a new artifact."""
        return await self._presigned.presign_upload(
            session_id, filename, mime_type, expires
        )

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
        return await self._presigned.register_uploaded_artifact(
            artifact_id,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id=session_id,
            ttl=ttl,
        )

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
        return await self._presigned.presign_upload_and_register(
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id=session_id,
            ttl=ttl,
            expires=expires,
        )

    # ─────────────────────────────────────────────────────────────────
    # Multipart upload operations
    # ─────────────────────────────────────────────────────────────────

    async def initiate_multipart_upload(
        self,
        request: MultipartUploadInitRequest,
    ) -> Dict[str, Any]:
        """
        Initiate a multipart upload for large files (>5MB).

        Multipart uploads enable efficient uploading of large files in chunks.
        Ideal for videos, datasets, and media workflows.

        Workflow:
            1. Call initiate_multipart_upload() to get upload_id
            2. Get presigned URLs for each part with get_part_upload_url()
            3. Client uploads each part (minimum 5MB except last part)
            4. Call complete_multipart_upload() with part ETags

        Args:
            request: MultipartUploadInitRequest with all upload parameters

        Returns:
            Dictionary with upload_id, artifact_id, key, session_id

        Examples:
            >>> # Step 1: Initiate
            >>> request = MultipartUploadInitRequest(
            ...     filename="video.mp4",
            ...     mime_type="video/mp4",
            ...     user_id="alice"
            ... )
            >>> info = await store.initiate_multipart_upload(request)
            >>> upload_id = info["upload_id"]
            >>>
            >>> # Step 2: Get part URLs (client uploads each part)
            >>> for part_num in range(1, num_parts + 1):
            ...     url = await store.get_part_upload_url(upload_id, part_num)
            ...     # Client uploads part to URL
            >>>
            >>> # Step 3: Complete
            >>> complete_request = MultipartUploadCompleteRequest(
            ...     upload_id=upload_id,
            ...     parts=[MultipartUploadPart(PartNumber=1, ETag="...")]
            ... )
            >>> artifact_id = await store.complete_multipart_upload(complete_request)
        """
        return await self._presigned.initiate_multipart_upload(request)

    async def get_part_upload_url(
        self,
        upload_id: str,
        part_number: int,
        expires: int = _DEFAULT_PRESIGN_EXPIRES,
    ) -> str:
        """
        Get presigned URL for uploading a specific part.

        Part numbers must be sequential (1-10,000).
        Minimum part size: 5MB (except last part).

        Args:
            upload_id: Upload ID from initiate_multipart_upload()
            part_number: Part number (1-10000)
            expires: URL expiration in seconds (default 1 hour)

        Returns:
            Presigned PUT URL for the part

        Example:
            >>> url = await store.get_part_upload_url(upload_id, part_number=1)
            >>> # Client uploads: curl -X PUT -T part1.bin "$url"
        """
        return await self._presigned.get_part_upload_url(
            upload_id, part_number, expires
        )

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

        Examples:
            >>> # Complete with Pydantic model
            >>> request = MultipartUploadCompleteRequest(
            ...     upload_id=upload_id,
            ...     parts=[
            ...         MultipartUploadPart(PartNumber=1, ETag="abc123..."),
            ...         MultipartUploadPart(PartNumber=2, ETag="def456..."),
            ...     ],
            ...     summary="Large video upload"
            ... )
            >>> artifact_id = await store.complete_multipart_upload(request)
        """
        return await self._presigned.complete_multipart_upload(request)

    async def abort_multipart_upload(self, upload_id: str) -> bool:
        """
        Abort an incomplete multipart upload and clean up resources.

        Use this to cancel uploads that won't complete or to clean up
        after errors.

        Args:
            upload_id: Upload ID from initiate_multipart_upload()

        Returns:
            True if aborted successfully

        Example:
            >>> success = await store.abort_multipart_upload(upload_id)
        """
        return await self._presigned.abort_multipart_upload(upload_id)

    # ─────────────────────────────────────────────────────────────────
    # Batch operations
    # ─────────────────────────────────────────────────────────────────

    async def store_batch(
        self,
        items: List[Dict[str, Any]],
        session_id: str | None = None,
        ttl: int = _DEFAULT_TTL,
    ) -> List[str]:
        """Store multiple artifacts in a batch operation."""
        return await self._batch.store_batch(items, session_id, ttl)

    # ─────────────────────────────────────────────────────────────────
    # Metadata operations
    # ─────────────────────────────────────────────────────────────────

    async def update_metadata(
        self,
        artifact_id: str,
        *,
        summary: str = None,
        meta: Dict[str, Any] = None,
        merge: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """Update artifact metadata."""
        return await self._metadata.update_metadata(
            artifact_id, summary=summary, meta=meta, merge=merge, **kwargs
        )

    async def extend_ttl(
        self, artifact_id: str, additional_seconds: int
    ) -> Dict[str, Any]:
        """Extend artifact TTL."""
        return await self._metadata.extend_ttl(artifact_id, additional_seconds)

    # ─────────────────────────────────────────────────────────────────
    # Administrative operations
    # ─────────────────────────────────────────────────────────────────

    async def validate_configuration(self) -> ValidationResponse:
        """Validate store configuration and connectivity."""
        return await self._admin.validate_configuration()

    async def get_stats(self) -> StatsResponse:
        """Get storage statistics."""
        stats_dict = await self._admin.get_stats()

        # Add session manager stats
        session_stats_dict = self._session_manager.get_cache_stats()

        # Convert to proper models
        return StatsResponse(
            storage_provider=stats_dict.get(
                "storage_provider", self._storage_provider_name
            ),
            session_provider=stats_dict.get(
                "session_provider", self._session_provider_name
            ),
            bucket=stats_dict.get("bucket", self.bucket),
            sandbox_id=stats_dict.get("sandbox_id", self.sandbox_id),
            session_manager=SessionStats(**session_stats_dict)
            if session_stats_dict
            else SessionStats(),
            storage_stats=StorageStats(
                provider=stats_dict.get("storage_provider"),
                bucket=stats_dict.get("bucket"),
                total_artifacts=stats_dict.get("total_artifacts"),
                total_bytes=stats_dict.get("total_bytes"),
            ),
            # Backward compatibility fields at top level
            total_artifacts=stats_dict.get("total_artifacts"),
            total_bytes=stats_dict.get("total_bytes"),
        )

    # ─────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    def _detect_sandbox_id(self) -> str:
        """Auto-detect sandbox ID."""
        candidates = [
            os.getenv("ARTIFACT_SANDBOX_ID"),
            os.getenv("SANDBOX_ID"),
            os.getenv("HOSTNAME"),
        ]

        for candidate in candidates:
            if candidate:
                clean_id = "".join(c for c in candidate if c.isalnum() or c in "-_")[
                    :32
                ]
                if clean_id:
                    return clean_id

        # Generate fallback
        return f"sandbox-{uuid.uuid4().hex[:8]}"

    def _load_storage_provider(self, name: str) -> Callable[[], AsyncContextManager]:
        """Load storage provider."""
        from .provider_factory import factory_for_env
        from importlib import import_module
        import os

        # Temporarily set the provider name in environment
        # so factory_for_env can pick it up
        original_provider = os.environ.get("ARTIFACT_PROVIDER")
        try:
            os.environ["ARTIFACT_PROVIDER"] = name
            return factory_for_env()
        except ValueError:
            # If factory_for_env doesn't recognize it, try direct import
            try:
                mod = import_module(f"chuk_artifacts.providers.{name}")
                return mod.factory()
            except ModuleNotFoundError as exc:
                available = [
                    "memory",
                    "filesystem",
                    "s3",
                    "ibm_cos",
                    "vfs",
                    "vfs-memory",
                    "vfs-filesystem",
                    "vfs-s3",
                    "vfs-sqlite",
                ]
                raise ValueError(
                    f"Unknown storage provider '{name}'. Available: {', '.join(available)}"
                ) from exc
        finally:
            # Restore original environment
            if original_provider is not None:
                os.environ["ARTIFACT_PROVIDER"] = original_provider
            else:
                os.environ.pop("ARTIFACT_PROVIDER", None)

    def _load_session_provider(self, name: str) -> Callable[[], AsyncContextManager]:
        """Load session provider."""
        from importlib import import_module

        try:
            mod = import_module(f"chuk_sessions.providers.{name}")
            return mod.factory()
        except ModuleNotFoundError as exc:
            raise ValueError(f"Unknown session provider '{name}'") from exc

    # ─────────────────────────────────────────────────────────────────
    # Resource management
    # ─────────────────────────────────────────────────────────────────

    async def close(self):
        """Close the store."""
        if not self._closed:
            self._closed = True
            logger.info("ArtifactStore closed")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def get_sandbox_info(self) -> SandboxInfo:
        """
        Get sandbox information and metadata.

        Returns
        -------
        SandboxInfo
            Pydantic model containing sandbox information including:
            - sandbox_id: The current sandbox identifier
            - bucket: The storage bucket name
            - storage_provider: The storage provider type
            - session_provider: The session provider type
            - session_ttl_hours: Default session TTL
            - grid_prefix_pattern: The grid path pattern for this sandbox
            - created_at: Timestamp of when this info was retrieved
        """
        from datetime import datetime

        # Get session manager stats if available
        session_stats_dict = {}
        try:
            session_stats_dict = self._session_manager.get_cache_stats()
        except Exception:
            pass  # Session manager might not have stats

        # Get storage stats if available
        storage_stats_dict = {}
        try:
            storage_stats_dict = await self._admin.get_stats()
        except Exception:
            pass  # Storage might not have stats

        return SandboxInfo(
            sandbox_id=self.sandbox_id,
            bucket=self.bucket,
            storage_provider=self._storage_provider_name,
            session_provider=self._session_provider_name,
            session_ttl_hours=self.session_ttl_hours,
            max_retries=self.max_retries,
            grid_prefix_pattern=self.get_session_prefix_pattern(),
            created_at=datetime.utcnow().isoformat() + "Z",
            session_stats=SessionStats(**session_stats_dict)
            if session_stats_dict
            else SessionStats(),
            storage_stats=StorageStats(
                provider=storage_stats_dict.get("storage_provider"),
                bucket=storage_stats_dict.get("bucket"),
                total_artifacts=storage_stats_dict.get("total_artifacts"),
                total_bytes=storage_stats_dict.get("total_bytes"),
            ),
            closed=self._closed,
        )

    # ─────────────────────────────────────────────────────────────────
    # Unified Namespace Operations (Clean API - everything is VFS)
    # ─────────────────────────────────────────────────────────────────

    @property
    def namespace(self):
        """Access namespace operations (clean API)."""
        return self._namespace

    # Clean API - Namespace operations
    async def create_namespace(self, **kwargs):
        """
        Create a namespace (blob or workspace).

        Args:
        type: NamespaceType.BLOB or NamespaceType.WORKSPACE
            name: Optional name (recommended for workspaces)
            scope: StorageScope (SESSION, USER, SANDBOX)
            provider_type: VFS provider (vfs-memory, vfs-filesystem, etc.)
            **kwargs: Additional parameters

        Returns:
            NamespaceInfo

        Examples:
            >>> # Create blob namespace
            >>> blob_ns = await store.create_namespace(
            ...     type=NamespaceType.BLOB,
            ...     scope=StorageScope.SESSION
            ... )

            >>> # Create workspace namespace
            >>> workspace_ns = await store.create_namespace(
            ...     type=NamespaceType.WORKSPACE,
            ...     name="my-project",
            ...     scope=StorageScope.USER,
            ...     user_id="alice"
            ... )
        """
        return await self._namespace.create_namespace(**kwargs)

    async def write_namespace(self, namespace_id: str, **kwargs):
        """
        Write to namespace.

        For blobs: path=None writes to /_data
        For workspaces: path required

        Args:
            namespace_id: Namespace ID
            data: Data bytes
            path: File path (None for blobs, required for workspaces)
            mime: MIME type (for blobs)
        """
        return await self._namespace.write_namespace(namespace_id, **kwargs)

    async def read_namespace(self, namespace_id: str, **kwargs):
        """
        Read from namespace.

        For blobs: path=None reads from /_data
        For workspaces: path required

        Args:
            namespace_id: Namespace ID
            path: File path (None for blobs, required for workspaces)

        Returns:
            File contents as bytes
        """
        return await self._namespace.read_namespace(namespace_id, **kwargs)

    def get_namespace_vfs(self, namespace_id: str):
        """
        Get VFS instance for namespace (blob or workspace).

        Args:
            namespace_id: Namespace ID

        Returns:
            AsyncVirtualFileSystem instance
        """
        return self._namespace.get_namespace_vfs(namespace_id)

    def get_namespace_info(self, namespace_id: str, session_id: str | None = None):
        """Get namespace information."""
        return self._namespace.get_namespace_info(namespace_id, session_id)

    def list_namespaces(self, **kwargs):
        """
        List namespaces.

        Args:
            session_id: Filter by session
            user_id: Filter by user
            type: Filter by NamespaceType (BLOB or WORKSPACE)
            include_all_scopes: Include sandbox namespaces

        Returns:
            List of NamespaceInfo
        """
        return self._namespace.list_namespaces(**kwargs)

    async def destroy_namespace(self, namespace_id: str, session_id: str | None = None):
        """Destroy namespace (blob or workspace)."""
        return await self._namespace.destroy_namespace(namespace_id, session_id)

    async def checkpoint_namespace(self, namespace_id: str, **kwargs):
        """Create checkpoint of namespace (blob or workspace)."""
        return await self._namespace.checkpoint_namespace(namespace_id, **kwargs)

    async def restore_namespace(self, namespace_id: str, checkpoint_id: str):
        """Restore namespace from checkpoint."""
        return await self._namespace.restore_namespace(namespace_id, checkpoint_id)

    async def list_checkpoints(self, namespace_id: str):
        """List checkpoints for namespace."""
        return await self._namespace.list_checkpoints(namespace_id)
