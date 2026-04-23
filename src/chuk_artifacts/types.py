# -*- coding: utf-8 -*-
# chuk_artifacts/types.py
"""
Type definitions, enums, and constants for chuk-artifacts.

This module provides strongly-typed enums and constants to replace magic strings
throughout the codebase, enabling better IDE support and type checking.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field, ConfigDict


class StorageScope(str, Enum):
    """
    Storage scope for artifacts.

    - SESSION: Ephemeral, tied to a session (15min-24h TTL)
    - USER: Persistent, tied to a user (long/no TTL)
    - SANDBOX: Shared across sandbox (long/no TTL)
    """

    SESSION = "session"
    USER = "user"
    SANDBOX = "sandbox"


class StorageProvider(str, Enum):
    """
    Available storage providers for artifact and workspace storage.

    Legacy providers (artifacts only):
    - MEMORY: In-memory storage (development/testing)
    - FILESYSTEM: Local filesystem storage
    - S3: AWS S3 or S3-compatible storage
    - IBM_COS: IBM Cloud Object Storage

    VFS providers (recommended for both artifacts and workspaces):
    - VFS_MEMORY: VFS-based memory storage
    - VFS_FILESYSTEM: VFS-based filesystem storage
    - VFS_S3: VFS-based S3 storage
    - VFS_SQLITE: VFS-based SQLite storage
    """

    MEMORY = "memory"
    FILESYSTEM = "filesystem"
    S3 = "s3"
    IBM_COS = "ibm_cos"
    VFS = "vfs"
    VFS_MEMORY = "vfs-memory"
    VFS_FILESYSTEM = "vfs-filesystem"
    VFS_S3 = "vfs-s3"
    VFS_SQLITE = "vfs-sqlite"


class SessionProvider(str, Enum):
    """
    Available session providers for metadata storage.

    - MEMORY: In-memory session storage (development/testing)
    - REDIS: Redis-based session storage (persistent)
    """

    MEMORY = "memory"
    REDIS = "redis"


class NamespaceType(str, Enum):
    """
    Namespace type for unified VFS-backed storage.

    - BLOB: Single-file namespace (artifact/blob storage)
    - WORKSPACE: Multi-file namespace (workspace/file tree)
    """

    BLOB = "blob"
    WORKSPACE = "workspace"


class OperationStatus(str, Enum):
    """Status of an operation or system component."""

    SUCCESS = "success"
    FAILED = "failed"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    # Backward compatibility aliases
    OK = "ok"  # Maps to HEALTHY for backward compat
    ERROR = "error"  # Maps to FAILED for backward compat


# Constants
DEFAULT_TTL = 900  # seconds (15 minutes)
DEFAULT_PRESIGN_EXPIRES = 3600  # seconds (1 hour)
DEFAULT_SESSION_TTL_HOURS = 24  # hours
DEFAULT_BUCKET = "artifacts"
DEFAULT_SANDBOX_PREFIX = "sandbox"


# Response Models


class ProviderStatus(BaseModel):
    """Status information for a provider (storage or session)."""

    status: OperationStatus = Field(description="Provider status")
    provider: str = Field(description="Provider name/type")
    message: Optional[str] = Field(None, description="Status message or error")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional details"
    )

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            # Check in details dict (backward compat - details were flattened in old API)
            if key in self.details:
                return self.details[key]
            # Check in extra fields
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator for backward compatibility."""
        try:
            getattr(self, key)
            return True
        except AttributeError:
            # Check in details dict (backward compat)
            if key in self.details:
                return True
            extra = getattr(self, "__pydantic_extra__", None)
            return extra is not None and key in extra


