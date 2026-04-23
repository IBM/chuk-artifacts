#!/usr/bin/env python3
"""
Example 3: Unified "Everything is VFS" Architecture

This example demonstrates how blobs and workspaces are unified under the same
VFS architecture, sharing the same operations, grid structure, and session management.

Key Concepts:
- Both types use create_namespace()
- Both support checkpoints
- Both use the same grid architecture
- Both have direct VFS access
- Both support SESSION, USER, and SANDBOX scopes
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    store = ArtifactStore()

    print("=" * 70)
    print("UNIFIED 'EVERYTHING IS VFS' ARCHITECTURE")
    print("=" * 70)

    # ========================================================================
    # Part 1: Unified Creation API
    # ========================================================================
    print("\n📦 PART 1: UNIFIED CREATION API")
    print("-" * 70)

    # Create blob namespace
    blob = await store.create_namespace(
        type=NamespaceType.BLOB,  # Only difference!
        scope=StorageScope.SESSION,
        provider_type="vfs-memory",
    )
    print(f"✓ Created BLOB namespace: {blob.namespace_id}")

    # Create workspace namespace
    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,  # Only difference!
        name="demo-project",
        scope=StorageScope.SESSION,
        provider_type="vfs-memory",
    )
    print(f"✓ Created WORKSPACE namespace: {workspace.namespace_id}")

    print("\n  Both use the SAME API: create_namespace()")
    print("  Both return NamespaceInfo")
    print("  Both are VFS-backed")

    # ========================================================================
    # Part 2: Unified Grid Architecture
    # ========================================================================
    print("\n🗂️  PART 2: UNIFIED GRID ARCHITECTURE")
    print("-" * 70)

    print(f"\nBLOB grid path:      {blob.grid_path}")
    print(f"WORKSPACE grid path: {workspace.grid_path}")

    print("\n  Pattern: grid/{sandbox}/{session}/{namespace_id}/")
    print(f"  Same sandbox: {blob.sandbox_id == workspace.sandbox_id}")
    print(f"  Same session: {blob.session_id == workspace.session_id}")
    print(f"  Different IDs: {blob.namespace_id != workspace.namespace_id}")

    # ========================================================================
    # Part 3: Unified VFS Access
    # ========================================================================
    print("\n📁 PART 3: UNIFIED VFS ACCESS")
    print("-" * 70)

    # Both can get VFS instances
    blob_vfs = store.get_namespace_vfs(blob.namespace_id)
    workspace_vfs = store.get_namespace_vfs(workspace.namespace_id)

    print("\n  Both provide AsyncVirtualFileSystem instances")

    # Blob: data at /_data
    await blob_vfs.write_file("/_data", b"Blob content")
    blob_entries = await blob_vfs.ls("/")
    print(f"\n  BLOB files: {blob_entries}")

    # Workspace: full file tree
    await workspace_vfs.write_file("/main.py", b"print('hello')")
    await workspace_vfs.write_file("/config.json", b'{"version": "1.0"}')
    await workspace_vfs.mkdir("/src")
    workspace_entries = await workspace_vfs.ls("/")
    print(f"  WORKSPACE files: {workspace_entries}")

    print("\n  Both use the SAME VFS methods:")
    print("    - write_file() / read_file()")
    print("    - ls()")
    print("    - mkdir()")
    print("    - rm()")
    print("    - get_node_info(), exists(), cp(), mv()")

    # ========================================================================
    # Part 4: Unified Checkpoint System
    # ========================================================================
    print("\n💾 PART 4: UNIFIED CHECKPOINT SYSTEM")
    print("-" * 70)

    # Create checkpoint for blob
    blob_cp = await store.checkpoint_namespace(
        blob.namespace_id,
        name="blob-v1",
        description="Initial blob state",
    )
    print(f"\n✓ Created BLOB checkpoint: {blob_cp.checkpoint_id}")

    # Create checkpoint for workspace
    workspace_cp = await store.checkpoint_namespace(
        workspace.namespace_id,
        name="workspace-v1",
        description="Initial workspace state",
    )
    print(f"✓ Created WORKSPACE checkpoint: {workspace_cp.checkpoint_id}")

    print("\n  Both use the SAME checkpoint API:")
    print("    - checkpoint_namespace()")
    print("    - restore_namespace()")
    print("    - list_checkpoints()")

    # Modify both
    await blob_vfs.write_file("/_data", b"Modified blob content")
    await workspace_vfs.write_file("/main.py", b"print('modified')")

    # Restore both
    await store.restore_namespace(blob.namespace_id, blob_cp.checkpoint_id)
    await store.restore_namespace(workspace.namespace_id, workspace_cp.checkpoint_id)

    print("\n✓ Both restored from checkpoints successfully")

    # ========================================================================
    # Part 5: Unified Scoping (SESSION, USER, SANDBOX)
    # ========================================================================
    print("\n🔐 PART 5: UNIFIED SCOPING")
    print("-" * 70)

    # Create user-scoped blob
    user_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.USER,
        user_id="alice",
        provider_type="vfs-memory",
    )

    # Create user-scoped workspace
    user_workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="alice-workspace",
        scope=StorageScope.USER,
        user_id="alice",
        provider_type="vfs-memory",
    )

    # Create sandbox-scoped blob (shared)
    sandbox_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SANDBOX,
        provider_type="vfs-memory",
    )

    print(f"\n  SESSION blob:  {blob.grid_path}")
    print(f"  USER blob:     {user_blob.grid_path}")
    print(f"  SANDBOX blob:  {sandbox_blob.grid_path}")

    print(f"\n  SESSION workspace:  {workspace.grid_path}")
    print(f"  USER workspace:     {user_workspace.grid_path}")

    print("\n  Both BLOB and WORKSPACE support:")
    print("    ✓ SESSION scope (ephemeral, session-tied)")
    print("    ✓ USER scope (persistent, user-owned)")
    print("    ✓ SANDBOX scope (shared, sandbox-wide)")

    # ========================================================================
    # Part 6: Unified Listing
    # ========================================================================
    print("\n📋 PART 6: UNIFIED LISTING")
    print("-" * 70)

    # List all namespaces for session
    all_session = store.list_namespaces(session_id=blob.session_id)
    print(f"\nAll session namespaces: {len(all_session)}")
    for ns in all_session:
        print(f"  - {ns.type.value}: {ns.namespace_id}")

    # Filter by type
    session_blobs = store.list_namespaces(
        session_id=blob.session_id,
        type=NamespaceType.BLOB,
    )
    print(f"\nSession blobs only: {len(session_blobs)}")

    session_workspaces = store.list_namespaces(
        session_id=blob.session_id,
        type=NamespaceType.WORKSPACE,
    )
    print(f"Session workspaces only: {len(session_workspaces)}")

    # List user namespaces
    user_namespaces = store.list_namespaces(user_id="alice")
    print(f"\nUser 'alice' namespaces: {len(user_namespaces)}")
    for ns in user_namespaces:
        print(f"  - {ns.type.value}: {ns.name or ns.namespace_id}")

    # ========================================================================
    # Part 7: Unified Read/Write API
    # ========================================================================
    print("\n✍️  PART 7: UNIFIED READ/WRITE API")
    print("-" * 70)

    # Write to blob (path=None defaults to /_data)
    await store.write_namespace(
        blob.namespace_id,
        data=b"Blob data via unified API",
    )
    print("\n✓ Wrote to BLOB using write_namespace()")

    # Write to workspace (path required)
    await store.write_namespace(
        workspace.namespace_id,
        path="/unified.txt",
        data=b"Workspace file via unified API",
    )
    print("✓ Wrote to WORKSPACE using write_namespace()")

    # Read from blob
    blob_data = await store.read_namespace(blob.namespace_id)
    print(f"\n✓ Read from BLOB: {blob_data.decode()}")

    # Read from workspace
    workspace_data = await store.read_namespace(
        workspace.namespace_id, path="/unified.txt"
    )
    print(f"✓ Read from WORKSPACE: {workspace_data.decode()}")

    print("\n  Same methods for both:")
    print("    - write_namespace(namespace_id, data, path)")
    print("    - read_namespace(namespace_id, path)")

    # ========================================================================
    # Part 8: Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ EVERYTHING IS VFS - SUMMARY")
    print("=" * 70)

    print("""
  UNIFIED APIs:
    ✓ create_namespace(type=BLOB|WORKSPACE)
    ✓ write_namespace() / read_namespace()
    ✓ get_namespace_vfs()
    ✓ checkpoint_namespace() / restore_namespace()
    ✓ list_namespaces()
    ✓ destroy_namespace()

  UNIFIED ARCHITECTURE:
    ✓ Same grid structure: grid/{sandbox}/{scope}/{namespace_id}
    ✓ Same session management
    ✓ Same scoping (SESSION, USER, SANDBOX)
    ✓ Same VFS operations
    ✓ Same checkpoint system

  DIFFERENCES:
    ✗ BLOB: Single file at /_data
    ✗ WORKSPACE: Full directory tree

  BENEFIT:
    → One API to rule them all!
    → Everything is VFS-backed
    → Consistent, predictable, clean
    """)

    # Cleanup
    print("\n🧹 Cleaning up...")
    for ns in [blob, workspace, user_blob, user_workspace, sandbox_blob]:
        await store.destroy_namespace(ns.namespace_id)
    print("✓ All namespaces destroyed")

    print("\n" + "=" * 70)
    print("✓ UNIFIED ARCHITECTURE DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
