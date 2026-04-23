#!/usr/bin/env python3
"""
Example 1: Blob Namespace Basics

This example demonstrates the core concepts of blob namespaces in the unified
"everything is VFS" architecture.

Blob namespaces are single-file VFS-backed storage units perfect for:
- Storing artifacts (images, documents, data files)
- Caching computed results
- Session-specific temporary storage
- User-specific persistent storage
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
    print("BLOB NAMESPACE BASICS")
    print("=" * 70)

    # ========================================================================
    # Example 1: Create a session-scoped blob namespace
    # ========================================================================
    print("\n1. Creating a session-scoped blob namespace...")

    blob_ns = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION,
        provider_type="vfs-memory",  # In-memory for quick testing
    )

    print(f"   ✓ Created blob namespace: {blob_ns.namespace_id}")
    print(f"   ✓ Type: {blob_ns.type.value}")
    print(f"   ✓ Scope: {blob_ns.scope.value}")
    print(f"   ✓ Provider: {blob_ns.provider_type}")
    print(f"   ✓ Grid path: {blob_ns.grid_path}")
    print(f"   ✓ Session: {blob_ns.session_id}")

    # ========================================================================
    # Example 2: Write data to blob namespace
    # ========================================================================
    print("\n2. Writing data to blob namespace...")

    data = b"Hello from the unified VFS architecture!"
    await store.write_namespace(
        blob_ns.namespace_id,
        data=data,
        mime="text/plain",
    )

    print(f"   ✓ Wrote {len(data)} bytes to blob")

    # ========================================================================
    # Example 3: Read data from blob namespace
    # ========================================================================
    print("\n3. Reading data from blob namespace...")

    retrieved_data = await store.read_namespace(blob_ns.namespace_id)

    print(f"   ✓ Read {len(retrieved_data)} bytes from blob")
    print(f"   ✓ Data: {retrieved_data.decode()}")
    print(f"   ✓ Data matches: {retrieved_data == data}")

    # ========================================================================
    # Example 4: Direct VFS access to blob namespace
    # ========================================================================
    print("\n4. Accessing blob via VFS...")

    vfs = store.get_namespace_vfs(blob_ns.namespace_id)

    # Blobs store data at /_data
    blob_data = await vfs.read_file("/_data")
    print(f"   ✓ Read from /_data: {blob_data.decode()}")

    # Check metadata
    meta_data = await vfs.read_file("/_meta.json")
    print(f"   ✓ Metadata: {meta_data.decode()}")

    # List all files in blob namespace
    entries = await vfs.ls("/")
    print(f"   ✓ Files in blob namespace: {entries}")

    # ========================================================================
    # Example 5: Create user-scoped blob (persistent)
    # ========================================================================
    print("\n5. Creating a user-scoped blob namespace...")

    user_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.USER,
        user_id="alice",
        provider_type="vfs-memory",
    )

    print(f"   ✓ Created user blob: {user_blob.namespace_id}")
    print(f"   ✓ User: {user_blob.user_id}")
    print(f"   ✓ Grid path: {user_blob.grid_path}")

    await store.write_namespace(
        user_blob.namespace_id,
        data=b"Alice's persistent data",
        mime="text/plain",
    )

    print("   ✓ Wrote user-scoped data")

    # ========================================================================
    # Example 6: Create checkpoint of blob namespace
    # ========================================================================
    print("\n6. Creating checkpoint of blob...")

    checkpoint = await store.checkpoint_namespace(
        blob_ns.namespace_id,
        name="v1.0",
        description="Initial state",
    )

    print(f"   ✓ Created checkpoint: {checkpoint.checkpoint_id}")
    print(f"   ✓ Name: {checkpoint.name}")
    print(f"   ✓ Description: {checkpoint.description}")
    print(f"   ✓ Created: {checkpoint.created_at}")

    # Modify the blob
    await store.write_namespace(
        blob_ns.namespace_id,
        data=b"Modified data!",
    )

    modified_data = await store.read_namespace(blob_ns.namespace_id)
    print(f"   ✓ Modified data: {modified_data.decode()}")

    # Restore from checkpoint
    await store.restore_namespace(blob_ns.namespace_id, checkpoint.checkpoint_id)

    restored_data = await store.read_namespace(blob_ns.namespace_id)
    print(f"   ✓ Restored data: {restored_data.decode()}")
    print(f"   ✓ Data restored correctly: {restored_data == data}")

    # ========================================================================
    # Example 7: List all namespaces
    # ========================================================================
    print("\n7. Listing namespaces...")

    # List blobs for current session
    session_blobs = store.list_namespaces(
        session_id=blob_ns.session_id,
        type=NamespaceType.BLOB,
    )

    print(f"   ✓ Session blobs: {len(session_blobs)}")
    for ns in session_blobs:
        print(f"     - {ns.namespace_id} ({ns.type.value})")

    # List user blobs
    user_blobs = store.list_namespaces(
        user_id="alice",
        type=NamespaceType.BLOB,
    )

    print(f"   ✓ User blobs: {len(user_blobs)}")
    for ns in user_blobs:
        print(f"     - {ns.namespace_id} (user={ns.user_id})")

    # ========================================================================
    # Example 8: Cleanup
    # ========================================================================
    print("\n8. Cleaning up...")

    await store.destroy_namespace(blob_ns.namespace_id)
    print(f"   ✓ Destroyed session blob: {blob_ns.namespace_id}")

    await store.destroy_namespace(user_blob.namespace_id)
    print(f"   ✓ Destroyed user blob: {user_blob.namespace_id}")

    print("\n" + "=" * 70)
    print("✓ BLOB NAMESPACE BASICS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