class ValidationResponse(BaseModel):
    """
    Response from configuration validation.

    Provides detailed status for both storage and session providers.
    """

    storage: ProviderStatus = Field(description="Storage provider status")
    session: ProviderStatus = Field(description="Session provider status")
    overall: OperationStatus = Field(description="Overall validation status")
    timestamp: Optional[str] = Field(
        None, description="Validation timestamp (ISO 8601, backward compat)"
    )
    session_manager: Optional[Dict[str, Any]] = Field(
        None, description="Session manager status (backward compat)"
    )

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator for backward compatibility."""
        try:
            getattr(self, key)
            return True
        except AttributeError:
            return False


class SessionStats(BaseModel):
    """Statistics from the session manager."""

    cache_hits: int = Field(default=0, description="Number of cache hits")
    cache_misses: int = Field(default=0, description="Number of cache misses")
    total_requests: int = Field(default=0, description="Total requests")
    hit_rate: float = Field(default=0.0, description="Cache hit rate (0.0-1.0)")

    model_config = ConfigDict(extra="allow")

    def __eq__(self, other):
        """Support comparison with dicts for backward compatibility."""
        if isinstance(other, dict):
            # Only compare fields that exist in the dict
            self_dict = self.model_dump()
            for key in list(self_dict.keys()):
                if key not in other:
                    # Remove fields from self_dict that aren't in other
                    del self_dict[key]
            return self_dict == other
        return super().__eq__(other)


class StorageStats(BaseModel):
    """Storage provider statistics."""

    provider: Optional[str] = Field(None, description="Storage provider type")
    bucket: Optional[str] = Field(None, description="Bucket/container name")
    total_artifacts: Optional[int] = Field(None, description="Total artifacts stored")
    total_bytes: Optional[int] = Field(None, description="Total bytes stored")

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, key: str) -> Any:
        """Support dict-style access for backwards compatibility."""
        try:
            return getattr(self, key)
        except AttributeError:
            # Check in extra fields
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __eq__(self, other):
        """Support comparison with dicts for backward compatibility."""
        if isinstance(other, dict):
            # Check if all non-None fields match or if comparing with empty dict
            if not other:  # Empty dict comparison
                return all(
                    v is None
                    for v in [
                        self.provider,
                        self.bucket,
                        self.total_artifacts,
                        self.total_bytes,
                    ]
                )
            # Only compare fields that exist in the dict
            self_dict = self.model_dump()
            for key in list(self_dict.keys()):
                if key not in other:
                    # Remove fields from self_dict that aren't in other
                    del self_dict[key]
            return self_dict == other
        return super().__eq__(other)


class StatsResponse(BaseModel):
    """
    Comprehensive statistics response.

    Provides statistics for both storage and session management.
    """

    storage_provider: str = Field(description="Storage provider type")
    session_provider: str = Field(description="Session provider type")
    bucket: str = Field(description="Bucket/container name")
    sandbox_id: str = Field(description="Sandbox identifier")
    session_manager: SessionStats = Field(
        default_factory=SessionStats, description="Session manager stats"
    )
    storage_stats: StorageStats = Field(
        default_factory=StorageStats,  # type: ignore[arg-type]
        description="Storage stats",
    )
    # Additional backward compatibility fields
    total_artifacts: Optional[int] = Field(
        None, description="Total artifacts (backward compat)"
    )
    total_bytes: Optional[int] = Field(
        None, description="Total bytes (backward compat)"
    )

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            # Check in extra fields
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator for backward compatibility."""
        try:
            getattr(self, key)
            return True
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            return extra is not None and key in extra

    def keys(self):
        """Support dict.keys() for backwards compatibility."""
        return self.model_dump().keys()

    def values(self):
        """Support dict.values() for backwards compatibility."""
        return self.model_dump().values()

    def items(self):
        """Support dict.items() for backwards compatibility."""
        return self.model_dump().items()


class SessionInfo(BaseModel):
    """
    Session information response.

    Provides details about a specific session.
    """

    session_id: str = Field(description="Session identifier")
    sandbox_id: str = Field(description="Sandbox identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    expires_at: Optional[str] = Field(
        None, description="Expiration timestamp (ISO 8601)"
    )
    ttl_hours: Optional[int] = Field(None, description="Time-to-live in hours")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Custom session metadata"
    )

    model_config = ConfigDict(extra="allow")

    def __eq__(self, other):
        """Support comparison with dicts for backward compatibility."""
        if isinstance(other, dict):
            # Only compare fields that exist in the dict
            self_dict = self.model_dump()
            for key in list(self_dict.keys()):
                if key not in other:
                    # Remove fields from self_dict that aren't in other
                    del self_dict[key]
            return self_dict == other
        return super().__eq__(other)

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        """Support dict.keys() for backwards compatibility."""
        return self.model_dump().keys()

    def values(self):
        """Support dict.values() for backwards compatibility."""
        return self.model_dump().values()

    def items(self):
        """Support dict.items() for backwards compatibility."""
        return self.model_dump().items()


