#!/usr/bin/env python3
"""
Example 10: User Isolation and Security

This example demonstrates the user-level security model for MCP servers:
- Per-user artifact isolation (users cannot see each other's files)
- The correct API for listing a user's artifacts (list_by_user)
- Why search() requires user_id
- Sandbox-shared artifacts (opt-in cross-user visibility)
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore


async def main():
    print("=" * 70)
    print("USER ISOLATION AND SECURITY")
    print("=" * 70)

    store = ArtifactStore(sandbox_id="demo-sandbox")

    # ========================================================================
    # Part 1: Store artifacts for two different users
    # ========================================================================
    print("\n📁 PART 1: STORING ARTIFACTS FOR TWO USERS")
    print("-" * 70)

    # Alice stores a spreadsheet
    alice_sheet = await store.store(
        data=b"revenue,Q1,Q2\nalice_corp,100,200",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        summary="Alice's revenue sheet",
        scope="user",
        user_id="alice",
    )
    print(f"\n  Alice stored: {alice_sheet}")

    # Alice stores a presentation
    alice_deck = await store.store(
        data=b"slide1: intro\nslide2: results",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        summary="Alice's Q2 deck",
        scope="user",
        user_id="alice",
    )
    print(f"  Alice stored: {alice_deck}")

    # Bob stores a spreadsheet
    bob_sheet = await store.store(
        data=b"expenses,Q1,Q2\nbob_corp,50,80",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        summary="Bob's expense sheet",
        scope="user",
        user_id="bob",
    )
    print(f"  Bob stored:   {bob_sheet}")

    # ========================================================================
    # Part 2: list_by_user — correct API for MCP tools
    # ========================================================================
    print("\n✅ PART 2: list_by_user() — ISOLATED TO ONE USER")
    print("-" * 70)

    alice_files = await store.list_by_user("alice")
    print(f"\n  Alice's files ({len(alice_files)}):")
    for f in alice_files:
        print(f"    • {f.summary} [{f.mime.split('.')[-1]}]")

    bob_files = await store.list_by_user("bob")
    print(f"\n  Bob's files ({len(bob_files)}):")
    for f in bob_files:
        print(f"    • {f.summary} [{f.mime.split('.')[-1]}]")

    assert len(alice_files) == 2, "Alice should have 2 files"
    assert len(bob_files) == 1, "Bob should have 1 file"
    assert all(f.owner_id == "alice" for f in alice_files), (
        "All Alice files owned by alice"
    )
    assert all(f.owner_id == "bob" for f in bob_files), "All Bob files owned by bob"
    print("\n  ✓ No cross-user leakage confirmed")

    # ========================================================================
    # Part 3: Filter by MIME type (MCP tool: "list all spreadsheets")
    # ========================================================================
    print("\n🔍 PART 3: list_by_user() WITH MIME FILTER")
    print("-" * 70)

    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml"
    alice_sheets = await store.list_by_user("alice", mime_prefix=xlsx_mime)
    print(f"\n  Alice's spreadsheets: {len(alice_sheets)}")
    print(f"    • {alice_sheets[0].summary}")

    # Bob calling list_by_user("alice") is already blocked at the MCP layer
    # (user_id comes from the auth context, not the request)
    bob_sheets = await store.list_by_user("bob", mime_prefix=xlsx_mime)
    print(f"\n  Bob's spreadsheets: {len(bob_sheets)}")
    print(f"    • {bob_sheets[0].summary}")

    print("\n  ✓ Each user only sees their own spreadsheets")

    # ========================================================================
    # Part 4: search() without user_id is blocked
    # ========================================================================
    print("\n🔒 PART 4: search() WITHOUT user_id IS BLOCKED")
    print("-" * 70)

    try:
        # This is the vulnerable pattern Sheerin flagged — now blocked
        await store.search(mime_prefix=xlsx_mime)
        print("  ✗ BUG: Should have raised ValueError")
    except ValueError as e:
        print(f"\n  ✓ Blocked: {e}")

    # search() with user_id is fine
    results = await store.search(user_id="alice", mime_prefix=xlsx_mime)
    print(f"\n  ✓ search(user_id='alice') works: {len(results)} result(s)")

    # ========================================================================
    # Part 5: Sandbox-shared artifacts (explicit opt-in)
    # ========================================================================
    print("\n🌐 PART 5: SANDBOX-SHARED ARTIFACTS (opt-in)")
    print("-" * 70)

    # Admins can store shared resources accessible to everyone
    shared_id = await store.store(
        data=b"company logo bytes",
        mime="image/png",
        summary="Company logo (shared)",
        scope="sandbox",
    )
    print(f"\n  Shared artifact: {shared_id}")

    # Anyone can search sandbox scope without user_id — this is intentional
    shared = await store.search(scope="sandbox")
    print(f"  ✓ search(scope='sandbox') finds {len(shared)} shared artifact(s)")
    print(f"    • {shared[0].summary}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ USER ISOLATION SUMMARY")
    print("=" * 70)
    print("""
  SECURITY RULES:

    ✓ list_by_user(user_id)         — always isolated to one user
    ✓ search(user_id=..., ...)      — user_id required (no cross-user scans)
    ✓ search(scope='sandbox')       — shared artifacts only (opt-in)
    ✗ search()                      — BLOCKED: raises ValueError
    ✗ search(scope='user')          — BLOCKED: user_id required

  MCP TOOL PATTERN:

    async def list_my_spreadsheets(ctx):
        user_id = ctx.get_user_id()          # from auth context
        return await store.list_by_user(
            user_id,
            mime_prefix="application/vnd.openxmlformats-officedocument.spreadsheetml",
        )

  This ensures Alice's MCP server call NEVER returns Bob's files.
    """)


if __name__ == "__main__":
    asyncio.run(main())
