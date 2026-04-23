# -*- coding: utf-8 -*-
# chuk_artifacts/namespace.py
"""
Unified namespace operations for chuk-artifacts.

Everything is VFS - both blobs and workspaces are VFS-backed namespaces with
the same session/grid architecture.

Clean API Design:
- create_namespace(type=BLOB|WORKSPACE)
- write_namespace(namespace_id, data, path)
- read_namespace(namespace_id, path)
- get_namespace_vfs(namespace_id)
- checkpoint_namespace(namespace_id)
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from chuk_virtual_fs import AsyncVirtualFileSystem
from chuk_virtual_fs.snapshot_manager import AsyncSnapshotManager

from .exceptions import SessionError
from .types import CheckpointInfo, NamespaceInfo, NamespaceType, StorageScope

if TYPE_CHECKING:
    from .store import ArtifactStore

logger = logging.getLogger(__name__)


class NamespaceOperations:
    """
    Unified VFS-backed namespace operations.

    Everything is VFS:
    - BLOB namespaces: Single file at /_data with metadata at /_meta.json
    - WORKSPACE namespaces: Full directory tree with metadata at /.workspace/meta.json

    Both use the same grid architecture: grid/{sandbox}/{session|user}/{namespace_id}/
    """

    def __init__(self, store: "ArtifactStore"):
        """
        Initialize namespace operations.

        Args:
            store: Parent ArtifactStore instance
        """
        self.store = store

        # Namespace storage: {namespace_id: (vfs, info)}
        self._namespaces: Dict[str, tuple[AsyncVirtualFileSystem, NamespaceInfo]] = {}

        # Per-session current namespace: {session_id: namespace_id}
        self._session_current: Dict[str, str] = {}

        # Checkpoint managers: {namespace_id: AsyncSnapshotManager}
        self._snapshot_managers: Dict[str, AsyncSnapshotManager] = {}

        self._lock = asyncio.Lock()

        logger.debug("NamespaceOperations initialized (everything is VFS)")

    async def create_namespace(
        self,
        type: NamespaceType,
        name: Optional[str] = None,
        scope: StorageScope = StorageScope.SESSION,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        provider_type: str = "vfs-memory",
        provider_config: Optional[Dict[str, Any]] = None,
        ttl_hours: int = 24,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NamespaceInfo:
        """
        Create a new namespace (blob or workspace).

        Args:
            type: Namespace type (BLOB or WORKSPACE)
            name: Namespace name (optional for blobs, recommended for workspaces)
            scope: Storage scope (SESSION, USER, or SANDBOX)
            session_id: Session ID (auto-allocated if not provided)
            user_id: User ID (required for USER scope)
            provider_type: VFS provider (vfs-memory, vfs-filesystem, vfs-sqlite, vfs-s3)
            provider_config: Provider-specific configuration
            ttl_hours: TTL for session-scoped namespaces
            metadata: Custom metadata

        Returns:
            NamespaceInfo for the created namespace

        Raises:
            ValueError: If namespace already exists or invalid parameters
            SessionError: If session validation fails
        """
        async with self._lock:
            # 1. Allocate/validate session using store's session manager
            if session_id is None:
                session_id = await self.store._session_manager.allocate_session(
                    user_id=user_id, ttl_hours=ttl_hours
                )
            else:
                valid = await self.store._session_manager.validate_session(session_id)
                if not valid:
                    raise SessionError(f"Invalid session: {session_id}")

            # 2. Validate scope requirements
            if scope == StorageScope.USER and not user_id:
                raise ValueError("user_id required for USER scope")

            # 3. Generate namespace ID
            namespace_id = f"ns-{uuid.uuid4().hex[:12]}"

            # 4. Build grid path
            grid_path = self._build_grid_path(
                namespace_id, type, name, scope, session_id, user_id
            )

            # 5. Check uniqueness
            if namespace_id in self._namespaces:
                raise ValueError(f"Namespace already exists: {namespace_id}")

            # 6. Create VFS provider
            config = provider_config or {}

            # Map provider type to actual provider name
            provider_name = provider_type.replace("vfs-", "")

            if provider_name == "filesystem":
                # Use grid path for filesystem storage
                if "root_path" not in config:
                    _vfs_root = os.environ.get("CHUK_VFS_TMP_ROOT", tempfile.gettempdir())
                    config["root_path"] = f"{_vfs_root}/vfs-namespaces/{grid_path}"
            elif provider_name == "sqlite":
                if "db_path" not in config:
                    _vfs_root = os.environ.get("CHUK_VFS_TMP_ROOT", tempfile.gettempdir())
                    config["db_path"] = f"{_vfs_root}/vfs-namespaces/{namespace_id}.db"

            # 7. Create VFS
            vfs = AsyncVirtualFileSystem(provider_name, **config)
            await vfs.initialize()

            # 8. Initialize namespace structure
            if type == NamespaceType.BLOB:
                # For blobs: create placeholder /_data and /_meta.json
                await vfs.write_file("/_meta.json", b"{}")
            else:
                # For workspaces: create /.workspace directory
                await vfs.mkdir("/.workspace")
                await vfs.write_file("/.workspace/meta.json", b"{}")

            # 9. Calculate expiration
            ttl_seconds = ttl_hours * 3600 if scope == StorageScope.SESSION else 0
            expires_at = None
            if ttl_seconds > 0:
                expires_at = (
                    (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds))
                    .isoformat()
                    .replace("+00:00", "Z")
                )

            # 10. Create namespace info
            info = NamespaceInfo(
                namespace_id=namespace_id,
                type=type,
                name=name,
                provider_type=provider_type,
                scope=scope,
                session_id=session_id,
                sandbox_id=self.store._session_manager.sandbox_id,
                user_id=user_id,
                owner_id=user_id if scope == StorageScope.USER else None,
                created_at=datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                expires_at=expires_at,
                ttl_seconds=ttl_seconds,
                grid_path=grid_path,
                current_path="/",
                metadata=metadata or {},
            )

            # 11. Store namespace
            self._namespaces[namespace_id] = (vfs, info)

            # 12. Set as current for this session
            self._session_current[session_id] = namespace_id

            logger.info(
                "Created %s namespace: %s (scope=%s, session=%s)",
                type.value,
                namespace_id,
                scope.value,
                session_id,
            )

            return info

    def _build_grid_path(
        self,
        namespace_id: str,
        type: NamespaceType,
        name: Optional[str],
        scope: StorageScope,
        session_id: str,
        user_id: Optional[str],
    ) -> str:
        """
        Build grid path for namespace.

        Pattern: grid/{sandbox}/{scope_prefix}/{namespace_id}

        Args:
            namespace_id: Namespace ID
            type: Namespace type
            name: Namespace name
            scope: Storage scope
            session_id: Session ID
            user_id: User ID (for USER scope)

        Returns:
            Grid path string
        """
        sandbox_id = self.store._session_manager.sandbox_id

        if scope == StorageScope.SESSION:
            scope_prefix = session_id
        elif scope == StorageScope.USER:
            if not user_id:
                raise ValueError("user_id required for USER scope")
            scope_prefix = f"user-{user_id}"
        else:  # SANDBOX
            scope_prefix = "shared"

        return f"grid/{sandbox_id}/{scope_prefix}/{namespace_id}"

    async def write_namespace(
        self,
        namespace_id: str,
        data: bytes,
        path: Optional[str] = None,
        mime: Optional[str] = None,
    ) -> None:
        """
        Write data to namespace.

        For BLOB namespaces:
        - path=None: writes to /_data
        - Updates /_meta.json with mime type and metadata

        For WORKSPACE namespaces:
        - path required: writes to specified file path
        - Creates parent directories as needed

        Args:
            namespace_id: Namespace ID
            data: Data to write
            path: File path (None = /_data for blobs, required for workspaces)
            mime: MIME type (for blobs)

        Raises:
            ValueError: If namespace not found or invalid path
        """
        vfs, info = self._get_namespace(namespace_id)

        if info.type == NamespaceType.BLOB:
            # For blobs: write to /_data
            target_path = "/_data"
            await vfs.write_file(target_path, data)

            # Update metadata
            if mime:
                import json

                meta = {"mime": mime, "size": len(data)}
                await vfs.write_file("/_meta.json", json.dumps(meta).encode())

            logger.debug("Wrote %d bytes to blob namespace %s", len(data), namespace_id)

        else:  # WORKSPACE
            if not path:
                raise ValueError("path required for workspace namespaces")

            # Ensure parent directory exists
            parent = str(Path(path).parent)
            if parent != "/" and parent != ".":
                try:
                    await vfs.mkdir(parent)
                except Exception:
                    pass  # Directory may already exist

            # Write file
            await vfs.write_file(path, data)

            logger.debug(
                "Wrote %d bytes to workspace namespace %s at %s",
                len(data),
                namespace_id,
                path,
            )

    async def read_namespace(
        self, namespace_id: str, path: Optional[str] = None
    ) -> bytes:
        """
        Read data from namespace.

        For BLOB namespaces:
        - path=None: reads from /_data

        For WORKSPACE namespaces:
        - path required: reads from specified file path

        Args:
            namespace_id: Namespace ID
            path: File path (None = /_data for blobs, required for workspaces)

        Returns:
            File contents as bytes

        Raises:
            ValueError: If namespace not found or invalid path
        """
        vfs, info = self._get_namespace(namespace_id)

        if info.type == NamespaceType.BLOB:
            # For blobs: read from /_data
            target_path = "/_data"
            raw = await vfs.read_file(target_path)
            data = raw if isinstance(raw, bytes) else (raw.encode() if isinstance(raw, str) else b"")
            logger.debug(
                "Read %d bytes from blob namespace %s", len(data), namespace_id
            )
            return data

        else:  # WORKSPACE
            if not path:
                raise ValueError("path required for workspace namespaces")

            raw = await vfs.read_file(path)
            data = raw if isinstance(raw, bytes) else (raw.encode() if isinstance(raw, str) else b"")
            logger.debug(
                "Read %d bytes from workspace namespace %s at %s",
                len(data),
                namespace_id,
                path,
            )
            return data

    def get_namespace_vfs(self, namespace_id: str) -> AsyncVirtualFileSystem:
        """
        Get VFS instance for namespace.

        Args:
            namespace_id: Namespace ID

        Returns:
            AsyncVirtualFileSystem instance

        Raises:
            ValueError: If namespace not found
        """
        vfs, _ = self._get_namespace(namespace_id)
        return vfs

    def get_namespace_info(
        self, namespace_id: str, session_id: Optional[str] = None
    ) -> NamespaceInfo:
        """
        Get namespace information.

        Args:
            namespace_id: Namespace ID
            session_id: Session ID for access control

        Returns:
            NamespaceInfo

        Raises:
            ValueError: If namespace not found
            PermissionError: If session doesn't have access
        """
        _, info = self._get_namespace(namespace_id)

        # Access control
        if session_id and info.scope == StorageScope.SESSION:
            if info.session_id != session_id:
                raise PermissionError(f"Access denied to namespace: {namespace_id}")

        return info

    def list_namespaces(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        type: Optional[NamespaceType] = None,
        include_all_scopes: bool = True,
    ) -> list[NamespaceInfo]:
        """
        List accessible namespaces.

        Args:
            session_id: Session ID (returns session-scoped namespaces)
            user_id: User ID (returns user-scoped namespaces)
            type: Filter by namespace type (BLOB or WORKSPACE)
            include_all_scopes: Include sandbox-scoped namespaces

        Returns:
            List of NamespaceInfo objects
        """
        accessible = []

        for ns_id, (_, info) in self._namespaces.items():
            # Type filter
            if type and info.type != type:
                continue

            # Session-scoped: must match session_id
            if info.scope == StorageScope.SESSION:
                if session_id and info.session_id == session_id:
                    accessible.append(info)

            # User-scoped: must match user_id
            elif info.scope == StorageScope.USER:
                if user_id and info.user_id == user_id:
                    accessible.append(info)

            # Sandbox-scoped: always accessible if requested
            elif info.scope == StorageScope.SANDBOX:
                if include_all_scopes:
                    accessible.append(info)

        return accessible

    async def destroy_namespace(
        self, namespace_id: str, session_id: Optional[str] = None
    ) -> None:
        """
        Destroy a namespace.

        Args:
            namespace_id: Namespace ID to destroy
            session_id: Session ID for access control

        Raises:
            ValueError: If namespace not found
            PermissionError: If session doesn't have access
        """
        async with self._lock:
            vfs, info = self._get_namespace(namespace_id)

            # Access control check
            if session_id and info.session_id != session_id:
                # Allow if user owns namespace
                if not (info.scope == StorageScope.USER and info.user_id):
                    raise PermissionError(f"Access denied to namespace: {namespace_id}")

            # Cleanup VFS
            if vfs.provider and hasattr(vfs.provider, "cleanup"):
                await vfs.provider.cleanup()

            # Remove snapshot manager
            if namespace_id in self._snapshot_managers:
                del self._snapshot_managers[namespace_id]

            # Remove from storage
            del self._namespaces[namespace_id]

            # Remove from session current if set
            if info.session_id in self._session_current:
                if self._session_current[info.session_id] == namespace_id:
                    del self._session_current[info.session_id]

            logger.info("Destroyed namespace: %s", namespace_id)

    # ========================================================================
    # Checkpoint Operations
    # ========================================================================

    def _get_snapshot_manager(self, namespace_id: str) -> AsyncSnapshotManager:
        """Get or create snapshot manager for namespace."""
        if namespace_id not in self._snapshot_managers:
            vfs = self.get_namespace_vfs(namespace_id)
            self._snapshot_managers[namespace_id] = AsyncSnapshotManager(vfs)

        return self._snapshot_managers[namespace_id]

    async def checkpoint_namespace(
        self, namespace_id: str, name: Optional[str] = None, description: str = ""
    ) -> CheckpointInfo:
        """
        Create checkpoint of namespace state (blob or workspace).

        Args:
            namespace_id: Namespace ID
            name: Optional checkpoint name
            description: Checkpoint description

        Returns:
            CheckpointInfo

        Raises:
            ValueError: If namespace not found
        """
        snapshot_mgr = self._get_snapshot_manager(namespace_id)

        # Create snapshot
        checkpoint_id = await snapshot_mgr.create_snapshot(
            name=name, description=description
        )

        # Get snapshot metadata
        snapshots = snapshot_mgr.list_snapshots()
        snapshot_meta = next((s for s in snapshots if s["name"] == checkpoint_id), None)

        if snapshot_meta is None:
            raise RuntimeError(f"Failed to create checkpoint: {checkpoint_id}")

        return CheckpointInfo(
            checkpoint_id=checkpoint_id,
            workspace_id=namespace_id,  # Keep workspace_id for backward compat
            name=name,
            description=snapshot_meta.get("description", ""),
            created_at=datetime.fromtimestamp(snapshot_meta["created"], tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            stats=snapshot_meta.get("stats", {}),
        )

    async def restore_namespace(self, namespace_id: str, checkpoint_id: str) -> bool:
        """
        Restore namespace to checkpoint.

        Args:
            namespace_id: Namespace ID
            checkpoint_id: Checkpoint ID

        Returns:
            True if successful

        Raises:
            ValueError: If namespace or checkpoint not found
        """
        snapshot_mgr = self._get_snapshot_manager(namespace_id)
        success = await snapshot_mgr.restore_snapshot(checkpoint_id)

        if not success:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        logger.info(
            "Restored namespace %s to checkpoint %s", namespace_id, checkpoint_id
        )

        return success

    async def list_checkpoints(self, namespace_id: str) -> list[CheckpointInfo]:
        """
        List checkpoints for namespace.

        Args:
            namespace_id: Namespace ID

        Returns:
            List of CheckpointInfo

        Raises:
            ValueError: If namespace not found
        """
        snapshot_mgr = self._get_snapshot_manager(namespace_id)
        snapshots = snapshot_mgr.list_snapshots()

        checkpoints = []
        for snapshot in snapshots:
            checkpoint = CheckpointInfo(
                checkpoint_id=snapshot["name"],
                workspace_id=namespace_id,  # Keep workspace_id for backward compat
                name=snapshot.get("name"),
                description=snapshot.get("description", ""),
                created_at=datetime.fromtimestamp(snapshot["created"], tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                stats=snapshot.get("stats", {}),
            )
            checkpoints.append(checkpoint)

        return checkpoints

    async def delete_checkpoint(self, namespace_id: str, checkpoint_id: str) -> bool:
        """
        Delete a checkpoint.

        Args:
            namespace_id: Namespace ID
            checkpoint_id: Checkpoint ID

        Returns:
            True if successful

        Raises:
            ValueError: If namespace or checkpoint not found
        """
        snapshot_mgr = self._get_snapshot_manager(namespace_id)
        success = snapshot_mgr.delete_snapshot(checkpoint_id)

        if not success:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")

        logger.info(
            "Deleted checkpoint %s from namespace %s", checkpoint_id, namespace_id
        )

        return success

    # ========================================================================
    # Internal Helpers
    # ========================================================================

    def _get_namespace(
        self, namespace_id: str
    ) -> tuple[AsyncVirtualFileSystem, NamespaceInfo]:
        """Get namespace VFS and info, raising if not found."""
        if namespace_id not in self._namespaces:
            raise ValueError(f"Namespace not found: {namespace_id}")
        return self._namespaces[namespace_id]