class SandboxInfo(BaseModel):
    """
    Sandbox information response.

    Provides comprehensive information about the sandbox.
    """

    sandbox_id: str = Field(description="Sandbox identifier")
    bucket: str = Field(description="Storage bucket name")
    storage_provider: str = Field(description="Storage provider type")
    session_provider: str = Field(description="Session provider type")
    session_ttl_hours: int = Field(description="Default session TTL in hours")
    max_retries: int = Field(description="Maximum retry attempts")
    grid_prefix_pattern: str = Field(description="Grid path pattern")
    created_at: str = Field(description="Timestamp when info was retrieved (ISO 8601)")
    session_stats: SessionStats = Field(
        default_factory=SessionStats, description="Session stats"
    )
    storage_stats: StorageStats = Field(
        default_factory=StorageStats,  # type: ignore[arg-type]
        description="Storage stats",
    )
    closed: bool = Field(default=False, description="Whether the store is closed")

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        """Support 'in' operator for backward compatibility."""
        try:
            getattr(self, key)
            return True
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            return extra is not None and key in extra

    def keys(self):
        """Support dict.keys() for backwards compatibility."""
        return self.model_dump().keys()

    def values(self):
        """Support dict.values() for backwards compatibility."""
        return self.model_dump().values()

    def items(self):
        """Support dict.items() for backwards compatibility."""
        return self.model_dump().items()


class PresignedUploadResponse(BaseModel):
    """
    Response from presigned upload URL generation.

    Contains the presigned URL and artifact ID for client-side uploads.
    """

    upload_url: str = Field(description="Presigned upload URL")
    artifact_id: str = Field(description="Artifact identifier")
    expires_in: int = Field(description="URL expiration time in seconds")

    model_config = ConfigDict(extra="allow")


class MultipartUploadInitResponse(BaseModel):
    """
    Response from multipart upload initiation.

    Contains all necessary information to continue the multipart upload.
    """

    upload_id: str = Field(description="Multipart upload identifier")
    artifact_id: str = Field(description="Artifact identifier")
    key: str = Field(description="Storage key (grid path)")
    session_id: str = Field(description="Session identifier")
    expires_in: int = Field(description="Upload window in seconds")

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class UpdateMetadataResponse(BaseModel):
    """
    Response from metadata update operation.

    Returns the updated metadata.
    """

    artifact_id: str = Field(description="Artifact identifier")
    updated_at: str = Field(description="Update timestamp (ISO 8601)")
    summary: Optional[str] = Field(None, description="Updated summary")
    meta: Dict[str, Any] = Field(default_factory=dict, description="Updated metadata")

    model_config = ConfigDict(extra="allow")

    # Backwards compatibility: dict-like access
    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class BatchStoreResponse(BaseModel):
    """
    Response from batch store operation.

    Contains list of artifact IDs (or None for failed uploads).
    """

    artifact_ids: List[Optional[str]] = Field(
        description="List of artifact IDs (None if failed)"
    )
    total: int = Field(description="Total items in batch")
    successful: int = Field(description="Number of successful uploads")
    failed: int = Field(description="Number of failed uploads")

    model_config = ConfigDict(extra="allow")


# Type aliases for convenience
ArtifactID = str
SessionID = str
SandboxID = str
UserID = str
WorkspaceID = str


# ============================================================================
# Unified Namespace Models (Clean API)
# ============================================================================


NamespaceID = str


