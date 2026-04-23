# -*- coding: utf-8 -*-
# tests/test_store_access_and_search.py
"""
Tests for access control and search functionality in ArtifactStore.
"""

import pytest
import os
from chuk_artifacts import ArtifactStore
from chuk_artifacts.exceptions import AccessDeniedError


@pytest.fixture
async def store():
    """Create a test store with memory providers."""
    os.environ["ARTIFACT_PROVIDER"] = "memory"
    os.environ["SESSION_PROVIDER"] = "memory"

    async with ArtifactStore(sandbox_id="test-sandbox") as s:
        yield s


class TestUserScopedArtifacts:
    """Test user-scoped artifact storage."""

    @pytest.mark.asyncio
    async def test_user_scoped_requires_user_id(self, store):
        """Test that user-scoped artifacts require user_id."""
        with pytest.raises(ValueError) as exc_info:
            await store.store(
                data=b"test data",
                mime="text/plain",
                summary="test",
                scope="user",  # user scope requires user_id
            )
        assert "user_id is required" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_user_scoped_with_user_id_success(self, store):
        """Test that user-scoped artifacts work with user_id."""
        artifact_id = await store.store(
            data=b"test data",
            mime="text/plain",
            summary="test",
            scope="user",
            user_id="alice",
        )
        assert artifact_id is not None

        # Verify metadata
        metadata = await store.metadata(artifact_id)
        assert metadata.scope == "user"
        assert metadata.owner_id == "alice"


class TestAccessControlInRetrieve:
    """Test access control checks in retrieve() method."""

    @pytest.mark.asyncio
    async def test_retrieve_user_scoped_same_user(self, store):
        """Test retrieving user-scoped artifact as the same user."""
        # Store a user-scoped artifact
        artifact_id = await store.store(
            data=b"user data",
            mime="text/plain",
            summary="test",
            scope="user",
            user_id="alice",
        )

        # Retrieve as the same user (should succeed)
        data = await store.retrieve(artifact_id, user_id="alice")
        assert data == b"user data"

    @pytest.mark.asyncio
    async def test_retrieve_user_scoped_different_user(self, store):
        """Test retrieving user-scoped artifact as different user."""
        # Store a user-scoped artifact
        artifact_id = await store.store(
            data=b"user data",
            mime="text/plain",
            summary="test",
            scope="user",
            user_id="alice",
        )

        # Try to retrieve as different user (should fail)
        with pytest.raises(AccessDeniedError):
            await store.retrieve(artifact_id, user_id="bob")

    @pytest.mark.asyncio
    async def test_retrieve_sandbox_scoped(self, store):
        """Test retrieving sandbox-scoped artifact."""
        # Store a sandbox-scoped artifact
        artifact_id = await store.store(
            data=b"sandbox data",
            mime="text/plain",
            summary="test",
            scope="sandbox",
        )

        # Anyone in the sandbox can retrieve
        data = await store.retrieve(artifact_id, user_id="alice")
        assert data == b"sandbox data"

        data = await store.retrieve(artifact_id, user_id="bob")
        assert data == b"sandbox data"

    @pytest.mark.asyncio
    async def test_retrieve_session_scoped_with_session_id(self, store):
        """Test retrieving session-scoped artifact with session_id check."""
        # Store a session-scoped artifact
        artifact_id = await store.store(
            data=b"session data",
            mime="text/plain",
            summary="test",
            scope="session",
        )

        # Get the session_id from metadata
        metadata = await store.metadata(artifact_id)
        session_id = metadata.session_id

        # Retrieve with correct session_id (should succeed)
        data = await store.retrieve(artifact_id, session_id=session_id)
        assert data == b"session data"

        # Retrieve with different session_id (should fail)
        with pytest.raises(AccessDeniedError):
            await store.retrieve(artifact_id, session_id="different-session")


class TestAccessControlInDelete:
    """Test access control checks in delete() method."""

    @pytest.mark.asyncio
    async def test_delete_user_scoped_same_user(self, store):
        """Test deleting user-scoped artifact as the same user."""
        # Store a user-scoped artifact
        artifact_id = await store.store(
            data=b"user data",
            mime="text/plain",
            summary="test",
            scope="user",
            user_id="alice",
        )

        # Delete as the same user (should succeed)
        result = await store.delete(artifact_id, user_id="alice")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_scoped_different_user(self, store):
        """Test deleting user-scoped artifact as different user."""
        # Store a user-scoped artifact
        artifact_id = await store.store(
            data=b"user data",
            mime="text/plain",
            summary="test",
            scope="user",
            user_id="alice",
        )

        # Try to delete as different user (should fail)
        with pytest.raises(AccessDeniedError) as exc_info:
            await store.delete(artifact_id, user_id="bob")

        assert "Cannot delete artifact" in str(exc_info.value)
        assert "insufficient permissions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_sandbox_scoped_fails(self, store):
        """Test that sandbox-scoped artifacts cannot be deleted via regular delete."""
        # Store a sandbox-scoped artifact
        artifact_id = await store.store(
            data=b"sandbox data",
            mime="text/plain",
            summary="test",
            scope="sandbox",
        )

        # Try to delete (should fail - sandbox artifacts need admin operations)
        with pytest.raises(AccessDeniedError):
            await store.delete(artifact_id, user_id="alice")

    @pytest.mark.asyncio
    async def test_delete_session_scoped_with_session_id(self, store):
        """Test deleting session-scoped artifact with session_id check."""
        # Store a session-scoped artifact
        artifact_id = await store.store(
            data=b"session data",
            mime="text/plain",
            summary="test",
            scope="session",
        )

        # Get the session_id from metadata
        metadata = await store.metadata(artifact_id)
        session_id = metadata.session_id

        # Try to delete with different session_id (should fail)
        with pytest.raises(AccessDeniedError):
            await store.delete(artifact_id, session_id="different-session")

        # Delete with correct session_id (should succeed)
        result = await store.delete(artifact_id, session_id=session_id)
        assert result is True


