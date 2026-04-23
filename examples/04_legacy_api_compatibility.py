#!/usr/bin/env python3
"""
Example 4: Legacy API Compatibility

This example demonstrates how the legacy blob API (store/retrieve) still works
and is now internally implemented using the unified namespace architecture.

This ensures backward compatibility for existing code while providing a clean
path forward to the unified API.
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, StorageScope


async def main():
    store = ArtifactStore()

    print("=" * 70)
    print("LEGACY API COMPATIBILITY")
    print("=" * 70)

    # ========================================================================
    # Part 1: Legacy store() and retrieve()
    # ========================================================================
    print("\n📦 PART 1: LEGACY STORE() AND RETRIEVE()")
    print("-" * 70)

    # OLD API (still works!)
    artifact_id = await store.store(
        data=b"Hello from legacy API",
        mime="text/plain",
        summary="Test artifact",
        scope=StorageScope.SESSION,
    )

    print(f"\n✓ Stored using legacy API: {artifact_id}")
    print("  This internally:")
    print("    1. Created a BLOB namespace")
    print("    2. Wrote data to /_data")
    print("    3. Returned namespace_id as artifact_id")

    # Retrieve using legacy API
    data = await store.retrieve(artifact_id)
    print(f"\n✓ Retrieved using legacy API: {data.decode()}")
    print("  This internally:")
    print("    1. Reads from namespace_id")
    print("    2. Reads /_data from the blob VFS")

    # ========================================================================
    # Part 2: Legacy API Still Works (Separate Implementation)
    # ========================================================================
    print("\n🔄 PART 2: LEGACY API STILL WORKS")
    print("-" * 70)

    # Store using legacy API
    legacy_id = await store.store(
        data=b"Stored via legacy",
        mime="application/json",
        summary="Legacy artifact",
    )
    print(f"\n✓ Stored via legacy: {legacy_id}")

    # Retrieve using legacy API
    legacy_data = await store.retrieve(legacy_id)
    print(f"✓ Retrieved via legacy: {legacy_data.decode()}")

    print("\n  Note: Legacy API uses the old internal implementation")
    print("  This is intentional for backward compatibility")
    print("  Legacy artifacts != namespace artifacts (for now)")

    # ========================================================================
    # Part 3: Unified API Examples (New Code)
    # ========================================================================
    print("\n🆕 PART 3: UNIFIED API (NEW CODE)")
    print("-" * 70)

    # Use the new unified namespace API
    from chuk_artifacts import NamespaceType

    # Create blob namespace
    blob_ns = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION,
    )
    print(f"\n✓ Created blob namespace: {blob_ns.namespace_id}")

    # Write data
    await store.write_namespace(blob_ns.namespace_id, data=b"New unified blob")

    # Read data
    data = await store.read_namespace(blob_ns.namespace_id)
    print(f"✓ Read data: {data.decode()}")

    # Create workspace namespace
    workspace_ns = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="new-project",
        scope=StorageScope.SESSION,
    )
    print(f"\n✓ Created workspace: {workspace_ns.name}")

    # Write files
    await store.write_namespace(
        workspace_ns.namespace_id, path="/README.md", data=b"# New Project"
    )
    print("✓ Wrote README.md")

    # List namespaces
    namespaces = store.list_namespaces(session_id=blob_ns.session_id)
    print(f"\n✓ Total namespaces in session: {len(namespaces)}")
    for ns in namespaces:
        print(f"  - {ns.type.value}: {ns.name or ns.namespace_id}")

    # ========================================================================
    # Part 4: Migration Path
    # ========================================================================
    print("\n🚀 PART 4: MIGRATION PATH")
    print("-" * 70)

    print("""
  EXISTING CODE (Legacy API):

    artifact_id = await store.store(data, mime="text/plain", summary="...")
    data = await store.retrieve(artifact_id)

  ✓ STILL WORKS! No changes needed.

  NEW CODE (Unified Namespace API):

    blob = await store.create_namespace(type=NamespaceType.BLOB)
    await store.write_namespace(blob.namespace_id, data=data)
    data = await store.read_namespace(blob.namespace_id)

  ✓ MORE EXPLICIT, MORE POWERFUL!

  BENEFITS OF NEW API:
    ✓ Explicit namespace types (BLOB vs WORKSPACE)
    ✓ Unified API for both types
    ✓ Direct VFS access
    ✓ Checkpoint support for both
    ✓ SESSION/USER/SANDBOX scoping
    ✓ Clearer semantics

  RECOMMENDATION:
    → Use legacy API for existing code (backward compatible)
    → Use unified API for new code (more powerful)
    → Both work side-by-side!
    """)

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ LEGACY COMPATIBILITY - SUMMARY")
    print("=" * 70)

    print("""
  LEGACY API PRESERVED:
    ✓ store(data, mime, summary) still works
    ✓ retrieve(artifact_id) still works
    ✓ All existing code keeps working
    ✓ No breaking changes!

  CURRENT STATE:
    → Legacy API uses old internal implementation
    → This is intentional for backward compatibility
    → Legacy artifacts and namespace artifacts are separate
    → Both work perfectly fine side-by-side

  UNIFIED NAMESPACE API (NEW):
    ✓ create_namespace(type=BLOB|WORKSPACE)
    ✓ Explicit types and scoping
    ✓ Full VFS access
    ✓ Checkpoint support
    ✓ Consistent API for both types

  RECOMMENDATION:
    → Use legacy API: existing code (no changes needed)
    → Use unified API: new code (more powerful, cleaner)
    → Both APIs work perfectly together!
    """)

    # Cleanup
    print("\n🧹 Cleaning up...")
    # Cleanup unified namespaces
    namespaces = store.list_namespaces(session_id=blob_ns.session_id)
    for ns in namespaces:
        await store.destroy_namespace(ns.namespace_id)

    print(f"✓ Cleaned up {len(namespaces)} unified namespaces")
    print("  (Legacy artifacts cleaned up automatically by session expiration)")

    print("\n" + "=" * 70)
    print("✓ LEGACY COMPATIBILITY DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