class NamespaceInfo(BaseModel):
    """
    Unified namespace information (clean API).

    A namespace is a VFS-backed storage unit that can be:
    - BLOB: Single-file namespace (artifact/blob storage at /_data)
    - WORKSPACE: Multi-file namespace (full directory tree)

    Both types use the same grid architecture and session management.
    """

    namespace_id: str = Field(description="Namespace identifier")
    type: NamespaceType = Field(description="Namespace type (blob or workspace)")
    name: Optional[str] = Field(
        None, description="Namespace name (required for workspaces)"
    )

    provider_type: str = Field(
        description="Storage provider (vfs-memory, vfs-filesystem, etc.)"
    )
    scope: StorageScope = Field(description="Storage scope (session, user, sandbox)")

    session_id: str = Field(description="Session identifier")
    sandbox_id: str = Field(description="Sandbox identifier")
    user_id: Optional[str] = Field(None, description="User identifier (for user scope)")
    owner_id: Optional[str] = Field(
        None, description="Owner ID (user_id for user scope)"
    )

    created_at: str = Field(description="Creation timestamp (ISO 8601)")
    expires_at: Optional[str] = Field(
        None, description="Expiration timestamp (ISO 8601)"
    )
    ttl_seconds: int = Field(description="Time-to-live in seconds")

    grid_path: str = Field(description="Grid storage path")
    current_path: str = Field(default="/", description="Current working directory")

    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Custom metadata"
    )

    model_config = ConfigDict(extra="allow")


# ============================================================================
# Workspace Models (Legacy API - backward compatibility)
# ============================================================================


class WorkspaceInfo(BaseModel):
    """
    Workspace information model.

    Workspaces are VFS-backed file collections with same scoping as artifacts.
    """

    workspace_id: str = Field(description="Workspace identifier")
    name: str = Field(description="Workspace name")
    provider_type: str = Field(
        description="Storage provider (vfs-memory, vfs-filesystem, etc.)"
    )
    scope: StorageScope = Field(description="Storage scope (session, user, sandbox)")
    session_id: str = Field(description="Session identifier")
    sandbox_id: str = Field(description="Sandbox identifier")
    user_id: Optional[str] = Field(None, description="User identifier (for user scope)")
    owner_id: Optional[str] = Field(
        None, description="Owner ID (user_id for user scope)"
    )

    created_at: str = Field(description="Creation timestamp (ISO 8601)")
    expires_at: Optional[str] = Field(
        None, description="Expiration timestamp (ISO 8601)"
    )
    ttl_seconds: int = Field(description="Time-to-live in seconds")

    grid_path: str = Field(description="Grid storage path")
    current_path: str = Field(default="/", description="Current working directory")

    mount_point: Optional[str] = Field(
        None, description="FUSE mount point (if mounted)"
    )
    is_mounted: bool = Field(default=False, description="Whether workspace is mounted")

    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Custom metadata"
    )

    model_config = ConfigDict(extra="allow")


class CheckpointInfo(BaseModel):
    """
    Checkpoint (snapshot) information.

    Checkpoints capture workspace state for restore.
    """

    checkpoint_id: str = Field(description="Checkpoint identifier")
    workspace_id: str = Field(description="Associated workspace ID")
    name: Optional[str] = Field(None, description="Checkpoint name")
    description: str = Field(description="Checkpoint description")
    created_at: str = Field(description="Creation timestamp (ISO 8601)")
    stats: Dict[str, Any] = Field(
        default_factory=dict, description="Checkpoint statistics"
    )

    model_config = ConfigDict(extra="allow")


__all__ = [
    # Enums
    "StorageScope",
    "StorageProvider",
    "SessionProvider",
    "OperationStatus",
    "NamespaceType",  # NEW - unified VFS
    # Constants
    "DEFAULT_TTL",
    "DEFAULT_PRESIGN_EXPIRES",
    "DEFAULT_SESSION_TTL_HOURS",
    "DEFAULT_BUCKET",
    "DEFAULT_SANDBOX_PREFIX",
    # Response Models
    "ProviderStatus",
    "ValidationResponse",
    "SessionStats",
    "StorageStats",
    "StatsResponse",
    "SessionInfo",
    "SandboxInfo",
    "PresignedUploadResponse",
    "MultipartUploadInitResponse",
    "UpdateMetadataResponse",
    "BatchStoreResponse",
    # Type Aliases
    "ArtifactID",
    "SessionID",
    "SandboxID",
    "UserID",
    "WorkspaceID",
    "NamespaceID",  # NEW - unified VFS
    # Unified Namespace Models (Clean API)
    "NamespaceInfo",  # NEW - unified VFS
    # Workspace Models (Legacy API)
    "WorkspaceInfo",
    "CheckpointInfo",
]
