# -*- coding: utf-8 -*-
# tests/test_core.py
"""
Tests for chuk_artifacts.core module.

Tests core storage operations for the artifact store.
"""

import json
import hashlib
import pytest
from unittest.mock import Mock, AsyncMock, patch
from chuk_artifacts.core import CoreStorageOperations, _DEFAULT_TTL
from chuk_artifacts.exceptions import ArtifactStoreError, ProviderError, SessionError
from chuk_artifacts.models import ArtifactMetadata


@pytest.fixture
def mock_artifact_store():
    """Create a mock ArtifactStore for testing."""
    store = Mock()
    store.bucket = "test-bucket"
    store.sandbox_id = "test-sandbox"
    store.max_retries = 3
    store._closed = False
    store._storage_provider_name = "memory"
    store._session_provider_name = "memory"

    # Mock factories
    store._s3_factory = Mock()
    store._session_factory = Mock()

    # Mock grid operations
    store.generate_artifact_key = Mock()

    return store


@pytest.fixture
def core_operations(mock_artifact_store):
    """Create CoreStorageOperations instance for testing."""
    return CoreStorageOperations(mock_artifact_store)


@pytest.fixture
def sample_artifact_data():
    """Create sample artifact data for testing."""
    return {
        "data": b"test file content",
        "mime": "text/plain",
        "summary": "Test file",
        "filename": "test.txt",
        "meta": {"type": "test"},
        "session_id": "test-session-123",
    }


class TestCoreOperationsInitialization:
    """Test CoreStorageOperations initialization."""

    def test_initialization(self, mock_artifact_store):
        """Test that CoreStorageOperations initializes correctly."""
        core_ops = CoreStorageOperations(mock_artifact_store)
        assert core_ops.artifact_store is mock_artifact_store

    def test_initialization_with_none_store(self):
        """Test initialization with None store."""
        core_ops = CoreStorageOperations(None)
        assert core_ops.artifact_store is None


