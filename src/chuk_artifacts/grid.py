# -*- coding: utf-8 -*-
# chuk_artifacts/grid.py
"""Utility helpers for grid-style paths.

Supports scope-based storage with different path patterns:
- Session: grid/{sandbox_id}/sessions/{session_id}/{artifact_id}[/{subpath}]
- User: grid/{sandbox_id}/users/{user_id}/{artifact_id}[/{subpath}]
- Sandbox: grid/{sandbox_id}/shared/{artifact_id}[/{subpath}]

Legacy pattern (backwards compatible):
- grid/{sandbox_id}/{session_id}/{artifact_id}[/{subpath}]

All components (sandbox_id, session_id, artifact_id) must be non-empty strings
to ensure proper grid organization and prevent path collisions.
"""

import mimetypes
from typing import Optional, Literal
from .models import GridKeyComponents

_ROOT = "grid"
_SCOPE_SESSION = "sessions"
_SCOPE_USER = "users"
_SCOPE_SANDBOX = "shared"

# Common MIME type to extension mappings
_MIME_TO_EXT = {
    # Images
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/x-icon": ".ico",
    # Documents
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/css": ".css",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/markdown": ".md",
    # Office
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    # Archives
    "application/zip": ".zip",
    "application/x-tar": ".tar",
    "application/gzip": ".gz",
    "application/x-7z-compressed": ".7z",
    "application/x-rar-compressed": ".rar",
    # Video
    "video/mp4": ".mp4",
    "video/mpeg": ".mpeg",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    # Audio
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/webm": ".weba",
    "audio/aac": ".aac",
    # Code
    "text/javascript": ".js",
    "application/javascript": ".js",
    "text/x-python": ".py",
    "application/x-python-code": ".py",
    "text/x-java": ".java",
    "text/x-c": ".c",
    "text/x-c++": ".cpp",
    "application/x-sh": ".sh",
    # Other
    "application/octet-stream": ".bin",
}


def get_extension_from_mime(mime_type: str, filename: Optional[str] = None) -> str:
    """
    Get file extension from MIME type or filename.

    Args:
        mime_type: MIME type string (e.g., "image/png")
        filename: Optional filename to extract extension from

    Returns:
        File extension with leading dot (e.g., ".png"), or empty string if unknown
    """
    # First, check if filename already has an extension
    if filename:
        import os

        _, ext = os.path.splitext(filename)
        if ext:
            return ext

    # Check our custom mapping
    mime_lower = mime_type.lower().strip()
    if mime_lower in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime_lower]

    # Fall back to mimetypes module
    ext = mimetypes.guess_extension(mime_type)
    if ext:
        return ext

    # No extension found
    return ""


class GridError(ValueError):
    """Raised when grid path operations encounter invalid input."""

    pass


def _validate_component(component: str, name: str) -> None:
    """Validate a grid path component."""
    if not isinstance(component, str):
        raise GridError(f"{name} must be a string, got {type(component).__name__}")
    if not component:
        raise GridError(f"{name} cannot be empty")
    if "/" in component:
        raise GridError(f"{name} cannot contain '/' characters: {component!r}")


def canonical_prefix(
    sandbox_id: str, session_id: str, use_legacy_format: bool = False
) -> str:
    """
    Generate canonical prefix for a sandbox/session combination.

    Args:
        sandbox_id: Non-empty sandbox identifier
        session_id: Non-empty session identifier
        use_legacy_format: If True, use legacy format (grid/{sandbox}/{session}/)
                          Default False (new scoped format: grid/{sandbox}/sessions/{session}/)

    Returns:
        Canonical prefix ending with '/'

    Raises:
        GridError: If any component is invalid

    Note:
        New format (default): grid/{sandbox}/sessions/{session}/
        Legacy format: grid/{sandbox}/{session}/
    """
    _validate_component(sandbox_id, "sandbox_id")
    _validate_component(session_id, "session_id")

    if use_legacy_format:
        return f"{_ROOT}/{sandbox_id}/{session_id}/"
    else:
        return f"{_ROOT}/{sandbox_id}/{_SCOPE_SESSION}/{session_id}/"


