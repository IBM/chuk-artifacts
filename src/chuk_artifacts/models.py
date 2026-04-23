# -*- coding: utf-8 -*-
# chuk_artifacts/models.py
import warnings
from typing import (
    Any,
    Dict,
    ItemsView,
    KeysView,
    Optional,
    AsyncIterator,
    Callable,
    ValuesView,
)
from pydantic import BaseModel, Field, ConfigDict, field_validator
from .types import StorageScope


class ArtifactEnvelope(BaseModel):
    """
    A tiny, model-friendly wrapper describing a stored artefact.

    The *bytes*, *mime_type*, etc. let the UI reason about the file
    without ever uploading the raw payload into the chat context.
    """

    success: bool = True
    artifact_id: str  # opaque handle for look-ups
    mime_type: str  # e.g. "image/png", "text/csv"
    bytes: int  # size on disk
    summary: str  # human-readable description / alt
    meta: Dict[str, Any] = Field(default_factory=dict)

    # Pydantic V2 configuration using ConfigDict
    model_config = ConfigDict(extra="allow")  # future-proof: lets tools add keys


class ArtifactMetadata(BaseModel):
    """
    Complete metadata record for a stored artifact.

    This is the canonical structure stored in the session provider (Redis/memory)
    and used throughout the system for artifact tracking.

    Supports both attribute access (metadata.key) and dict-style access (metadata["key"])
    for backwards compatibility.

    Storage Scopes:
    - session: Ephemeral, tied to a session (default, 15min-24h TTL)
    - user: Persistent, tied to a user (long/no TTL)
    - sandbox: Shared across sandbox (long/no TTL)
    """

    artifact_id: str
    session_id: str
    sandbox_id: str
    key: str  # Storage key (grid path)
    mime: str  # MIME type
    summary: str  # Human-readable description
    meta: Dict[str, Any] = Field(default_factory=dict)  # User-defined metadata
    filename: Optional[str] = None
    bytes: int = Field(ge=0)  # File size in bytes (must be >= 0)
    sha256: Optional[str] = None  # SHA-256 hash (optional for presigned uploads)
    stored_at: str  # ISO 8601 datetime string
    ttl: int = Field(gt=0)  # Time-to-live in seconds (must be > 0)
    storage_provider: str  # e.g., "s3", "filesystem", "memory"
    session_provider: str  # e.g., "redis", "memory"

    # Scope-based storage (Phase 1 expansion)
    scope: StorageScope = Field(
        default=StorageScope.SESSION,
        description="Storage scope: session (ephemeral), user (persistent), or sandbox (shared)",
    )
    owner_id: Optional[str] = Field(
        None,
        description="Owner identifier - user_id for user scope, None for session/sandbox scope",
    )

    # Optional fields for specific upload methods
    batch_operation: Optional[bool] = None
    batch_index: Optional[int] = None
    uploaded_via_presigned: Optional[bool] = None
    updated_at: Optional[str] = None  # ISO 8601 datetime string

    model_config = ConfigDict(
        extra="allow"
    )  # Allow additional fields for extensibility

    @field_validator("bytes")
    @classmethod
    def validate_bytes(cls, v: int) -> int:
        """Ensure bytes is non-negative."""
        if v < 0:
            raise ValueError("bytes must be non-negative")
        return v

    @field_validator("ttl")
    @classmethod
    def validate_ttl(cls, v: int) -> int:
        """Ensure TTL is positive."""
        if v <= 0:
            raise ValueError("ttl must be positive")
        return v

    # Backwards compatibility: dict-like access
    # Deprecated — use attribute access (metadata.key) instead.
    def __getitem__(self, key: str) -> Any:
        warnings.warn(
            "Dict-style access on ArtifactMetadata is deprecated; use attribute access instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return getattr(self, key)
        except AttributeError:
            extra = getattr(self, "__pydantic_extra__", None)
            if extra and key in extra:
                return extra[key]
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        warnings.warn(
            "Dict-style access on ArtifactMetadata is deprecated; use attribute access instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return getattr(self, key)
        except AttributeError:
            return default

    def keys(self) -> KeysView[str]:
        warnings.warn(
            "Dict-style access on ArtifactMetadata is deprecated; use model_dump() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.model_dump().keys()

    def values(self) -> ValuesView[Any]:
        warnings.warn(
            "Dict-style access on ArtifactMetadata is deprecated; use model_dump() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.model_dump().values()

    def items(self) -> ItemsView[str, Any]:
        warnings.warn(
            "Dict-style access on ArtifactMetadata is deprecated; use model_dump() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.model_dump().items()


class GridKeyComponents(BaseModel):
    """
    Parsed components of a grid storage key.

    Grid keys follow the pattern: grid/{sandbox_id}/{session_id}/{artifact_id}[/{subpath}]

    Supports both attribute access (components.sandbox_id) and dict-style access
    (components["sandbox_id"]) for backwards compatibility.
    """

    sandbox_id: str = Field(min_length=1, description="Sandbox identifier")
    session_id: str = Field(min_length=1, description="Session identifier")
    artifact_id: str = Field(min_length=1, description="Artifact identifier")
    subpath: Optional[str] = Field(None, description="Optional subpath within artifact")

    model_config = ConfigDict(frozen=True)  # Make immutable

    @field_validator("sandbox_id", "session_id", "artifact_id")
    @classmethod
    def validate_no_slashes(cls, v: str) -> str:
        """Ensure components don't contain slashes."""
        if "/" in v:
            raise ValueError(f"Grid component cannot contain '/': {v!r}")
        return v

    # Backwards compatibility: dict-like access
    # Deprecated — use attribute access (components.sandbox_id) instead.
    def __getitem__(self, key: str) -> Any:
        warnings.warn(
            "Dict-style access on GridKeyComponents is deprecated; use attribute access instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        warnings.warn(
            "Dict-style access on GridKeyComponents is deprecated; use attribute access instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        try:
            return getattr(self, key)
        except AttributeError:
            return default


class BatchStoreItem(BaseModel):
    """
    Input item for batch store operations.

    Defines the required structure for each item in a batch upload.
    """

    data: bytes = Field(description="Raw file data")
    mime: str = Field(min_length=1, description="MIME type (e.g., 'image/png')")
    summary: str = Field(description="Human-readable description")
    meta: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    filename: Optional[str] = Field(None, description="Optional filename")

    model_config = ConfigDict(arbitrary_types_allowed=True)  # Allow bytes type

    @field_validator("data")
    @classmethod
    def validate_data(cls, v: bytes) -> bytes:
        """Ensure data is not empty."""
        if len(v) == 0:
            raise ValueError("data cannot be empty")
        return v


class AccessContext(BaseModel):
    """
    Context for access control checks.

    Represents the identity of the requestor attempting to access an artifact.
    """

    user_id: Optional[str] = Field(None, description="User ID of the requestor")
    session_id: Optional[str] = Field(None, description="Session ID of the requestor")
    sandbox_id: str = Field(description="Sandbox ID (must match artifact's sandbox)")

    model_config = ConfigDict(frozen=True)  # Immutable for security


class StreamUploadRequest(BaseModel):
    """
    Parameters for streaming upload operations.

    Defines all parameters needed to perform a streaming upload with optional
    progress tracking.
    """

    data_stream: AsyncIterator[bytes] = Field(
        description="Async iterator yielding bytes chunks"
    )
    mime: str = Field(min_length=1, description="MIME type (e.g., 'video/mp4')")
    summary: str = Field(description="Human-readable description")
    meta: Optional[Dict[str, Any]] = Field(None, description="Optional custom metadata")
    filename: Optional[str] = Field(None, description="Optional filename")
    session_id: Optional[str] = Field(
        None, description="Session ID (auto-allocated if not provided)"
    )
    user_id: Optional[str] = Field(
        None, description="User ID (used for session allocation and user scope)"
    )
    ttl: int = Field(default=900, gt=0, description="Time-to-live in seconds")
    scope: StorageScope = Field(
        default=StorageScope.SESSION,
        description="Storage scope: session (ephemeral), user (persistent), or sandbox (shared)",
    )
    content_length: Optional[int] = Field(
        None, description="Total content length in bytes (if known)"
    )
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = Field(
        None, description="Callback function (bytes_processed, total_bytes)"
    )
    chunk_size: int = Field(
        default=65536, gt=0, description="Chunk size for reading (64KB default)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class StreamDownloadRequest(BaseModel):
    """
    Parameters for streaming download operations.

    Defines all parameters needed to perform a streaming download with optional
    progress tracking.
    """

    artifact_id: str = Field(min_length=1, description="ID of artifact to download")
    user_id: Optional[str] = Field(
        None,
        description="User ID for access control (required for user-scoped artifacts)",
    )
    session_id: Optional[str] = Field(
        None,
        description="Session ID for access control (optional for session-scoped artifacts)",
    )
    chunk_size: int = Field(
        default=65536, gt=0, description="Chunk size for streaming (64KB default)"
    )
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = Field(
        None, description="Callback function (bytes_processed, total_bytes)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class MultipartUploadInitRequest(BaseModel):
    """
    Parameters for initiating a multipart upload.

    Multipart uploads are ideal for large files (>5MB). The workflow:
    1. Initiate upload to get upload_id
    2. Upload parts (minimum 5MB except last part)
    3. Complete upload with part ETags

    Maximum: 10,000 parts per upload.
    """

    filename: str = Field(min_length=1, description="Name of file being uploaded")
    mime_type: str = Field(
        default="application/octet-stream", description="MIME type (e.g., 'video/mp4')"
    )
    user_id: Optional[str] = Field(
        default=None, description="User ID (for auto-generated session)"
    )
    session_id: Optional[str] = Field(default=None, description="Explicit session ID")
    scope: StorageScope = Field(
        default=StorageScope.SESSION,
        description="Storage scope: session (ephemeral), user (persistent), or sandbox (shared)",
    )
    ttl: int = Field(default=900, gt=0, description="Time-to-live in seconds")
    meta: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional custom metadata"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class MultipartUploadPart(BaseModel):
    """
    Represents an uploaded part in a multipart upload.

    After uploading each part via presigned URL, the ETag from the
    response headers must be collected and provided to complete the upload.
    """

    PartNumber: int = Field(ge=1, le=10000, description="Part number (1-10000)")
    ETag: str = Field(min_length=1, description="ETag from upload response headers")

    model_config = ConfigDict(frozen=True)  # Immutable once created


class MultipartUploadCompleteRequest(BaseModel):
    """
    Parameters for completing a multipart upload.

    After all parts have been uploaded, provide the list of parts
    with their ETags to finalize the upload.
    """

    upload_id: str = Field(min_length=1, description="Upload ID from initiate")
    parts: list[MultipartUploadPart] = Field(
        min_length=1, description="List of uploaded parts with ETags"
    )
    summary: str = Field(
        default="Multipart upload", description="Human-readable description"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)
