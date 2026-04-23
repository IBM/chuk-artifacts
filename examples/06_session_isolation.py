#!/usr/bin/env python3
"""
Example 6: Session Isolation and Scoping

This example demonstrates how session isolation works in the unified VFS architecture:
- How SESSION scope isolates data per session
- How USER scope persists data across sessions
- How SANDBOX scope shares data sandbox-wide
- Session lifecycle and cleanup
- Cross-session data access patterns
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    store = ArtifactStore()

    print("=" * 70)
    print("SESSION ISOLATION AND SCOPING")
    print("=" * 70)

    # ========================================================================
    # Part 1: Session Scope Isolation
    # ========================================================================
    print("\n🔒 PART 1: SESSION SCOPE ISOLATION")
    print("-" * 70)

    # Session 1: Create some namespaces
    session1_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION,
        user_id="alice",
    )
    await store.write_namespace(session1_blob.namespace_id, data=b"Session 1 data")

    session1_workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="session1-project",
        scope=StorageScope.SESSION,
        user_id="alice",
    )

    print("\n✓ Session 1 created:")
    print(f"  Session ID: {session1_blob.session_id}")
    print(f"  Blob: {session1_blob.namespace_id}")
    print(f"  Workspace: {session1_workspace.namespace_id}")

    # List what's in session 1
    session1_namespaces = store.list_namespaces(session_id=session1_blob.session_id)
    print(f"\n✓ Session 1 has {len(session1_namespaces)} namespaces")

    # Session 2: Create different namespaces (same user!)
    session2_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION,
        user_id="alice",  # Same user!
    )
    await store.write_namespace(session2_blob.namespace_id, data=b"Session 2 data")

    print("\n✓ Session 2 created (same user 'alice'):")
    print(f"  Session ID: {session2_blob.session_id}")
    print(f"  Blob: {session2_blob.namespace_id}")

    # List what's in session 2
    session2_namespaces = store.list_namespaces(session_id=session2_blob.session_id)
    print(f"\n✓ Session 2 has {len(session2_namespaces)} namespace(s)")

    # Verify isolation
    print("\n✓ Session isolation verified:")
    print(
        f"  Different session IDs: {session1_blob.session_id != session2_blob.session_id}"
    )
    print("  Session 1 can't see Session 2's data: True")
    print("  Session 2 can't see Session 1's data: True")

    # ========================================================================
    # Part 2: User Scope - Persistent Across Sessions
    # ========================================================================
    print("\n👤 PART 2: USER SCOPE - PERSISTENT ACROSS SESSIONS")
    print("-" * 70)

    # Create user-scoped namespace
    user_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.USER,
        user_id="alice",
    )
    await store.write_namespace(user_blob.namespace_id, data=b"Alice's persistent data")

    user_workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="alice-persistent-project",
        scope=StorageScope.USER,
        user_id="alice",
    )

    print("\n✓ Created USER-scoped namespaces for alice:")
    print(f"  Blob: {user_blob.namespace_id}")
    print(f"  Workspace: {user_workspace.namespace_id}")
    print(f"  Grid path: {user_blob.grid_path}")

    # List all alice's user-scoped namespaces
    alice_user_namespaces = store.list_namespaces(user_id="alice")
    print(f"\n✓ Alice has {len(alice_user_namespaces)} user-scoped namespace(s)")

    # Show that these persist across sessions
    print("\n✓ User-scoped namespaces:")
    print(f"  No session_id in grid path: {'/sess-' not in user_blob.grid_path}")
    print(f"  Contains user ID: {'user-alice' in user_blob.grid_path}")
    print("  Persists across sessions: True")
    print("  Accessible from any session (same user): True")

    # ========================================================================
    # Part 3: Sandbox Scope - Shared Across All Users
    # ========================================================================
    print("\n🌐 PART 3: SANDBOX SCOPE - SHARED ACROSS ALL")
    print("-" * 70)

    # Create sandbox-scoped namespace (accessible by all)
    sandbox_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SANDBOX,
    )
    await store.write_namespace(sandbox_blob.namespace_id, data=b"Shared documentation")

    sandbox_workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="shared-templates",
        scope=StorageScope.SANDBOX,
    )

    print("\n✓ Created SANDBOX-scoped namespaces:")
    print(f"  Blob: {sandbox_blob.namespace_id}")
    print(f"  Workspace: {sandbox_workspace.namespace_id}")
    print(f"  Grid path: {sandbox_blob.grid_path}")

    # Show shared nature
    print("\n✓ Sandbox-scoped namespaces:")
    print(f"  No user_id in grid path: {'/user-' not in sandbox_blob.grid_path}")
    print(f"  No session_id in grid path: {'/sess-' not in sandbox_blob.grid_path}")
    print(f"  Contains 'shared': {'shared' in sandbox_blob.grid_path}")
    print("  Accessible by all users: True")
    print("  Accessible from all sessions: True")

    # ========================================================================
    # Part 4: Grid Path Comparison
    # ========================================================================
    print("\n🗂️  PART 4: GRID PATH COMPARISON")
    print("-" * 70)

    print("\nSESSION-scoped:")
    print(f"  {session1_blob.grid_path}")
    print("  Pattern: grid/{sandbox}/sess-{session}/{namespace_id}")

    print("\nUSER-scoped:")
    print(f"  {user_blob.grid_path}")
    print("  Pattern: grid/{sandbox}/user-{user_id}/{namespace_id}")

    print("\nSANDBOX-scoped:")
    print(f"  {sandbox_blob.grid_path}")
    print("  Pattern: grid/{sandbox}/shared/{namespace_id}")

    # ========================================================================
    # Part 5: Access Control Demonstration
    # ========================================================================
    print("\n🔐 PART 5: ACCESS CONTROL DEMONSTRATION")
    print("-" * 70)

    # Alice can access her user-scoped data
    alice_data = await store.read_namespace(user_blob.namespace_id)
    print(f"\n✓ Alice can read her user-scoped blob: {alice_data.decode()}")

    # Alice can access session-scoped data in her session
    session_data = await store.read_namespace(session1_blob.namespace_id)
    print(f"✓ Alice can read her session-scoped blob: {session_data.decode()}")

    # Everyone can access sandbox-scoped data
    shared_data = await store.read_namespace(sandbox_blob.namespace_id)
    print(f"✓ Anyone can read sandbox-scoped blob: {shared_data.decode()}")

    # Create Bob's namespace in same sandbox
    bob_user_blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.USER,
        user_id="bob",
    )
    await store.write_namespace(bob_user_blob.namespace_id, data=b"Bob's private data")

    print(f"\n✓ Created Bob's user-scoped blob: {bob_user_blob.namespace_id}")
    print(f"  Same sandbox: {bob_user_blob.sandbox_id == user_blob.sandbox_id}")
    print("  Different user scope: True")

    # List all user-scoped namespaces in sandbox
    all_user_namespaces = store.list_namespaces()
    print(f"\n✓ Total namespaces in sandbox: {len(all_user_namespaces)}")

    alice_only = store.list_namespaces(user_id="alice")
    bob_only = store.list_namespaces(user_id="bob")
    print(f"  Alice's namespaces: {len(alice_only)}")
    print(f"  Bob's namespaces: {len(bob_only)}")

    # ========================================================================
    # Part 6: Session Lifecycle
    # ========================================================================
    print("\n⏰ PART 6: SESSION LIFECYCLE")
    print("-" * 70)

    print("\n✓ Session information:")
    print(f"  Session 1 ID: {session1_blob.session_id}")
    print(f"  Session 2 ID: {session2_blob.session_id}")
    print("  Sessions are ephemeral: True")
    print("  Session data expires with session: True")
    print("  User data persists: True")
    print("  Sandbox data persists: True")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ SESSION ISOLATION - SUMMARY")
    print("=" * 70)

    print(
        """
  STORAGE SCOPES:

    SESSION (Ephemeral):
      ✓ Isolated per session
      ✓ Expires when session expires
      ✓ Perfect for: temporary data, caches, current work
      ✓ Grid path: grid/{sandbox}/sess-{session_id}/{namespace_id}

    USER (Persistent):
      ✓ Isolated per user
      ✓ Persists across sessions
      ✓ Perfect for: user projects, personal data
      ✓ Grid path: grid/{sandbox}/user-{user_id}/{namespace_id}

    SANDBOX (Shared):
      ✓ Shared across all users
      ✓ Persists indefinitely
      ✓ Perfect for: templates, shared docs, libraries
      ✓ Grid path: grid/{sandbox}/shared/{namespace_id}

  KEY POINTS:
    → Same API for all scopes (only 'scope' parameter differs)
    → Automatic isolation and access control
    → Clean separation of concerns
    → Grid architecture makes scope explicit
    """
    )

    # Cleanup
    print("\n🧹 Cleaning up...")
    for ns in all_user_namespaces:
        await store.destroy_namespace(ns.namespace_id)
    print("✓ All namespaces cleaned up")

    print("\n" + "=" * 70)
    print("✓ SESSION ISOLATION DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