class TestStore:
    """Test the store method."""

    @pytest.mark.asyncio
    async def test_store_success(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test successful artifact storage."""
        # Expected key with new scoped format (with file extension from MIME type)
        test_key = "grid/test-sandbox/sessions/test-session-123/abc123def456.txt"

        # Mock storage operations
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session operations
        mock_session = AsyncMock()
        mock_session.setex = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"

            result = await core_operations.store(**sample_artifact_data)

        # Verify result
        assert result == "abc123def456"

        # Verify storage call
        mock_s3.put_object.assert_called_once()
        put_call = mock_s3.put_object.call_args[1]
        assert put_call["Bucket"] == "test-bucket"
        assert put_call["Key"] == test_key
        assert put_call["Body"] == sample_artifact_data["data"]
        assert put_call["ContentType"] == sample_artifact_data["mime"]

        # Verify metadata storage
        mock_session.setex.assert_called_once()
        setex_call = mock_session.setex.call_args[0]
        assert setex_call[0] == "abc123def456"  # artifact_id
        assert setex_call[1] == _DEFAULT_TTL  # ttl

        # Verify metadata content
        metadata = json.loads(setex_call[2])
        assert metadata["artifact_id"] == "abc123def456"
        assert metadata["session_id"] == sample_artifact_data["session_id"]
        assert metadata["sandbox_id"] == "test-sandbox"
        assert metadata["key"] == test_key
        assert metadata["mime"] == sample_artifact_data["mime"]
        assert metadata["summary"] == sample_artifact_data["summary"]
        assert metadata["meta"] == sample_artifact_data["meta"]
        assert metadata["filename"] == sample_artifact_data["filename"]
        assert metadata["bytes"] == len(sample_artifact_data["data"])
        assert "sha256" in metadata
        assert "stored_at" in metadata

    @pytest.mark.asyncio
    async def test_store_closed_store(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test store when artifact store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await core_operations.store(**sample_artifact_data)

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_with_custom_ttl(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test store with custom TTL."""
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock storage and session operations
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        custom_ttl = 3600
        await core_operations.store(**sample_artifact_data, ttl=custom_ttl)

        # Verify TTL was used
        setex_call = mock_session.setex.call_args[0]
        assert setex_call[1] == custom_ttl

    @pytest.mark.asyncio
    async def test_store_without_optional_fields(
        self, core_operations, mock_artifact_store
    ):
        """Test store with minimal required fields."""
        minimal_data = {
            "data": b"minimal content",
            "mime": "text/plain",
            "summary": "Minimal test",
            "session_id": "test-session",
        }

        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock operations
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await core_operations.store(**minimal_data)

        assert isinstance(result, str)
        assert len(result) == 32  # UUID hex length

        # Verify metadata with None values for optional fields
        setex_call = mock_session.setex.call_args[0]
        metadata = json.loads(setex_call[2])
        assert metadata["meta"] == {}
        assert metadata["filename"] is None

    @pytest.mark.asyncio
    async def test_store_storage_failure(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test store when storage operation fails."""
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock failing storage
        mock_s3 = AsyncMock()
        mock_s3.put_object.side_effect = Exception("Storage failed")
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await core_operations.store(**sample_artifact_data)

        assert "Storage failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_session_failure(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test store when session operation fails."""
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock successful storage
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock failing session
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session failed")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(SessionError) as exc_info:
            await core_operations.store(**sample_artifact_data)

        assert "Metadata storage failed" in str(exc_info.value)


class TestUpdateFile:
    """Test the update_file method."""

    @pytest.mark.asyncio
    async def test_update_file_success(self, core_operations, mock_artifact_store):
        """Test successful file update."""
        artifact_id = "test123"
        new_data = b"updated content"

        # Mock existing record
        existing_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Original summary",
            meta={"original": True},
            filename="original.txt",
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        # Mock _get_record
        core_operations._get_record = AsyncMock(return_value=existing_record)

        # Mock storage operations
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session operations
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        await core_operations.update_file(
            artifact_id, new_data, summary="Updated summary", meta={"updated": True}
        )

        # Verify storage update
        mock_s3.put_object.assert_called_once()
        put_call = mock_s3.put_object.call_args[1]
        assert put_call["Body"] == new_data
        assert put_call["Key"] == "test/key"

        # Verify metadata update
        mock_session.setex.assert_called_once()
        setex_call = mock_session.setex.call_args[0]
        updated_metadata = json.loads(setex_call[2])
        assert updated_metadata["summary"] == "Updated summary"
        assert updated_metadata["meta"] == {"updated": True}
        assert updated_metadata["bytes"] == len(new_data)
        assert "updated_at" in updated_metadata

    @pytest.mark.asyncio
    async def test_update_file_closed_store(self, core_operations, mock_artifact_store):
        """Test update_file when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await core_operations.update_file("test123", b"data")

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_file_not_found(self, core_operations, mock_artifact_store):
        """Test update_file when artifact not found."""
        core_operations._get_record = AsyncMock(side_effect=Exception("Not found"))

        with pytest.raises(ProviderError) as exc_info:
            await core_operations.update_file("nonexistent", b"data")

        assert "Artifact update failed" in str(exc_info.value)


class TestRetrieve:
    """Test the retrieve method."""

    @pytest.mark.asyncio
    async def test_retrieve_success(self, core_operations, mock_artifact_store):
        """Test successful artifact retrieval."""
        artifact_id = "test123"
        test_data = b"test content"
        test_sha256 = hashlib.sha256(test_data).hexdigest()

        # Mock record
        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            sha256=test_sha256,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        # Mock storage response
        mock_s3 = AsyncMock()
        mock_response = {"Body": test_data}
        mock_s3.get_object.return_value = mock_response

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await core_operations.retrieve(artifact_id)

        assert result == test_data

        # Verify get_object call
        mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="test/key")

    @pytest.mark.asyncio
    async def test_retrieve_with_stream_body(
        self, core_operations, mock_artifact_store
    ):
        """Test retrieve with streaming body response."""
        artifact_id = "test123"
        test_data = b"streaming content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        # Mock streaming body
        mock_body = AsyncMock()
        mock_body.read.return_value = test_data

        mock_s3 = AsyncMock()
        mock_response = {"Body": mock_body}
        mock_s3.get_object.return_value = mock_response

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await core_operations.retrieve(artifact_id)

        assert result == test_data
        mock_body.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_sha256_mismatch(self, core_operations, mock_artifact_store):
        """Test retrieve with SHA256 mismatch."""
        artifact_id = "test123"
        test_data = b"test content"
        wrong_sha256 = "wrong_hash"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            sha256=wrong_sha256,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = AsyncMock()
        mock_response = {"Body": test_data}
        mock_s3.get_object.return_value = mock_response

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await core_operations.retrieve(artifact_id)

        assert "SHA256 mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retrieve_closed_store(self, core_operations, mock_artifact_store):
        """Test retrieve when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await core_operations.retrieve("test123")

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_retrieve_storage_failure(self, core_operations, mock_artifact_store):
        """Test retrieve when storage fails."""
        record = ArtifactMetadata(
            artifact_id="test123",
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = AsyncMock()
        mock_s3.get_object.side_effect = Exception("Storage error")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await core_operations.retrieve("test123")

        assert "Retrieval failed" in str(exc_info.value)


class TestStoreWithRetry:
    """Test the _store_with_retry method."""

    @pytest.mark.asyncio
    async def test_store_with_retry_success_first_attempt(
        self, core_operations, mock_artifact_store
    ):
        """Test successful storage on first attempt."""
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        await core_operations._store_with_retry(
            b"test data", "test/key", "text/plain", "test.txt", "session123"
        )

        mock_s3.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_with_retry_success_after_failures(
        self, core_operations, mock_artifact_store
    ):
        """Test successful storage after failures."""
        mock_s3 = AsyncMock()

        # Fail first two attempts, succeed on third
        call_count = 0

        def put_object_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Temporary failure")
            return AsyncMock()

        mock_s3.put_object.side_effect = put_object_side_effect
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await core_operations._store_with_retry(
                b"test data", "test/key", "text/plain", "test.txt", "session123"
            )

        # Should have made 3 attempts
        assert mock_s3.put_object.call_count == 3

        # Should have slept between retries
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_store_with_retry_all_attempts_fail(
        self, core_operations, mock_artifact_store
    ):
        """Test when all retry attempts fail."""
        mock_s3 = AsyncMock()
        mock_s3.put_object.side_effect = Exception("Persistent failure")
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(Exception) as exc_info:
                await core_operations._store_with_retry(
                    b"test data", "test/key", "text/plain", "test.txt", "session123"
                )

        assert "Persistent failure" in str(exc_info.value)
        assert mock_s3.put_object.call_count == mock_artifact_store.max_retries


class TestGetRecord:
    """Test the _get_record method (inherited from base)."""

    @pytest.mark.asyncio
    async def test_get_record_success(self, core_operations, mock_artifact_store):
        """Test successful record retrieval."""
        artifact_id = "test123"
        test_record = {
            "artifact_id": artifact_id,
            "session_id": "session123",
            "sandbox_id": "sandbox123",
            "key": "test/key",
            "mime": "text/plain",
            "summary": "Test",
            "meta": {},
            "bytes": 100,
            "sha256": "abc123",
            "stored_at": "2025-01-01T00:00:00Z",
            "ttl": 900,
            "storage_provider": "memory",
            "session_provider": "memory",
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = json.dumps(test_record)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await core_operations._get_record(artifact_id)

        assert result.artifact_id == artifact_id
        mock_session.get.assert_called_once_with(artifact_id)


class TestCoreOperationsIntegration:
    """Integration tests for core operations."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_workflow(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test complete store and retrieve workflow."""
        # Setup for store operation
        test_key = "grid/test-sandbox/test-session-123/abc123"
        mock_artifact_store.generate_artifact_key.return_value = test_key

        # Mock storage operations
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session operations
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Store artifact
        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"
            artifact_id = await core_operations.store(**sample_artifact_data)

        # Setup for retrieve operation
        stored_record = ArtifactMetadata(
            artifact_id="abc123def456",
            key=test_key,
            session_id="test-session-123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(sample_artifact_data["data"]),
            sha256=hashlib.sha256(sample_artifact_data["data"]).hexdigest(),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        # Mock get_record for retrieve
        core_operations._get_record = AsyncMock(return_value=stored_record)

        # Mock storage response for retrieve
        mock_s3.get_object.return_value = {"Body": sample_artifact_data["data"]}

        # Retrieve artifact
        retrieved_data = await core_operations.retrieve(artifact_id)

        # Verify workflow
        assert artifact_id == "abc123def456"
        assert retrieved_data == sample_artifact_data["data"]

    @pytest.mark.asyncio
    async def test_store_update_retrieve_workflow(
        self, core_operations, mock_artifact_store, sample_artifact_data
    ):
        """Test store, update, and retrieve workflow."""
        artifact_id = "test123"
        sample_artifact_data["data"]
        updated_data = b"updated content"

        # Mock for store
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Store original
        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = artifact_id
            stored_id = await core_operations.store(**sample_artifact_data)

        # Mock for update
        existing_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Original",
            meta={},
            filename="test.txt",
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=existing_record)

        # Update artifact
        await core_operations.update_file(artifact_id, updated_data, summary="Updated")

        # Mock for retrieve
        updated_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Updated",
            meta={},
            bytes=len(updated_data),
            sha256=hashlib.sha256(updated_data).hexdigest(),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=updated_record)
        mock_s3.get_object.return_value = {"Body": updated_data}

        # Retrieve updated artifact
        retrieved_data = await core_operations.retrieve(artifact_id)

        # Verify workflow
        assert stored_id == artifact_id
        assert retrieved_data == updated_data


class TestCoreOperationsEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_store_empty_data(self, core_operations, mock_artifact_store):
        """Test storing empty data."""
        empty_data = {
            "data": b"",
            "mime": "application/octet-stream",
            "summary": "Empty file",
            "session_id": "test-session",
        }

        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await core_operations.store(**empty_data)

        assert isinstance(result, str)

        # Verify metadata shows 0 bytes
        setex_call = mock_session.setex.call_args[0]
        metadata = json.loads(setex_call[2])
        assert metadata["bytes"] == 0

    @pytest.mark.asyncio
    async def test_store_large_data(self, core_operations, mock_artifact_store):
        """Test storing large data."""
        large_data = {
            "data": b"x" * (10 * 1024 * 1024),  # 10MB
            "mime": "application/octet-stream",
            "summary": "Large file",
            "session_id": "test-session",
        }

        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await core_operations.store(**large_data)

        assert isinstance(result, str)

        # Verify large data was stored
        put_call = mock_s3.put_object.call_args[1]
        assert len(put_call["Body"]) == 10 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_retrieve_without_sha256(self, core_operations, mock_artifact_store):
        """Test retrieve when record has no SHA256."""
        artifact_id = "test123"
        test_data = b"test content"

        # Record without SHA256
        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = AsyncMock()
        mock_response = {"Body": test_data}
        mock_s3.get_object.return_value = mock_response

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Should succeed without integrity check
        result = await core_operations.retrieve(artifact_id)
        assert result == test_data


class TestUpdateFileEdgeCases:
    """Test edge cases for update_file method."""

    @pytest.mark.asyncio
    async def test_update_file_no_parameters(
        self, core_operations, mock_artifact_store
    ):
        """Test update_file when no update parameters are provided."""
        with pytest.raises(ValueError) as exc_info:
            await core_operations.update_file("test123")

        assert "At least one update parameter must be provided" in str(exc_info.value)


class TestRetrieveBodyTypes:
    """Test different body response types in retrieve."""

    @pytest.mark.asyncio
    async def test_retrieve_bytes_body_type(self, core_operations, mock_artifact_store):
        """Test retrieve with bytes body response (fallback case)."""
        artifact_id = "test123"
        test_data = b"test content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = AsyncMock()
        # Return a non-bytes, non-readable object to trigger bytes() fallback
        mock_response = {"Body": bytearray(test_data)}
        mock_s3.get_object.return_value = mock_response

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await core_operations.retrieve(artifact_id)
        assert result == bytes(test_data)


class TestStreamUploadDownload:
    """Test streaming upload and download operations."""

    @pytest.mark.asyncio
    async def test_stream_upload_closed_store(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload when store is closed."""
        mock_artifact_store._closed = True

        async def dummy_stream():
            yield b"data"

        with pytest.raises(ArtifactStoreError) as exc_info:
            await core_operations.stream_upload(
                dummy_stream(),
                mime="text/plain",
                summary="Test",
                session_id="test-session",
            )

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_upload_with_native_support(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload with native streaming support."""
        test_data = [b"chunk1", b"chunk2", b"chunk3"]
        combined_data = b"".join(test_data)

        async def data_stream():
            for chunk in test_data:
                yield chunk

        # Mock S3 with native streaming support
        mock_s3 = AsyncMock()
        mock_s3.put_object_stream = AsyncMock(
            return_value={"ContentLength": len(combined_data)}
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "streamtest123"

            artifact_id = await core_operations.stream_upload(
                data_stream(),
                mime="application/octet-stream",
                summary="Stream test",
                session_id="test-session",
            )

        assert artifact_id == "streamtest123"
        mock_s3.put_object_stream.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_upload_fallback_without_native_support(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload fallback when native streaming not supported."""
        test_data = [b"chunk1", b"chunk2"]

        async def data_stream():
            for chunk in test_data:
                yield chunk

        # Mock S3 WITHOUT put_object_stream (no attribute)
        mock_s3 = Mock(spec=[])  # Empty spec so hasattr returns False
        mock_s3.put_object = AsyncMock()

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "fallbacktest123"

            artifact_id = await core_operations.stream_upload(
                data_stream(),
                mime="application/octet-stream",
                summary="Fallback test",
                session_id="test-session",
            )

        assert artifact_id == "fallbacktest123"
        mock_s3.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_upload_with_progress_callback(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload with progress callback."""
        test_data = [b"chunk1", b"chunk2"]
        progress_calls = []

        def progress_callback(bytes_sent, total):
            progress_calls.append((bytes_sent, total))

        async def data_stream():
            for chunk in test_data:
                yield chunk

        # Mock S3 without native support to trigger fallback with progress
        mock_s3 = Mock(spec=[])
        mock_s3.put_object = AsyncMock()

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        await core_operations.stream_upload(
            data_stream(),
            mime="text/plain",
            summary="Progress test",
            session_id="test-session",
            progress_callback=progress_callback,
            content_length=12,
        )

        # Verify progress was reported
        assert len(progress_calls) > 0

    @pytest.mark.asyncio
    async def test_stream_upload_session_error(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload with session error."""

        async def data_stream():
            yield b"test"

        mock_s3 = Mock(spec=[])
        mock_s3.put_object = AsyncMock()

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session failure
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session connection error")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(SessionError) as exc_info:
            await core_operations.stream_upload(
                data_stream(),
                mime="text/plain",
                summary="Test",
                session_id="test-session",
            )

        assert "Metadata storage failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_upload_provider_error(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload with provider error."""

        async def data_stream():
            yield b"test"

        # Mock S3 failure
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.side_effect = Exception("Storage error")
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await core_operations.stream_upload(
                data_stream(),
                mime="text/plain",
                summary="Test",
                session_id="test-session",
            )

        assert "Streaming storage failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_upload_retry_logic(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_upload retry logic."""
        test_data = [b"test"]
        call_count = 0

        async def data_stream():
            for chunk in test_data:
                yield chunk

        # Mock S3 that fails twice then succeeds
        def create_s3_mock():
            nonlocal call_count
            call_count += 1
            mock = Mock(spec=[])
            if call_count <= 2:
                mock.put_object = AsyncMock(side_effect=Exception("Temporary failure"))
            else:
                mock.put_object = AsyncMock()
            return mock

        mock_artifact_store._s3_factory.side_effect = lambda: create_storage_ctx(
            create_s3_mock()
        )

        def create_storage_ctx(s3):
            ctx = AsyncMock()
            ctx.__aenter__.return_value = s3
            ctx.__aexit__.return_value = None
            return ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("asyncio.sleep", new_callable=AsyncMock):
            artifact_id = await core_operations.stream_upload(
                data_stream(),
                mime="text/plain",
                summary="Retry test",
                session_id="test-session",
            )

        assert isinstance(artifact_id, str)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_stream_download_closed_store(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError):
            async for _ in core_operations.stream_download("test123"):
                pass

    @pytest.mark.asyncio
    async def test_stream_download_with_native_streaming(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download with native streaming support."""
        artifact_id = "test123"
        test_chunks = [b"chunk1", b"chunk2", b"chunk3"]
        combined_data = b"".join(test_chunks)

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(combined_data),
            sha256=hashlib.sha256(combined_data).hexdigest(),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        # Mock S3 with native streaming
        async def mock_stream(**kwargs):
            for chunk in test_chunks:
                yield chunk

        mock_s3 = AsyncMock()
        mock_s3.get_object_stream = mock_stream

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Collect streamed data
        received_chunks = []
        async for chunk in core_operations.stream_download(artifact_id):
            received_chunks.append(chunk)

        assert b"".join(received_chunks) == combined_data

    @pytest.mark.asyncio
    async def test_stream_download_native_streaming_sha256_mismatch(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download with native streaming and SHA256 mismatch."""
        artifact_id = "test123"
        test_chunks = [b"chunk1", b"chunk2"]

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=12,
            sha256="wronghash123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        async def mock_stream(**kwargs):
            for chunk in test_chunks:
                yield chunk

        mock_s3 = AsyncMock()
        mock_s3.get_object_stream = mock_stream

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            async for _ in core_operations.stream_download(artifact_id):
                pass

        assert "SHA256 mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_download_fallback_with_readable_body(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download fallback with readable body."""
        artifact_id = "test123"
        test_data = b"test content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            sha256=hashlib.sha256(test_data).hexdigest(),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        # Mock S3 without native streaming
        mock_body = AsyncMock()
        mock_body.read.return_value = test_data

        mock_s3 = Mock(spec=[])  # No get_object_stream
        mock_s3.get_object = AsyncMock(return_value={"Body": mock_body})

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        received_data = b""
        async for chunk in core_operations.stream_download(artifact_id, chunk_size=5):
            received_data += chunk

        assert received_data == test_data
        mock_body.read.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_download_fallback_with_bytes_body(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download fallback with bytes body."""
        artifact_id = "test123"
        test_data = b"test content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = Mock(spec=[])
        mock_s3.get_object = AsyncMock(return_value={"Body": test_data})

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        received_data = b""
        async for chunk in core_operations.stream_download(artifact_id):
            received_data += chunk

        assert received_data == test_data

    @pytest.mark.asyncio
    async def test_stream_download_fallback_with_other_body_type(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download fallback with other body type."""
        artifact_id = "test123"
        test_data = b"test content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = Mock(spec=[])
        # Use bytearray to trigger bytes() conversion
        mock_s3.get_object = AsyncMock(return_value={"Body": bytearray(test_data)})

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        received_data = b""
        async for chunk in core_operations.stream_download(artifact_id):
            received_data += chunk

        assert received_data == bytes(test_data)

    @pytest.mark.asyncio
    async def test_stream_download_fallback_sha256_mismatch(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download fallback with SHA256 mismatch."""
        artifact_id = "test123"
        test_data = b"test content"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            sha256="wronghash",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = Mock(spec=[])
        mock_s3.get_object = AsyncMock(return_value={"Body": test_data})

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            async for _ in core_operations.stream_download(artifact_id):
                pass

        assert "SHA256 mismatch" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_download_with_progress_callback(
        self, core_operations, mock_artifact_store
    ):
        """Test stream_download with progress callback."""
        artifact_id = "test123"
        test_data = b"test content for progress"
        progress_calls = []

        def progress_callback(bytes_sent, total):
            progress_calls.append((bytes_sent, total))

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=len(test_data),
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        mock_s3 = Mock(spec=[])
        mock_s3.get_object = AsyncMock(return_value={"Body": test_data})

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        async for _ in core_operations.stream_download(
            artifact_id, chunk_size=5, progress_callback=progress_callback
        ):
            pass

        # Verify progress was reported
        assert len(progress_calls) > 0

    @pytest.mark.asyncio
    async def test_stream_download_error(self, core_operations, mock_artifact_store):
        """Test stream_download error handling."""
        artifact_id = "test123"

        record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        core_operations._get_record = AsyncMock(return_value=record)

        # Mock S3 failure
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.side_effect = Exception("Download error")
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            async for _ in core_operations.stream_download(artifact_id):
                pass

        assert "Streaming retrieval failed" in str(exc_info.value)


class TestGetRecordErrorPaths:
    """Test _get_record error handling."""

    @pytest.mark.asyncio
    async def test_get_record_session_error(self, core_operations, mock_artifact_store):
        """Test _get_record with session error."""
        artifact_id = "test123"

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session connection error")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(SessionError) as exc_info:
            await core_operations._get_record(artifact_id)

        assert "Session error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_record_not_found(self, core_operations, mock_artifact_store):
        """Test _get_record when artifact not found."""
        artifact_id = "nonexistent"

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(Exception) as exc_info:
            await core_operations._get_record(artifact_id)

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_record_corrupted_metadata(
        self, core_operations, mock_artifact_store
    ):
        """Test _get_record with corrupted metadata."""
        artifact_id = "test123"

        mock_session = AsyncMock()
        mock_session.get.return_value = "invalid json {"

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ProviderError) as exc_info:
            await core_operations._get_record(artifact_id)

        assert "Corrupted metadata" in str(exc_info.value)


class TestDefaultConstants:
    """Test default constants and configuration."""

    def test_default_ttl_constant(self):
        """Test that default TTL constant is defined correctly."""
        assert _DEFAULT_TTL == 900
        assert isinstance(_DEFAULT_TTL, int)
        assert _DEFAULT_TTL > 0
