# -*- coding: utf-8 -*-
# chuk_artifacts/provider_factory.py
"""
Resolve the storage back-end requested via **ARTIFACT_PROVIDER**.

Built-in providers
──────────────────
• **memory** (default) - in-process, non-persistent store (unit tests, demos)
• **fs**, **filesystem** - local filesystem rooted at `$ARTIFACT_FS_ROOT`
• **s3** - plain AWS or any S3-compatible endpoint
• **ibm_cos** - IBM COS, HMAC credentials (Signature V2)

Any other value is resolved dynamically as
`chuk_artifacts.providers.<name>.factory()`.
"""

from __future__ import annotations

import os
from importlib import import_module
from typing import Callable, AsyncContextManager

__all__ = ["factory_for_env"]


# ──────────────────────────────────────────────────────────────────
# Public factory selector
# ──────────────────────────────────────────────────────────────────


def factory_for_env() -> Callable[[], AsyncContextManager]:
    """Return a provider-specific factory based on `$ARTIFACT_PROVIDER`."""

    provider = os.getenv("ARTIFACT_PROVIDER", "memory").lower().strip()

    # Fast paths for the built-ins ------------------------------------------------
    # VFS-backed providers (new unified approach)
    if provider in ("vfs", "vfs-memory", "vfs_memory"):
        from .providers import vfs_adapter

        return vfs_adapter.factory(provider="memory")

    if provider in ("vfs-filesystem", "vfs_filesystem", "vfs-fs", "vfs_fs"):
        from .providers import vfs_adapter

        root_path = os.getenv("ARTIFACT_FS_ROOT", "/tmp/artifacts")  # nosec B108
        return vfs_adapter.factory(provider="filesystem", root_path=root_path)

    if provider in ("vfs-s3", "vfs_s3"):
        from .providers import vfs_adapter

        return vfs_adapter.factory(
            provider="s3",
            bucket_name=os.getenv("ARTIFACT_BUCKET", "artifacts"),
        )

    if provider in ("vfs-sqlite", "vfs_sqlite"):
        from .providers import vfs_adapter

        db_path = os.getenv("ARTIFACT_SQLITE_PATH", "artifacts.db")
        return vfs_adapter.factory(provider="sqlite", db_path=db_path)

    # Legacy providers (kept for backward compatibility)
    # Memory first as it's the default
    if provider in ("memory", "mem", "inmemory"):
        from .providers import memory

        return memory.factory()

    if provider in ("fs", "filesystem"):
        from .providers import filesystem

        return filesystem.factory()

    if provider == "s3":
        from .providers import s3

        return s3.factory()

    if provider == "ibm_cos":
        from .providers import ibm_cos

        return ibm_cos.factory()  # returns the zero-arg factory callable

    # ---------------------------------------------------------------------------
    # Fallback: dynamic lookup – allows user-supplied provider implementations.
    # ---------------------------------------------------------------------------
    try:
        mod = import_module(f"chuk_artifacts.providers.{provider}")
    except ModuleNotFoundError as exc:
        # Provide helpful error message with available providers
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
            f"Unknown storage provider '{provider}'. "
            f"Available providers: {', '.join(available)}"
        ) from exc

    if not hasattr(mod, "factory"):
        raise AttributeError(f"Provider '{provider}' lacks a factory() function")
    # For dynamic providers, call factory() to get the actual factory function
    factory_func = mod.factory
    if callable(factory_func):
        # If it's a function that returns a factory, call it
        try:
            return factory_func()  # type: ignore[no-any-return]
        except TypeError:
            # If it's already the factory function, return it directly
            return factory_func  # type: ignore[no-any-return]
    return factory_func  # type: ignore[no-any-return]
