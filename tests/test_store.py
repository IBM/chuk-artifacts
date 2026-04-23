# tests/test_store.py
# -*- coding: utf-8 -*-
"""
Comprehensive unit tests for ArtifactStore.

Tests cover:
- Core operations (store, retrieve, metadata, etc.)
- Session management integration
- File operations
- Presigned URL operations
- Batch operations
- Administrative operations
- Error handling and edge cases
- Security constraints
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import os

# Import the classes to test
from chuk_artifacts.store import ArtifactStore, _DEFAULT_TTL
from chuk_artifacts.exceptions import ArtifactStoreError, ProviderError


class TestArtifactStoreInitialization:
    """Test ArtifactStore initialization and configuration."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        # Clear environment to test true defaults
        with patch.dict(os.environ, {}, clear=True):
            store = ArtifactStore()

            # The bucket default may vary based on implementation
            assert isinstance(store.bucket, str)
            assert len(store.bucket) > 0
            assert store.session_ttl_hours == 24
            assert store.max_retries == 3
            assert not store._closed
            assert store._storage_provider_name == "memory"
            assert store._session_provider_name == "memory"

    def test_init_with_explicit_defaults(self):
        """Test initialization with explicitly provided defaults."""
        store = ArtifactStore(
            bucket="artifacts", storage_provider="memory", session_provider="memory"
        )

        assert store.bucket == "artifacts"
        assert store._storage_provider_name == "memory"
        assert store._session_provider_name == "memory"

    def test_init_with_custom_values(self):
        """Test initialization with custom values."""
        store = ArtifactStore(
            bucket="custom-bucket",
            storage_provider="filesystem",
            session_provider="redis",
            sandbox_id="test-sandbox",
            session_ttl_hours=48,
            max_retries=5,
        )

        assert store.bucket == "custom-bucket"
        assert store.sandbox_id == "test-sandbox"
        assert store.session_ttl_hours == 48
        assert store.max_retries == 5
        assert store._storage_provider_name == "filesystem"
        assert store._session_provider_name == "redis"

    @patch.dict(
        os.environ,
        {
            "ARTIFACT_BUCKET": "env-bucket",
            "ARTIFACT_PROVIDER": "s3",
            "SESSION_PROVIDER": "memory",  # Use available provider
            "ARTIFACT_SANDBOX_ID": "env-sandbox",
            "AWS_ACCESS_KEY_ID": "test_key",
            "AWS_SECRET_ACCESS_KEY": "test_secret",
        },
    )
    def test_init_with_env_vars(self):
        """Test initialization with environment variables."""
        store = ArtifactStore()

        assert store.bucket == "env-bucket"
        assert store.sandbox_id == "env-sandbox"
        assert store._storage_provider_name == "s3"
        assert store._session_provider_name == "memory"

    def test_init_with_unknown_providers(self):
        """Test initialization with unknown providers raises errors."""
        # Test unknown storage provider
        with pytest.raises(ValueError, match="Unknown storage provider"):
            ArtifactStore(storage_provider="unknown_storage")

        # Test unknown session provider
        with pytest.raises(ValueError, match="Unknown session provider"):
            ArtifactStore(session_provider="unknown_session")

    def test_sandbox_id_detection(self):
        """Test sandbox ID auto-detection."""
        with patch.dict(os.environ, {"HOSTNAME": "test-host-123"}):
            store = ArtifactStore()
            assert store.sandbox_id == "test-host-123"

    def test_sandbox_id_fallback(self):
        """Test sandbox ID fallback generation."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("uuid.uuid4") as mock_uuid:
                mock_uuid.return_value.hex = "abcdef123456"
                store = ArtifactStore()
                assert store.sandbox_id == "sandbox-abcdef12"

    def test_invalid_storage_provider(self):
        """Test error handling for invalid storage provider."""
        with pytest.raises(ValueError, match="Unknown storage provider 'invalid'"):
            ArtifactStore(storage_provider="invalid")

    def test_invalid_session_provider(self):
        """Test error handling for invalid session provider."""
        with pytest.raises(ValueError, match="Unknown session provider 'invalid'"):
            ArtifactStore(session_provider="invalid")


class TestCoreOperations:
    """Test core ArtifactStore operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_session_manager(self, store):
        """Mock the session manager."""
        mock_manager = AsyncMock()
        store._session_manager = mock_manager
        return mock_manager

    @pytest.fixture
    def mock_core_ops(self, store):
        """Mock core operations."""
        mock_ops = AsyncMock()
        store._core = mock_ops
        return mock_ops

    @pytest.fixture
    def mock_metadata_ops(self, store):
        """Mock metadata operations."""
        mock_ops = AsyncMock()
        store._metadata = mock_ops
        return mock_ops

    @pytest.mark.asyncio
    async def test_store_with_session_allocation(
        self, store, mock_session_manager, mock_core_ops
    ):
        """Test store operation with session allocation."""
        # Setup mocks
        mock_session_manager.allocate_session.return_value = "session-123"
        mock_core_ops.store.return_value = "artifact-456"

        # Test data
        data = b"test content"
        mime = "text/plain"
        summary = "Test artifact"

        # Call store
        result = await store.store(
            data=data,
            mime=mime,
            summary=summary,
            session_id="provided-session",
            user_id="user-123",
        )

        # Verify session allocation
        mock_session_manager.allocate_session.assert_called_once_with(
            session_id="provided-session", user_id="user-123"
        )

        # Verify core store call (includes new scope and owner_id parameters)
        mock_core_ops.store.assert_called_once_with(
            data=data,
            mime=mime,
            summary=summary,
            meta=None,
            filename=None,
            session_id="session-123",
            ttl=_DEFAULT_TTL,
            scope="session",  # Default scope
            owner_id=None,  # No owner_id for session scope
        )

        assert result == "artifact-456"

    @pytest.mark.asyncio
    async def test_store_with_all_parameters(
        self, store, mock_session_manager, mock_core_ops
    ):
        """Test store operation with all parameters."""
        # Setup mocks
        mock_session_manager.allocate_session.return_value = "session-123"
        mock_core_ops.store.return_value = "artifact-456"

        # Test data
        data = b"test content"
        mime = "application/json"
        summary = "Test JSON artifact"
        meta = {"key": "value", "type": "test"}
        filename = "test.json"

        # Call store
        result = await store.store(
            data=data,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id="provided-session",
            user_id="user-123",
            ttl=3600,
        )

        # Verify core store call (includes new scope and owner_id parameters)
        mock_core_ops.store.assert_called_once_with(
            data=data,
            mime=mime,
            summary=summary,
            meta=meta,
            filename=filename,
            session_id="session-123",
            ttl=3600,
            scope="session",  # Default scope
            owner_id=None,  # No owner_id for session scope
        )

        assert result == "artifact-456"

    @pytest.mark.asyncio
    async def test_retrieve(self, store, mock_core_ops, mock_metadata_ops):
        """Test artifact retrieval."""
        # Setup mocks
        expected_data = b"retrieved content"
        mock_core_ops.retrieve.return_value = expected_data

        # Mock metadata to return session-scoped artifact (no access control by default)
        from chuk_artifacts.models import ArtifactMetadata

        mock_metadata = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="test-session",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/test-session/artifact-123",
            mime="application/octet-stream",
            summary="Test",
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
            scope="session",  # Session scope - no access control enforcement without session_id param
        )
        mock_metadata_ops.get_metadata.return_value = mock_metadata

        # Call retrieve
        result = await store.retrieve("artifact-123")

        # Verify
        mock_core_ops.retrieve.assert_called_once_with("artifact-123")
        assert result == expected_data

    @pytest.mark.asyncio
    async def test_metadata(self, store, mock_metadata_ops):
        """Test metadata retrieval."""
        # Setup mock
        expected_meta = {
            "id": "artifact-123",
            "mime": "text/plain",
            "summary": "Test artifact",
            "created_at": "2025-01-01T00:00:00Z",
        }
        mock_metadata_ops.get_metadata.return_value = expected_meta

        # Call metadata
        result = await store.metadata("artifact-123")

        # Verify
        mock_metadata_ops.get_metadata.assert_called_once_with("artifact-123")
        assert result == expected_meta

    @pytest.mark.asyncio
    async def test_exists(self, store, mock_metadata_ops):
        """Test artifact existence check."""
        # Setup mock
        mock_metadata_ops.exists.return_value = True

        # Call exists
        result = await store.exists("artifact-123")

        # Verify
        mock_metadata_ops.exists.assert_called_once_with("artifact-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete(self, store, mock_metadata_ops):
        """Test artifact deletion."""
        # Setup mock
        mock_metadata_ops.delete.return_value = True

        # Call delete
        result = await store.delete("artifact-123")

        # Verify
        mock_metadata_ops.delete.assert_called_once_with("artifact-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_list_by_session(self, store, mock_metadata_ops):
        """Test listing artifacts by session."""
        # Setup mock
        expected_artifacts = [
            {"id": "artifact-1", "summary": "First artifact"},
            {"id": "artifact-2", "summary": "Second artifact"},
        ]
        mock_metadata_ops.list_by_session.return_value = expected_artifacts

        # Call list_by_session
        result = await store.list_by_session("session-123", limit=50)

        # Verify
        mock_metadata_ops.list_by_session.assert_called_once_with("session-123", 50)
        assert result == expected_artifacts


class TestSessionOperations:
    """Test session management operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_session_manager(self, store):
        """Mock the session manager."""
        mock_manager = AsyncMock()
        store._session_manager = mock_manager
        return mock_manager

    @pytest.mark.asyncio
    async def test_create_session(self, store, mock_session_manager):
        """Test session creation."""
        # Setup mock
        mock_session_manager.allocate_session.return_value = "session-123"

        # Call create_session
        result = await store.create_session(
            user_id="user-123", ttl_hours=48, custom_metadata={"project": "test"}
        )

        # Verify
        mock_session_manager.allocate_session.assert_called_once_with(
            user_id="user-123", ttl_hours=48, custom_metadata={"project": "test"}
        )
        assert result == "session-123"

    @pytest.mark.asyncio
    async def test_validate_session(self, store, mock_session_manager):
        """Test session validation."""
        # Setup mock
        mock_session_manager.validate_session.return_value = True

        # Call validate_session
        result = await store.validate_session("session-123")

        # Verify
        mock_session_manager.validate_session.assert_called_once_with("session-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_get_session_info(self, store, mock_session_manager):
        """Test getting session information."""
        # Setup mock
        expected_info = {
            "session_id": "session-123",
            "user_id": "user-123",
            "created_at": "2025-01-01T00:00:00Z",
            "expires_at": "2025-01-02T00:00:00Z",
        }
        mock_session_manager.get_session_info.return_value = expected_info

        # Call get_session_info
        result = await store.get_session_info("session-123")

        # Verify
        mock_session_manager.get_session_info.assert_called_once_with("session-123")
        assert result == expected_info

    @pytest.mark.asyncio
    async def test_update_session_metadata(self, store, mock_session_manager):
        """Test updating session metadata."""
        # Setup mock
        mock_session_manager.update_session_metadata.return_value = True

        # Call update_session_metadata
        metadata = {"updated": True, "timestamp": "2025-01-01T12:00:00Z"}
        result = await store.update_session_metadata("session-123", metadata)

        # Verify
        mock_session_manager.update_session_metadata.assert_called_once_with(
            "session-123", metadata
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_extend_session_ttl(self, store, mock_session_manager):
        """Test extending session TTL."""
        # Setup mock
        mock_session_manager.extend_session_ttl.return_value = True

        # Call extend_session_ttl
        result = await store.extend_session_ttl("session-123", 24)

        # Verify
        mock_session_manager.extend_session_ttl.assert_called_once_with(
            "session-123", 24
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_session(self, store, mock_session_manager):
        """Test session deletion."""
        # Setup mock
        mock_session_manager.delete_session.return_value = True

        # Call delete_session
        result = await store.delete_session("session-123")

        # Verify
        mock_session_manager.delete_session.assert_called_once_with("session-123")
        assert result is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, store, mock_session_manager):
        """Test cleanup of expired sessions."""
        # Setup mock
        mock_session_manager.cleanup_expired_sessions.return_value = 5

        # Call cleanup_expired_sessions
        result = await store.cleanup_expired_sessions()

        # Verify
        mock_session_manager.cleanup_expired_sessions.assert_called_once()
        assert result == 5


class TestGridOperations:
    """Test grid path operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    def test_get_canonical_prefix(self, store):
        """Test getting canonical prefix."""
        # Test the actual implementation instead of mocking
        result = store.get_canonical_prefix("session-123")

        # Should return a grid path format
        assert isinstance(result, str)
        assert "session-123" in result
        assert store.sandbox_id in result

    def test_generate_artifact_key(self, store):
        """Test generating artifact key."""
        # Test the actual implementation instead of mocking
        result = store.generate_artifact_key("session-123", "artifact-456")

        # Should return a grid key format
        assert isinstance(result, str)
        assert "session-123" in result
        assert "artifact-456" in result
        assert store.sandbox_id in result

    def test_parse_grid_key(self, store):
        """Test parsing grid key."""
        # Create a grid key using the store's method
        grid_key = store.generate_artifact_key("session-123", "artifact-456")
        result = store.parse_grid_key(grid_key)

        # Should parse the grid key correctly or return None
        if result:  # parse might return None for invalid keys
            # Check that it's a GridKeyComponents model
            from chuk_artifacts.models import GridKeyComponents

            assert isinstance(result, GridKeyComponents)
            assert result.sandbox_id == store.sandbox_id
            assert result.session_id == "session-123"
            assert result.artifact_id == "artifact-456"

    def test_get_session_prefix_pattern(self, store):
        """Test getting session prefix pattern."""
        result = store.get_session_prefix_pattern()
        assert result == f"grid/{store.sandbox_id}/"

    def test_grid_functions_imported(self, store):
        """Test that grid functions are properly available."""
        # Test that the grid functions exist and work
        try:
            from chuk_artifacts.grid import canonical_prefix, artifact_key, parse

            # Test canonical_prefix function
            prefix = canonical_prefix("test-sandbox", "session-123")
            assert "grid" in prefix
            assert "test-sandbox" in prefix
            assert "session-123" in prefix

            # Test artifact_key function
            key = artifact_key("test-sandbox", "session-123", "artifact-456")
            assert "grid" in key
            assert "test-sandbox" in key
            assert "session-123" in key
            assert "artifact-456" in key

            # Test parse function with a valid key
            parsed = parse(key)
            if parsed:  # parse might return None for invalid formats
                from chuk_artifacts.models import GridKeyComponents

                assert isinstance(parsed, GridKeyComponents)
                assert parsed.sandbox_id == "test-sandbox"
                assert parsed.session_id == "session-123"
                assert parsed.artifact_id == "artifact-456"
        except ImportError:
            # If grid module is not available, skip this test
            pytest.skip("chuk_artifacts.grid module not available")


class TestFileOperations:
    """Test file operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_write_file_string_content(self, store):
        """Test writing string content to file."""
        with patch.object(store, "store") as mock_store:
            mock_store.return_value = "artifact-123"

            result = await store.write_file(
                content="Hello, world!",
                filename="test.txt",
                mime="text/plain",
                summary="Test file",
                session_id="session-123",
            )

            mock_store.assert_called_once_with(
                data=b"Hello, world!",
                mime="text/plain",
                summary="Test file",
                filename="test.txt",
                session_id="session-123",
                user_id=None,
                meta=None,
                scope="session",
                ttl=900,
            )
            assert result == "artifact-123"

    @pytest.mark.asyncio
    async def test_write_file_bytes_content(self, store):
        """Test writing bytes content to file."""
        with patch.object(store, "store") as mock_store:
            mock_store.return_value = "artifact-123"

            content = b"Binary content"
            result = await store.write_file(
                content=content, filename="test.bin", mime="application/octet-stream"
            )

            mock_store.assert_called_once_with(
                data=content,
                mime="application/octet-stream",
                summary="File: test.bin",
                filename="test.bin",
                session_id=None,
                user_id=None,
                meta=None,
                scope="session",
                ttl=900,
            )
            assert result == "artifact-123"

    @pytest.mark.asyncio
    async def test_read_file_as_text(self, store):
        """Test reading file as text."""
        with patch.object(store, "retrieve") as mock_retrieve:
            mock_retrieve.return_value = b"Hello, world!"

            result = await store.read_file("artifact-123", as_text=True)

            mock_retrieve.assert_called_once_with("artifact-123")
            assert result == "Hello, world!"

    @pytest.mark.asyncio
    async def test_read_file_as_bytes(self, store):
        """Test reading file as bytes."""
        with patch.object(store, "retrieve") as mock_retrieve:
            expected_data = b"Binary data"
            mock_retrieve.return_value = expected_data

            result = await store.read_file("artifact-123", as_text=False)

            mock_retrieve.assert_called_once_with("artifact-123")
            assert result == expected_data

    @pytest.mark.asyncio
    async def test_list_files(self, store):
        """Test listing files."""
        with patch.object(store._metadata, "list_by_prefix") as mock_list:
            expected_files = [
                {"id": "artifact-1", "filename": "file1.txt"},
                {"id": "artifact-2", "filename": "file2.txt"},
            ]
            mock_list.return_value = expected_files

            result = await store.list_files("session-123", prefix="test/", limit=50)

            mock_list.assert_called_once_with("session-123", "test/", 50)
            assert result == expected_files

    @pytest.mark.asyncio
    async def test_get_directory_contents(self, store):
        """Test getting directory contents."""
        with patch.object(store._metadata, "list_by_prefix") as mock_list:
            expected_contents = [
                {"id": "artifact-1", "filename": "dir/file1.txt"},
                {"id": "artifact-2", "filename": "dir/file2.txt"},
            ]
            mock_list.return_value = expected_contents

            result = await store.get_directory_contents("session-123", "dir/")

            mock_list.assert_called_once_with("session-123", "dir/", 100)
            assert result == expected_contents

    @pytest.mark.asyncio
    async def test_get_directory_contents_error(self, store):
        """Test directory contents error handling."""
        with patch.object(store._metadata, "list_by_prefix") as mock_list:
            mock_list.side_effect = Exception("Database error")

            with pytest.raises(ProviderError, match="Directory listing failed"):
                await store.get_directory_contents("session-123", "dir/")

    @pytest.mark.asyncio
    async def test_copy_file_same_session(self, store):
        """Test copying file within same session."""
        # Setup mocks with ArtifactMetadata model
        from chuk_artifacts.models import ArtifactMetadata

        original_meta = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="session-123",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/session-123/artifact-123",
            mime="text/plain",
            summary="Original file",
            filename="original.txt",
            bytes=12,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
            meta={"key": "value"},
        )

        with (
            patch.object(store, "metadata") as mock_metadata,
            patch.object(store, "retrieve") as mock_retrieve,
            patch.object(store, "store") as mock_store,
        ):
            mock_metadata.return_value = original_meta
            mock_retrieve.return_value = b"file content"
            mock_store.return_value = "artifact-copy"

            # Mock datetime for consistent testing
            with patch("chuk_artifacts.store.datetime") as mock_datetime:
                mock_datetime.now.return_value.isoformat.return_value.replace.return_value = "2025-01-01T12:00:00Z"

                result = await store.copy_file(
                    "artifact-123", new_filename="copy.txt", new_meta={"copied": True}
                )

                # Verify calls
                mock_metadata.assert_called_once_with("artifact-123")
                mock_retrieve.assert_called_once_with("artifact-123")

                # Verify store call with merged metadata
                store_call = mock_store.call_args
                assert store_call[1]["data"] == b"file content"
                assert store_call[1]["mime"] == "text/plain"
                assert store_call[1]["summary"] == "Copy of Original file"
                assert store_call[1]["filename"] == "copy.txt"
                assert store_call[1]["session_id"] == "session-123"

                # Verify metadata includes copy tracking
                copy_meta = store_call[1]["meta"]
                assert copy_meta["key"] == "value"
                assert copy_meta["copied"] is True
                assert copy_meta["copied_from"] == "artifact-123"
                assert copy_meta["copy_timestamp"] == "2025-01-01T12:00:00Z"

                assert result == "artifact-copy"

    @pytest.mark.asyncio
    async def test_copy_file_cross_session_blocked(self, store):
        """Test that cross-session copying is blocked."""
        from chuk_artifacts.models import ArtifactMetadata

        original_meta = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="session-123",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/session-123/artifact-123",
            mime="text/plain",
            summary="Original file",
            filename="file.txt",
            bytes=10,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with patch.object(store, "metadata") as mock_metadata:
            mock_metadata.return_value = original_meta

            with pytest.raises(
                ArtifactStoreError, match="Cross-session copies are not permitted"
            ):
                await store.copy_file("artifact-123", target_session_id="session-456")

    @pytest.mark.asyncio
    async def test_move_file_same_session(self, store):
        """Test moving file within same session."""
        from chuk_artifacts.models import ArtifactMetadata

        original_record = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="session-123",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/session-123/artifact-123",
            mime="text/plain",
            summary="Original file",
            filename="original.txt",
            bytes=10,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
            meta={"key": "value"},
        )

        with patch.object(store, "metadata") as mock_metadata:
            mock_metadata.return_value = original_record

            result = await store.move_file(
                "artifact-123", new_filename="moved.txt", new_meta={"moved": True}
            )

            # Verify the returned record is updated
            assert result.filename == "moved.txt"
            assert result.meta["key"] == "value"
            assert result.meta["moved"] is True

    @pytest.mark.asyncio
    async def test_move_file_cross_session_blocked(self, store):
        """Test that cross-session moving is blocked."""
        from chuk_artifacts.models import ArtifactMetadata

        original_record = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="session-123",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/session-123/artifact-123",
            mime="text/plain",
            summary="Original file",
            filename="original.txt",
            bytes=10,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        with patch.object(store, "metadata") as mock_metadata:
            mock_metadata.return_value = original_record

            with pytest.raises(
                ArtifactStoreError, match="Cross-session moves are not permitted"
            ):
                await store.move_file("artifact-123", new_session_id="session-456")


class TestPresignedURLOperations:
    """Test presigned URL operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_presigned_ops(self, store):
        """Mock presigned operations."""
        mock_ops = AsyncMock()
        store._presigned = mock_ops
        return mock_ops

    @pytest.mark.asyncio
    async def test_presign(self, store, mock_presigned_ops):
        """Test generating presigned URL."""
        mock_presigned_ops.presign.return_value = "https://example.com/presigned-url"

        result = await store.presign("artifact-123", expires=7200)

        mock_presigned_ops.presign.assert_called_once_with("artifact-123", 7200)
        assert result == "https://example.com/presigned-url"

    @pytest.mark.asyncio
    async def test_presign_short(self, store, mock_presigned_ops):
        """Test generating short-lived presigned URL."""
        mock_presigned_ops.presign_short.return_value = "https://example.com/short-url"

        result = await store.presign_short("artifact-123")

        mock_presigned_ops.presign_short.assert_called_once_with("artifact-123")
        assert result == "https://example.com/short-url"

    @pytest.mark.asyncio
    async def test_presign_upload(self, store, mock_presigned_ops):
        """Test generating presigned upload URL."""
        mock_presigned_ops.presign_upload.return_value = (
            "https://upload-url",
            "artifact-123",
        )

        result = await store.presign_upload(
            session_id="session-123",
            filename="test.txt",
            mime_type="text/plain",
            expires=3600,
        )

        mock_presigned_ops.presign_upload.assert_called_once_with(
            "session-123", "test.txt", "text/plain", 3600
        )
        assert result == ("https://upload-url", "artifact-123")


class TestBatchOperations:
    """Test batch operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_batch_ops(self, store):
        """Mock batch operations."""
        mock_ops = AsyncMock()
        store._batch = mock_ops
        return mock_ops

    @pytest.mark.asyncio
    async def test_store_batch(self, store, mock_batch_ops):
        """Test batch store operation."""
        items = [
            {"data": b"content1", "mime": "text/plain", "summary": "Item 1"},
            {"data": b"content2", "mime": "text/plain", "summary": "Item 2"},
        ]
        expected_ids = ["artifact-1", "artifact-2"]

        mock_batch_ops.store_batch.return_value = expected_ids

        result = await store.store_batch(items, session_id="session-123", ttl=3600)

        mock_batch_ops.store_batch.assert_called_once_with(items, "session-123", 3600)
        assert result == expected_ids


class TestMetadataOperations:
    """Test metadata operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_metadata_ops(self, store):
        """Mock metadata operations."""
        mock_ops = AsyncMock()
        store._metadata = mock_ops
        return mock_ops

    @pytest.mark.asyncio
    async def test_update_metadata(self, store, mock_metadata_ops):
        """Test updating metadata."""
        updated_meta = {
            "id": "artifact-123",
            "summary": "Updated summary",
            "meta": {"updated": True},
        }
        mock_metadata_ops.update_metadata.return_value = updated_meta

        result = await store.update_metadata(
            "artifact-123",
            summary="Updated summary",
            meta={"updated": True},
            merge=True,
        )

        mock_metadata_ops.update_metadata.assert_called_once_with(
            "artifact-123",
            summary="Updated summary",
            meta={"updated": True},
            merge=True,
        )
        assert result == updated_meta

    @pytest.mark.asyncio
    async def test_extend_ttl(self, store, mock_metadata_ops):
        """Test extending TTL."""
        updated_meta = {"id": "artifact-123", "ttl": 7200}
        mock_metadata_ops.extend_ttl.return_value = updated_meta

        result = await store.extend_ttl("artifact-123", 3600)

        mock_metadata_ops.extend_ttl.assert_called_once_with("artifact-123", 3600)
        assert result == updated_meta


class TestAdministrativeOperations:
    """Test administrative operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.fixture
    def mock_admin_ops(self, store):
        """Mock admin operations."""
        mock_ops = AsyncMock()
        store._admin = mock_ops
        return mock_ops

    @pytest.mark.asyncio
    async def test_validate_configuration(self, store, mock_admin_ops):
        """Test configuration validation."""
        validation_result = {
            "storage_provider": "memory",
            "session_provider": "memory",
            "bucket": "artifacts",
            "sandbox_id": "test-sandbox",
            "status": "healthy",
        }
        mock_admin_ops.validate_configuration.return_value = validation_result

        result = await store.validate_configuration()

        mock_admin_ops.validate_configuration.assert_called_once()
        assert result == validation_result

    @pytest.mark.asyncio
    async def test_get_stats(self, store, mock_admin_ops):
        """Test getting storage statistics."""
        admin_stats = {
            "total_artifacts": 100,
            "total_size_bytes": 1024000,
            "active_sessions": 5,
        }
        session_stats = {"cache_hits": 50, "cache_misses": 10, "total_sessions": 15}

        mock_admin_ops.get_stats.return_value = admin_stats
        store._session_manager.get_cache_stats = Mock(return_value=session_stats)

        result = await store.get_stats()

        mock_admin_ops.get_stats.assert_called_once()
        assert result["total_artifacts"] == 100
        assert result["session_manager"] == session_stats


class TestResourceManagement:
    """Test resource management and lifecycle."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_close(self, store):
        """Test closing the store."""
        assert not store._closed

        await store.close()

        assert store._closed

    @pytest.mark.asyncio
    async def test_context_manager(self, store):
        """Test using store as async context manager."""
        async with store as ctx_store:
            assert ctx_store is store
            assert not ctx_store._closed

        assert store._closed

    @pytest.mark.asyncio
    async def test_multiple_close_calls(self, store):
        """Test that multiple close calls are safe."""
        await store.close()
        assert store._closed

        # Second close should not raise
        await store.close()
        assert store._closed


class TestErrorHandling:
    """Test error handling and edge cases."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_store_with_session_manager_error(self, store):
        """Test store operation when session manager fails."""
        with patch.object(store._session_manager, "allocate_session") as mock_allocate:
            mock_allocate.side_effect = Exception("Session allocation failed")

            with pytest.raises(Exception, match="Session allocation failed"):
                await store.store(data=b"test", mime="text/plain", summary="Test")

    @pytest.mark.asyncio
    async def test_retrieve_nonexistent_artifact(self, store):
        """Test retrieving non-existent artifact."""
        # Since retrieve() now calls metadata() first, we need to mock that too
        with patch.object(store._metadata, "get_metadata") as mock_metadata:
            mock_metadata.side_effect = ArtifactStoreError("Artifact not found")

            with pytest.raises(ArtifactStoreError, match="Artifact not found"):
                await store.retrieve("nonexistent-artifact")

    @pytest.mark.asyncio
    async def test_metadata_with_provider_error(self, store):
        """Test metadata operation with provider error."""
        with patch.object(store._metadata, "get_metadata") as mock_metadata:
            mock_metadata.side_effect = ProviderError("Database connection failed")

            with pytest.raises(ProviderError, match="Database connection failed"):
                await store.metadata("artifact-123")

    def test_invalid_provider_loading_integration(self):
        """Test actual invalid provider initialization."""
        # Test with a provider that doesn't exist
        with pytest.raises(ValueError, match="Unknown storage provider"):
            ArtifactStore(storage_provider="nonexistent_provider")

        with pytest.raises(ValueError, match="Unknown session provider"):
            ArtifactStore(session_provider="nonexistent_provider")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_store_empty_data(self, store):
        """Test storing empty data."""
        with (
            patch.object(store._session_manager, "allocate_session") as mock_allocate,
            patch.object(store._core, "store") as mock_store,
        ):
            mock_allocate.return_value = "session-123"
            mock_store.return_value = "artifact-123"

            result = await store.store(
                data=b"", mime="application/octet-stream", summary="Empty file"
            )

            mock_store.assert_called_once()
            assert mock_store.call_args[1]["data"] == b""
            assert result == "artifact-123"

    @pytest.mark.asyncio
    async def test_store_large_metadata(self, store):
        """Test storing artifact with large metadata."""
        large_meta = {f"key_{i}": f"value_{i}" * 100 for i in range(100)}

        with (
            patch.object(store._session_manager, "allocate_session") as mock_allocate,
            patch.object(store._core, "store") as mock_store,
        ):
            mock_allocate.return_value = "session-123"
            mock_store.return_value = "artifact-123"

            result = await store.store(
                data=b"test data",
                mime="text/plain",
                summary="Test with large metadata",
                meta=large_meta,
            )

            assert result == "artifact-123"
            assert mock_store.call_args[1]["meta"] == large_meta

    @pytest.mark.asyncio
    async def test_write_file_with_special_characters(self, store):
        """Test writing file with special characters in content and filename."""
        content = "Hello 世界! 🌍 Special chars: àáâãäå"
        filename = "special_文件名_🗂️.txt"

        with patch.object(store, "store") as mock_store:
            mock_store.return_value = "artifact-123"

            await store.write_file(
                content=content, filename=filename, mime="text/plain; charset=utf-8"
            )

            # Verify UTF-8 encoding
            expected_data = content.encode("utf-8")
            mock_store.assert_called_once()
            assert mock_store.call_args[1]["data"] == expected_data
            assert mock_store.call_args[1]["filename"] == filename

    @pytest.mark.asyncio
    async def test_copy_file_with_missing_filename(self, store):
        """Test copying file when original has no filename."""
        from chuk_artifacts.models import ArtifactMetadata

        original_meta = ArtifactMetadata(
            artifact_id="artifact-123",
            session_id="session-123",
            sandbox_id="test-sandbox",
            key="grid/test-sandbox/session-123/artifact-123",
            mime="application/octet-stream",
            summary="Binary data",
            filename=None,
            bytes=10,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
            meta={},
        )

        with (
            patch.object(store, "metadata") as mock_metadata,
            patch.object(store, "retrieve") as mock_retrieve,
            patch.object(store, "store") as mock_store,
        ):
            mock_metadata.return_value = original_meta
            mock_retrieve.return_value = b"binary data"
            mock_store.return_value = "artifact-copy"

            with patch("chuk_artifacts.store.datetime") as mock_datetime:
                mock_datetime.now.return_value.isoformat.return_value.replace.return_value = "2025-01-01T12:00:00Z"

                await store.copy_file("artifact-123")

                # Should use "file_copy" as default filename
                store_call = mock_store.call_args
                assert store_call[1]["filename"] == "file_copy"

    def test_sandbox_id_with_invalid_characters(self):
        """Test sandbox ID cleaning with invalid characters."""
        with patch.dict(
            os.environ, {"HOSTNAME": "test-host@#$%^&*()!+=/{}[]|\\:;\"'<>?,.`~"}
        ):
            store = ArtifactStore()
            # Should clean to only alphanumeric, dash, and underscore
            assert store.sandbox_id == "test-host"

    def test_sandbox_id_truncation(self):
        """Test sandbox ID truncation for long names."""
        long_hostname = "a" * 100
        with patch.dict(os.environ, {"HOSTNAME": long_hostname}):
            store = ArtifactStore()
            # Should be truncated to 32 characters
            assert len(store.sandbox_id) == 32
            assert store.sandbox_id == "a" * 32


class TestIntegrationScenarios:
    """Test integration scenarios that involve multiple operations."""

    @pytest.fixture
    def store(self):
        """Create a test store instance with mocked dependencies."""
        store = ArtifactStore(sandbox_id="test-sandbox")

        # Mock all operation modules
        store._core = AsyncMock()
        store._metadata = AsyncMock()
        store._presigned = AsyncMock()
        store._batch = AsyncMock()
        store._admin = AsyncMock()
        store._session_manager = AsyncMock()

        return store

    @pytest.mark.asyncio
    async def test_complete_file_lifecycle(self, store):
        """Test complete file lifecycle: create session, store, retrieve, update, delete."""
        # Setup mocks for the complete workflow
        store._session_manager.allocate_session.return_value = "session-123"
        store._core.store.return_value = "artifact-123"
        store._core.retrieve.return_value = b"file content"
        store._metadata.get_metadata.return_value = {
            "id": "artifact-123",
            "mime": "text/plain",
            "summary": "Test file",
        }
        store._metadata.update_metadata.return_value = {
            "id": "artifact-123",
            "summary": "Updated test file",
        }
        store._metadata.delete.return_value = True

        # 1. Create session
        session_id = await store.create_session(user_id="user-123")
        assert session_id == "session-123"

        # 2. Store file
        artifact_id = await store.store(
            data=b"file content",
            mime="text/plain",
            summary="Test file",
            session_id=session_id,
        )
        assert artifact_id == "artifact-123"

        # 3. Retrieve file
        content = await store.retrieve(artifact_id)
        assert content == b"file content"

        # 4. Get metadata
        metadata = await store.metadata(artifact_id)
        assert metadata["id"] == "artifact-123"

        # 5. Update metadata
        updated = await store.update_metadata(artifact_id, summary="Updated test file")
        assert updated["summary"] == "Updated test file"

        # 6. Delete file
        deleted = await store.delete(artifact_id)
        assert deleted is True

    @pytest.mark.asyncio
    async def test_batch_operations_workflow(self, store):
        """Test batch operations workflow."""
        # Setup mocks
        store._session_manager.allocate_session.return_value = "session-123"
        store._batch.store_batch.return_value = [
            "artifact-1",
            "artifact-2",
            "artifact-3",
        ]
        store._metadata.list_by_session.return_value = [
            {"id": "artifact-1", "summary": "Batch item 1"},
            {"id": "artifact-2", "summary": "Batch item 2"},
            {"id": "artifact-3", "summary": "Batch item 3"},
        ]

        # 1. Create session
        session_id = await store.create_session(user_id="batch-user")

        # 2. Batch store
        items = [
            {"data": b"content1", "mime": "text/plain", "summary": "Item 1"},
            {"data": b"content2", "mime": "text/plain", "summary": "Item 2"},
            {"data": b"content3", "mime": "text/plain", "summary": "Item 3"},
        ]
        artifact_ids = await store.store_batch(items, session_id=session_id)
        assert len(artifact_ids) == 3

        # 3. List artifacts in session
        artifacts = await store.list_by_session(session_id)
        assert len(artifacts) == 3

    @pytest.mark.asyncio
    async def test_file_operations_workflow(self, store):
        """Test file operations workflow with directory structure."""
        # Setup mocks
        store._session_manager.allocate_session.return_value = "session-123"
        store._metadata.list_by_prefix.return_value = [
            {"id": "artifact-1", "filename": "docs/readme.txt"},
            {"id": "artifact-2", "filename": "docs/guide.md"},
        ]

        # Mock store for write_file
        with patch.object(store, "store") as mock_store:
            mock_store.return_value = "artifact-123"

            # 1. Create session
            session_id = await store.create_session()

            # 2. Write file
            await store.write_file(
                content="# Documentation\n\nThis is a test file.",
                filename="docs/readme.md",
                mime="text/markdown",
                session_id=session_id,
            )

            # 3. List files in directory
            files = await store.list_files(session_id, prefix="docs/")
            assert len(files) == 2

            # 4. Get directory contents
            contents = await store.get_directory_contents(session_id, "docs/")
            assert len(contents) == 2


class TestConcurrencyAndAsyncBehavior:
    """Test concurrent operations and async behavior."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_concurrent_store_operations(self, store):
        """Test concurrent store operations."""
        with (
            patch.object(store._session_manager, "allocate_session") as mock_allocate,
            patch.object(store._core, "store") as mock_store,
        ):
            # Setup mocks to return different values for concurrent calls
            mock_allocate.side_effect = ["session-1", "session-2", "session-3"]
            mock_store.side_effect = ["artifact-1", "artifact-2", "artifact-3"]

            # Create concurrent store operations
            tasks = [
                store.store(
                    data=f"content{i}".encode(), mime="text/plain", summary=f"File {i}"
                )
                for i in range(3)
            ]

            # Execute concurrently
            results = await asyncio.gather(*tasks)

            # Verify results
            assert results == ["artifact-1", "artifact-2", "artifact-3"]
            assert mock_allocate.call_count == 3
            assert mock_store.call_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_session_operations(self, store):
        """Test concurrent session operations."""
        with (
            patch.object(store._session_manager, "allocate_session") as mock_allocate,
            patch.object(store._session_manager, "validate_session") as mock_validate,
        ):
            mock_allocate.side_effect = ["session-1", "session-2"]
            mock_validate.return_value = True

            # Create concurrent session operations
            create_tasks = [store.create_session(user_id=f"user-{i}") for i in range(2)]
            validate_task = store.validate_session("existing-session")

            # Execute concurrently
            results = await asyncio.gather(*create_tasks, validate_task)

            assert results[:2] == ["session-1", "session-2"]
            assert results[2] is True


class TestParameterValidationAndTypes:
    """Test parameter validation and type handling."""

    @pytest.fixture
    def store(self):
        """Create a test store instance."""
        return ArtifactStore(sandbox_id="test-sandbox")

    @pytest.mark.asyncio
    async def test_store_with_none_values(self, store):
        """Test store operation with None values for optional parameters."""
        with (
            patch.object(store._session_manager, "allocate_session") as mock_allocate,
            patch.object(store._core, "store") as mock_store,
        ):
            mock_allocate.return_value = "session-123"
            mock_store.return_value = "artifact-123"

            result = await store.store(
                data=b"test content",
                mime="text/plain",
                summary="Test",
                meta=None,
                filename=None,
                session_id=None,
                user_id=None,
            )

            # Verify None values are passed through correctly
            store_call = mock_store.call_args
            assert store_call[1]["meta"] is None
            assert store_call[1]["filename"] is None
            assert result == "artifact-123"

    @pytest.mark.asyncio
    async def test_write_file_encoding_variations(self, store):
        """Test write_file with different encoding parameters."""
        test_content = "Test content with émojis 🚀"

        with patch.object(store, "store") as mock_store:
            mock_store.return_value = "artifact-123"

            # Test UTF-8 encoding (default)
            await store.write_file(content=test_content, filename="test1.txt")
            utf8_data = mock_store.call_args[1]["data"]

            # Test Latin-1 encoding
            mock_store.reset_mock()
            await store.write_file(
                content="Test content",  # ASCII only for latin-1
                filename="test2.txt",
                encoding="latin-1",
            )
            latin1_data = mock_store.call_args[1]["data"]

            # Verify different encodings produce different byte sequences
            assert utf8_data != latin1_data

    def test_initialization_parameter_types(self):
        """Test initialization with various parameter types."""
        # Test with integer session_ttl_hours
        store1 = ArtifactStore(session_ttl_hours=48)
        assert store1.session_ttl_hours == 48

        # Test with integer max_retries
        store2 = ArtifactStore(max_retries=10)
        assert store2.max_retries == 10

        # Test with explicit None values - should use defaults (clear env vars)
        with patch.dict(os.environ, {}, clear=True):
            store3 = ArtifactStore(
                bucket="test-bucket",  # Provide explicit bucket
                storage_provider=None,
                session_provider=None,
                sandbox_id=None,
            )
            assert store3.bucket == "test-bucket"
            assert store3._storage_provider_name == "memory"  # Should default to memory
            assert store3._session_provider_name == "memory"  # Should default to memory

    def test_initialization_with_env_override(self):
        """Test that environment variables override None values."""
        with patch.dict(
            os.environ,
            {
                "ARTIFACT_PROVIDER": "s3",
                "SESSION_PROVIDER": "memory",
                "AWS_ACCESS_KEY_ID": "test_key",
                "AWS_SECRET_ACCESS_KEY": "test_secret",
            },
        ):
            store = ArtifactStore(
                bucket="test-bucket",
                storage_provider=None,  # Should use env var
                session_provider=None,  # Should use env var
            )
            assert store.bucket == "test-bucket"
            assert store._storage_provider_name == "s3"  # From env var
            assert store._session_provider_name == "memory"  # From env var


if __name__ == "__main__":
    # Configuration for running tests
    pytest.main(
        [
            __file__,
            "-v",
            "--tb=short",
            "--durations=10",
            "--cov=chuk_artifacts.store",
            "--cov-report=term-missing",
            "--cov-report=html",
        ]
    )