class TestSearchMethod:
    """Test the search() method for artifact discovery."""

    @pytest.mark.asyncio
    async def test_search_user_artifacts(self, store):
        """Test searching for user-scoped artifacts."""
        # Store multiple user-scoped artifacts for alice
        await store.store(
            data=b"alice data 1",
            mime="text/plain",
            summary="alice file 1",
            scope="user",
            user_id="alice",
        )
        await store.store(
            data=b"alice data 2",
            mime="image/png",
            summary="alice file 2",
            scope="user",
            user_id="alice",
        )

        # Store one for bob
        await store.store(
            data=b"bob data",
            mime="text/plain",
            summary="bob file",
            scope="user",
            user_id="bob",
        )

        # Search alice's artifacts
        results = await store.search(scope="user", user_id="alice")
        assert len(results) >= 2
        assert all(r.owner_id == "alice" for r in results)
        # Check that our specific files are there
        summaries = [r.summary for r in results]
        assert "alice file 1" in summaries
        assert "alice file 2" in summaries

    @pytest.mark.asyncio
    async def test_search_sandbox_artifacts(self, store):
        """Test searching for sandbox-scoped artifacts."""
        # Store sandbox-scoped artifacts
        await store.store(
            data=b"sandbox data 1",
            mime="text/plain",
            summary="shared file 1",
            scope="sandbox",
        )
        await store.store(
            data=b"sandbox data 2",
            mime="image/png",
            summary="shared file 2",
            scope="sandbox",
        )

        # Search sandbox artifacts
        results = await store.search(scope="sandbox")
        assert len(results) >= 2
        assert all(r.scope == "sandbox" for r in results)
        # Check that our specific files are there
        summaries = [r.summary for r in results]
        assert "shared file 1" in summaries
        assert "shared file 2" in summaries

    @pytest.mark.asyncio
    async def test_search_with_mime_filter(self, store):
        """Test searching with MIME type prefix filter."""
        # Store artifacts with different mime types
        await store.store(
            data=b"text 1",
            mime="text/plain",
            summary="text file",
            scope="user",
            user_id="alice",
        )
        await store.store(
            data=b"image 1",
            mime="image/png",
            summary="image file",
            scope="user",
            user_id="alice",
        )

        # Search for text files only
        results = await store.search(scope="user", user_id="alice", mime_prefix="text/")
        assert len(results) >= 1
        assert all(r.mime.startswith("text/") for r in results)
        # Check that our specific text file is there
        summaries = [r.summary for r in results]
        assert "text file" in summaries

    @pytest.mark.asyncio
    async def test_search_with_meta_filter(self, store):
        """Test searching with metadata filter."""
        # Store artifacts with metadata
        await store.store(
            data=b"data 1",
            mime="text/plain",
            summary="file 1",
            meta={"type": "document", "version": "1"},
            scope="user",
            user_id="alice",
        )
        await store.store(
            data=b"data 2",
            mime="text/plain",
            summary="file 2",
            meta={"type": "image", "version": "2"},
            scope="user",
            user_id="alice",
        )

        # Search with meta filter
        results = await store.search(
            scope="user",
            user_id="alice",
            meta_filter={"type": "document"},
        )
        assert len(results) == 1
        assert results[0].meta["type"] == "document"

    @pytest.mark.asyncio
    async def test_search_with_limit(self, store):
        """Test search with result limit."""
        # Store multiple artifacts
        for i in range(5):
            await store.store(
                data=f"data {i}".encode(),
                mime="text/plain",
                summary=f"file {i}",
                scope="user",
                user_id="alice",
            )

        # Search with limit
        results = await store.search(scope="user", user_id="alice", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_session_scope_returns_empty(self, store):
        """Test that searching session scope without session_id returns empty."""
        # Store a session-scoped artifact
        await store.store(
            data=b"session data",
            mime="text/plain",
            summary="session file",
            scope="session",
        )

        # Search session scope (should return empty and log warning)
        results = await store.search(scope="session")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_search_by_user_without_scope(self, store):
        """Test searching by user_id without specifying scope."""
        # Store user-scoped artifacts
        await store.store(
            data=b"user data",
            mime="text/plain",
            summary="user file",
            scope="user",
            user_id="alice",
        )

        # Search with user_id but no scope
        results = await store.search(user_id="alice")
        assert len(results) >= 1
        assert any(r.owner_id == "alice" for r in results)

    @pytest.mark.asyncio
    async def test_search_without_user_id_raises(self, store):
        """Searching without user_id (and not scope=sandbox) must raise ValueError."""
        import pytest as _pytest

        with _pytest.raises(ValueError, match="user_id is required"):
            await store.search()

        with _pytest.raises(ValueError, match="user_id is required"):
            await store.search(mime_prefix="text/")

        with _pytest.raises(ValueError, match="user_id is required"):
            await store.search(scope="user")
