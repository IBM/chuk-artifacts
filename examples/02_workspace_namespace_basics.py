#!/usr/bin/env python3
"""
Example 2: Workspace Namespace Basics

This example demonstrates workspace namespaces in the unified VFS architecture.

Workspace namespaces are multi-file VFS-backed storage units perfect for:
- Project workspaces
- File collections
- Directory trees
- Code repositories
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    # Initialize the artifact store
    store = ArtifactStore()

    print("=" * 70)
    print("WORKSPACE NAMESPACE BASICS")
    print("=" * 70)

    # ========================================================================
    # Example 1: Create a workspace namespace
    # ========================================================================
    print("\n1. Creating a workspace namespace...")

    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="my-project",
        scope=StorageScope.SESSION,
        provider_type="vfs-memory",
    )

    print(f"   ✓ Created workspace: {workspace.namespace_id}")
    print(f"   ✓ Name: {workspace.name}")
    print(f"   ✓ Type: {workspace.type.value}")
    print(f"   ✓ Grid path: {workspace.grid_path}")

    # ========================================================================
    # Example 2: Write files to workspace
    # ========================================================================
    print("\n2. Writing files to workspace...")

    # Write main.py
    await store.write_namespace(
        workspace.namespace_id,
        path="/main.py",
        data=b"print('Hello from workspace!')",
    )
    print("   ✓ Wrote /main.py")

    # Write config.json
    await store.write_namespace(
        workspace.namespace_id,
        path="/config.json",
        data=b'{"version": "1.0", "name": "my-project"}',
    )
    print("   ✓ Wrote /config.json")

    # Write nested file
    await store.write_namespace(
        workspace.namespace_id,
        path="/src/utils.py",
        data=b"def hello():\n    return 'Hello!'",
    )
    print("   ✓ Wrote /src/utils.py")

    # ========================================================================
    # Example 3: Read files from workspace
    # ========================================================================
    print("\n3. Reading files from workspace...")

    main_py = await store.read_namespace(workspace.namespace_id, path="/main.py")
    print(f"   ✓ Read /main.py: {main_py.decode()}")

    config_json = await store.read_namespace(
        workspace.namespace_id, path="/config.json"
    )
    print(f"   ✓ Read /config.json: {config_json.decode()}")

    # ========================================================================
    # Example 4: Direct VFS access to workspace
    # ========================================================================
    print("\n4. Accessing workspace via VFS...")

    vfs = store.get_namespace_vfs(workspace.namespace_id)

    # List root directory
    root_entries = await vfs.ls("/")
    print(f"   ✓ Root directory entries: {root_entries}")

    # List src directory
    src_entries = await vfs.ls("/src")
    print(f"   ✓ /src directory entries: {src_entries}")

    # Create a new directory
    await vfs.mkdir("/tests")
    print("   ✓ Created /tests directory")

    # Write a test file
    await vfs.write_file("/tests/test_main.py", b"def test_hello(): pass")
    print("   ✓ Wrote /tests/test_main.py")

    # Copy a file
    await vfs.cp("/src/utils.py", "/src/helpers.py")
    print("   ✓ Copied /src/utils.py to /src/helpers.py")

    # List updated src directory
    src_entries = await vfs.ls("/src")
    print(f"   ✓ Updated /src: {src_entries}")

    # ========================================================================
    # Example 5: Create user-scoped workspace
    # ========================================================================
    print("\n5. Creating a user-scoped workspace...")

    user_workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="alice-project",
        scope=StorageScope.USER,
        user_id="alice",
        provider_type="vfs-memory",
    )

    print(f"   ✓ Created user workspace: {user_workspace.namespace_id}")
    print(f"   ✓ User: {user_workspace.user_id}")
    print(f"   ✓ Grid path: {user_workspace.grid_path}")

    # Write files to user workspace
    user_vfs = store.get_namespace_vfs(user_workspace.namespace_id)
    await user_vfs.write_file("/README.md", b"# Alice's Project\n\nPersonal workspace.")
    print("   ✓ Wrote README.md to user workspace")

    # ========================================================================
    # Example 6: Create checkpoint of workspace
    # ========================================================================
    print("\n6. Creating checkpoint of workspace...")

    checkpoint1 = await store.checkpoint_namespace(
        workspace.namespace_id,
        name="initial-structure",
        description="Initial project structure with main.py, config.json, and utils",
    )

    print(f"   ✓ Created checkpoint: {checkpoint1.checkpoint_id}")
    print(f"   ✓ Name: {checkpoint1.name}")

    # Make changes
    await vfs.write_file("/main.py", b"print('Modified version!')")
    await vfs.write_file("/new_feature.py", b"# New feature")
    print("   ✓ Modified files and added new feature")

    # Create another checkpoint
    checkpoint2 = await store.checkpoint_namespace(
        workspace.namespace_id,
        name="added-feature",
        description="Added new feature",
    )
    print(f"   ✓ Created checkpoint: {checkpoint2.checkpoint_id}")

    # List checkpoints
    checkpoints = await store.list_checkpoints(workspace.namespace_id)
    print(f"   ✓ Total checkpoints: {len(checkpoints)}")
    for cp in checkpoints:
        print(f"     - {cp.name} ({cp.created_at})")

    # Restore to initial checkpoint
    await store.restore_namespace(workspace.namespace_id, checkpoint1.checkpoint_id)
    print(f"   ✓ Restored to checkpoint: {checkpoint1.name}")

    # Verify restoration
    restored_main = await vfs.read_file("/main.py")
    print(f"   ✓ Restored /main.py: {restored_main.decode()}")

    # Check that new_feature.py is gone
    root_entries = await vfs.ls("/")
    print(f"   ✓ Root after restore: {root_entries}")

    # ========================================================================
    # Example 7: File operations in workspace
    # ========================================================================
    print("\n7. Advanced file operations...")

    # Move a file
    await vfs.mv("/src/helpers.py", "/src/lib.py")
    print("   ✓ Moved /src/helpers.py to /src/lib.py")

    # Delete a file
    await vfs.rm("/tests/test_main.py")
    print("   ✓ Deleted /tests/test_main.py")

    # Get file info
    main_info = await vfs.get_node_info("/main.py")
    print(f"   ✓ /main.py size: {main_info.size} bytes")

    # Check if file exists
    exists = await vfs.exists("/config.json")
    print(f"   ✓ /config.json exists: {exists}")

    # ========================================================================
    # Example 8: List namespaces by type
    # ========================================================================
    print("\n8. Listing workspace namespaces...")

    # List all workspaces for session
    session_workspaces = store.list_namespaces(
        session_id=workspace.session_id,
        type=NamespaceType.WORKSPACE,
    )

    print(f"   ✓ Session workspaces: {len(session_workspaces)}")
    for ns in session_workspaces:
        print(f"     - {ns.name} ({ns.namespace_id})")

    # List user workspaces
    user_workspaces = store.list_namespaces(
        user_id="alice",
        type=NamespaceType.WORKSPACE,
    )

    print(f"   ✓ User workspaces: {len(user_workspaces)}")
    for ns in user_workspaces:
        print(f"     - {ns.name} (user={ns.user_id})")

    # ========================================================================
    # Example 9: Cleanup
    # ========================================================================
    print("\n9. Cleaning up...")

    await store.destroy_namespace(workspace.namespace_id)
    print(f"   ✓ Destroyed workspace: {workspace.namespace_id}")

    await store.destroy_namespace(user_workspace.namespace_id)
    print(f"   ✓ Destroyed user workspace: {user_workspace.namespace_id}")

    print("\n" + "=" * 70)
    print("✓ WORKSPACE NAMESPACE BASICS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