def artifact_key(
    sandbox_id: str,
    session_id: str,
    artifact_id: str,
    scope: Literal["session", "user", "sandbox"] = "session",
    owner_id: Optional[str] = None,
    use_legacy_session_format: bool = False,
    mime_type: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """
    Generate artifact key for grid storage with scope support and file extensions.

    Args:
        sandbox_id: Non-empty sandbox identifier
        session_id: Non-empty session identifier (used for session scope)
        artifact_id: Non-empty artifact identifier
        scope: Storage scope - "session" (default), "user", or "sandbox"
        owner_id: Owner ID for user-scoped artifacts (user_id)
        use_legacy_session_format: If True, use legacy path for session scope
                                   (grid/{sandbox}/{session}/{artifact}).
                                   Default False (new scoped format).
        mime_type: Optional MIME type to derive file extension from
        filename: Optional filename to extract extension from

    Returns:
        Grid artifact key following scope-based pattern with file extension

    Raises:
        GridError: If any component is invalid

    Examples:
        >>> artifact_key("sb1", "sess1", "art1", mime_type="image/png")
        'grid/sb1/sessions/sess1/art1.png'

        >>> artifact_key("sb1", "sess1", "art1", filename="photo.jpg")
        'grid/sb1/sessions/sess1/art1.jpg'

        >>> artifact_key("sb1", "sess1", "art1", use_legacy_session_format=True)
        'grid/sb1/sess1/art1'

        >>> artifact_key("sb1", "sess1", "art1", scope="user", owner_id="alice", mime_type="application/pdf")
        'grid/sb1/users/alice/art1.pdf'

        >>> artifact_key("sb1", "sess1", "art1", scope="sandbox", mime_type="text/plain")
        'grid/sb1/shared/art1.txt'

    Note:
        The parser (parse()) handles both legacy and new formats transparently,
        ensuring backward compatibility for reading existing artifacts.
    """
    _validate_component(sandbox_id, "sandbox_id")
    _validate_component(artifact_id, "artifact_id")

    # Get file extension if mime_type or filename provided
    extension = ""
    if mime_type or filename:
        extension = get_extension_from_mime(mime_type or "", filename)

    # Construct artifact_id with extension
    artifact_id_with_ext = artifact_id + extension

    if scope == "session":
        _validate_component(session_id, "session_id")
        # Backward compatibility: use legacy format by default
        if use_legacy_session_format:
            return f"{_ROOT}/{sandbox_id}/{session_id}/{artifact_id_with_ext}"
        else:
            return f"{_ROOT}/{sandbox_id}/{_SCOPE_SESSION}/{session_id}/{artifact_id_with_ext}"
    elif scope == "user":
        if not owner_id:
            raise GridError("owner_id (user_id) required for user-scoped artifacts")
        _validate_component(owner_id, "owner_id")
        return f"{_ROOT}/{sandbox_id}/{_SCOPE_USER}/{owner_id}/{artifact_id_with_ext}"
    elif scope == "sandbox":
        return f"{_ROOT}/{sandbox_id}/{_SCOPE_SANDBOX}/{artifact_id_with_ext}"
    else:
        raise GridError(
            f"Invalid scope: {scope!r}. Must be 'session', 'user', or 'sandbox'"
        )


def parse(key: str) -> Optional[GridKeyComponents]:
    """
    Parse a grid key into components.

    Supports both scope-based and legacy formats:
    - Scope-based: grid/{sandbox}/{scope_type}/{owner_or_session}/{artifact}[/{subpath}]
    - Legacy: grid/{sandbox}/{session}/{artifact}[/{subpath}]

    Args:
        key: Grid key to parse

    Returns:
        GridKeyComponents model with parsed components, or None if invalid

    Examples:
        >>> parse("grid/sandbox/sessions/session123/artifact")
        GridKeyComponents(sandbox_id='sandbox', session_id='session123', artifact_id='artifact', subpath=None)

        >>> parse("grid/sandbox/users/alice/artifact")
        GridKeyComponents(sandbox_id='sandbox', session_id='alice', artifact_id='artifact', subpath=None)

        >>> parse("grid/sandbox/shared/artifact")
        GridKeyComponents(sandbox_id='sandbox', session_id='shared', artifact_id='artifact', subpath=None)

        >>> parse("grid/sandbox/session/artifact")  # Legacy format
        GridKeyComponents(sandbox_id='sandbox', session_id='session', artifact_id='artifact', subpath=None)

        >>> parse("invalid/key")
        None
    """
    if not isinstance(key, str):
        return None

    parts = key.split("/")

    # Must start with correct root
    if len(parts) < 4 or parts[0] != _ROOT:
        return None

    sandbox_id = parts[1]
    if not sandbox_id:
        return None

    # Check for scope-based format (has scope type as 3rd component)
    scope_type = parts[2]

    if scope_type in (_SCOPE_SESSION, _SCOPE_USER, _SCOPE_SANDBOX):
        # Scope-based format: grid/{sandbox}/{scope_type}/{owner_or_session}/{artifact}
        if scope_type == _SCOPE_SANDBOX:
            # Sandbox scope: grid/{sandbox}/shared/{artifact}
            if len(parts) < 4:
                return None
            artifact_id = parts[3]
            session_id = "shared"  # Special marker for sandbox scope
            subpath_start = 4
        else:
            # Session or User scope: grid/{sandbox}/{scope}/{id}/{artifact}
            if len(parts) < 5:
                return None
            session_id = parts[3]  # session_id or user_id
            artifact_id = parts[4]
            subpath_start = 5
    else:
        # Legacy format: grid/{sandbox}/{session}/{artifact}
        if len(parts) < 4:
            return None
        session_id = parts[2]
        artifact_id = parts[3]
        subpath_start = 4

    # Validate that core components are non-empty
    if not sandbox_id or not session_id or not artifact_id:
        return None

    # Check for slashes in components (shouldn't happen after split, but be safe)
    if "/" in sandbox_id or "/" in session_id or "/" in artifact_id:
        return None

    # Handle subpath
    subpath = None
    if len(parts) > subpath_start:
        subpath_parts = parts[subpath_start:]
        subpath = "/".join(subpath_parts)
        # Convert empty subpath to None for consistency
        if subpath == "":
            subpath = None

    try:
        return GridKeyComponents(
            sandbox_id=sandbox_id,
            session_id=session_id,
            artifact_id=artifact_id,
            subpath=subpath,
        )
    except Exception:
        return None


def is_valid_grid_key(key: str) -> bool:
    """
    Check if a string is a valid grid key.

    Args:
        key: String to validate

    Returns:
        True if valid grid key, False otherwise
    """
    return parse(key) is not None


def validate_grid_key(key: str) -> GridKeyComponents:
    """
    Validate and parse a grid key, raising an exception if invalid.

    Args:
        key: Grid key to validate

    Returns:
        Parsed grid components as GridKeyComponents model

    Raises:
        GridError: If key is invalid
    """
    result = parse(key)
    if result is None:
        raise GridError(f"Invalid grid key: {key!r}")
    return result
