# -*- coding: utf-8 -*-
# tests/test_batch.py
"""
Tests for chuk_artifacts.batch module.

Tests batch operations for storing multiple artifacts.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from chuk_artifacts.batch import BatchOperations, _DEFAULT_TTL
from chuk_artifacts.exceptions import ArtifactStoreError


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

    # Mock session manager
    store._session_manager = AsyncMock()
    store._session_manager.allocate_session = AsyncMock()

    # Mock factories
    store._s3_factory = Mock()
    store._session_factory = Mock()

    # Mock grid operations
    store.generate_artifact_key = Mock()

    return store


@pytest.fixture
def batch_operations(mock_artifact_store):
    """Create BatchOperations instance for testing."""
    return BatchOperations(mock_artifact_store)


@pytest.fixture
def sample_batch_items():
    """Create sample batch items for testing."""
    return [
        {
            "data": b"test data 1",
            "mime": "text/plain",
            "summary": "Test file 1",
            "filename": "test1.txt",
            "meta": {"type": "test"},
        },
        {
            "data": b"test data 2",
            "mime": "text/plain",
            "summary": "Test file 2",
            "filename": "test2.txt",
        },
        {
            "data": b"binary data",
            "mime": "application/octet-stream",
            "summary": "Binary file",
            "meta": {"binary": True},
        },
    ]


class TestBatchOperationsInitialization:
    """Test BatchOperations initialization."""

    def test_initialization(self, mock_artifact_store):
        """Test that BatchOperations initializes correctly."""
        batch_ops = BatchOperations(mock_artifact_store)
        assert batch_ops.artifact_store is mock_artifact_store

    def test_initialization_with_none_store(self):
        """Test initialization with None store."""
        batch_ops = BatchOperations(None)
        assert batch_ops.artifact_store is None


class TestStoreBatch:
    """Test the store_batch method."""

    @pytest.mark.asyncio
    async def test_store_batch_success(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test successful batch storage."""
        # Mock session allocation
        session_id = "test-session-123"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id

        # Mock artifact key generation
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

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

        # Execute batch store
        result = await batch_operations.store_batch(sample_batch_items)

        # Verify results
        assert len(result) == 3
        assert all(isinstance(aid, str) for aid in result)
        assert all(len(aid) == 32 for aid in result)  # UUID hex length

        # Verify session allocation
        mock_artifact_store._session_manager.allocate_session.assert_called_once()

        # Verify storage calls
        assert mock_s3.put_object.call_count == 3
        assert mock_session.setex.call_count == 3

        # Verify artifact key generation
        assert mock_artifact_store.generate_artifact_key.call_count == 3

    @pytest.mark.asyncio
    async def test_store_batch_with_existing_session(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test batch storage with existing session ID."""
        existing_session = "existing-session-456"

        # Mock session allocation with existing session
        mock_artifact_store._session_manager.allocate_session.return_value = (
            existing_session
        )

        # Mock other operations
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

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

        # Execute with existing session
        result = await batch_operations.store_batch(
            sample_batch_items, session_id=existing_session
        )

        assert len(result) == 3

        # Verify session allocation was called with existing session
        mock_artifact_store._session_manager.allocate_session.assert_called_once_with(
            session_id=existing_session
        )

    @pytest.mark.asyncio
    async def test_store_batch_empty_list(self, batch_operations, mock_artifact_store):
        """Test batch storage with empty item list."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id

        result = await batch_operations.store_batch([])

        assert result == []
        mock_artifact_store._session_manager.allocate_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_batch_closed_store(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test batch storage when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await batch_operations.store_batch(sample_batch_items)

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_store_batch_partial_failure(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test batch storage with some items failing."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        # Mock the _store_with_retry method to fail on the second item
        original_store_with_retry = batch_operations._store_with_retry
        call_count = 0

        async def mock_store_with_retry(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call fails
                raise Exception("Storage failure")
            # For other calls, just return success (don't actually call storage)
            return

        batch_operations._store_with_retry = mock_store_with_retry

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("chuk_artifacts.batch.logger") as mock_logger:
            result = await batch_operations.store_batch(sample_batch_items)

        # Should have 3 results with None for failed item
        assert len(result) == 3
        assert result[0] is not None  # First succeeded
        assert result[1] is None  # Second failed
        assert result[2] is not None  # Third succeeded

        # Should have logged the failure and warning
        mock_logger.error.assert_called()
        mock_logger.warning.assert_called()

        # Restore original method
        batch_operations._store_with_retry = original_store_with_retry

    @pytest.mark.asyncio
    async def test_store_batch_metadata_content(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test that batch storage creates correct metadata."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        # Mock storage
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Capture metadata calls
        metadata_calls = []
        mock_session = AsyncMock()

        def capture_setex(artifact_id, ttl, data):
            metadata_calls.append((artifact_id, ttl, json.loads(data)))
            return AsyncMock()

        mock_session.setex.side_effect = capture_setex
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await batch_operations.store_batch(sample_batch_items, ttl=1800)

        # Verify metadata was stored correctly
        assert len(metadata_calls) == 3

        for i, (artifact_id, ttl, metadata) in enumerate(metadata_calls):
            assert artifact_id == result[i]
            assert ttl == 1800
            assert metadata["artifact_id"] == artifact_id
            assert metadata["session_id"] == session_id
            assert metadata["sandbox_id"] == "test-sandbox"
            assert metadata["mime"] == sample_batch_items[i]["mime"]
            assert metadata["summary"] == sample_batch_items[i]["summary"]
            assert metadata["bytes"] == len(sample_batch_items[i]["data"])
            assert metadata["batch_operation"] is True
            assert metadata["batch_index"] == i
            assert "sha256" in metadata
            assert "stored_at" in metadata

    @pytest.mark.asyncio
    async def test_store_batch_custom_ttl(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test batch storage with custom TTL."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

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
        await batch_operations.store_batch(sample_batch_items, ttl=custom_ttl)

        # Verify TTL was used in setex calls
        for call in mock_session.setex.call_args_list:
            args, kwargs = call
            assert args[1] == custom_ttl  # TTL argument

    @pytest.mark.asyncio
    async def test_store_batch_data_integrity(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test that batch storage preserves data integrity."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        # Capture storage calls
        storage_calls = []
        mock_s3 = AsyncMock()

        def capture_put_object(**kwargs):
            storage_calls.append(kwargs)
            return AsyncMock()

        mock_s3.put_object.side_effect = capture_put_object
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        await batch_operations.store_batch(sample_batch_items)

        # Verify storage calls have correct data
        assert len(storage_calls) == 3

        for i, call in enumerate(storage_calls):
            assert call["Body"] == sample_batch_items[i]["data"]
            assert call["ContentType"] == sample_batch_items[i]["mime"]
            assert call["Bucket"] == "test-bucket"
            assert "Key" in call
            assert call["Metadata"]["session_id"] == session_id
            assert call["Metadata"]["sandbox_id"] == "test-sandbox"


class TestStoreWithRetry:
    """Test the _store_with_retry method."""

    @pytest.mark.asyncio
    async def test_store_with_retry_success_first_attempt(
        self, batch_operations, mock_artifact_store
    ):
        """Test successful storage on first attempt."""
        mock_s3 = AsyncMock()
        mock_s3.put_object = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Should not raise any exception
        await batch_operations._store_with_retry(
            b"test data", "test/key", "text/plain", "test.txt", "session123"
        )

        mock_s3.put_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_with_retry_success_after_failures(
        self, batch_operations, mock_artifact_store
    ):
        """Test successful storage after some failures."""
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

        with patch("chuk_artifacts.batch.logger") as mock_logger:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await batch_operations._store_with_retry(
                    b"test data", "test/key", "text/plain", "test.txt", "session123"
                )

        # Should have made 3 attempts
        assert mock_s3.put_object.call_count == 3

        # Should have slept between retries (exponential backoff)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)  # 2^0
        mock_sleep.assert_any_call(2)  # 2^1

        # Should have logged warnings
        assert mock_logger.warning.call_count == 2

    @pytest.mark.asyncio
    async def test_store_with_retry_all_attempts_fail(
        self, batch_operations, mock_artifact_store
    ):
        """Test when all retry attempts fail."""
        mock_s3 = AsyncMock()
        mock_s3.put_object.side_effect = Exception("Persistent failure")
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("chuk_artifacts.batch.logger") as mock_logger:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(Exception) as exc_info:
                    await batch_operations._store_with_retry(
                        b"test data", "test/key", "text/plain", "test.txt", "session123"
                    )

        assert "Persistent failure" in str(exc_info.value)

        # Should have made max_retries attempts
        assert mock_s3.put_object.call_count == mock_artifact_store.max_retries

        # Should have logged error for final failure
        mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_store_with_retry_exponential_backoff(
        self, batch_operations, mock_artifact_store
    ):
        """Test exponential backoff timing."""
        mock_artifact_store.max_retries = 4  # More retries to test backoff

        mock_s3 = AsyncMock()
        mock_s3.put_object.side_effect = Exception("Always fails")
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(Exception):
                await batch_operations._store_with_retry(
                    b"test data", "test/key", "text/plain", "test.txt", "session123"
                )

        # Should have slept with exponential backoff: 1, 2, 4 seconds
        expected_sleeps = [1, 2, 4]  # 2^0, 2^1, 2^2
        actual_sleeps = [call[0][0] for call in mock_sleep.call_args_list]
        assert actual_sleeps == expected_sleeps

    @pytest.mark.asyncio
    async def test_store_with_retry_logging(
        self, batch_operations, mock_artifact_store
    ):
        """Test retry logging behavior."""
        mock_s3 = AsyncMock()
        mock_s3.put_object.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            AsyncMock(),  # Third attempt succeeds
        ]
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("chuk_artifacts.batch.logger") as mock_logger:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                await batch_operations._store_with_retry(
                    b"test data", "test/key", "text/plain", "test.txt", "session123"
                )

        # Should have logged warnings for first two attempts
        assert mock_logger.warning.call_count == 2

        # Check log message content
        warning_calls = mock_logger.warning.call_args_list
        assert "Batch storage attempt 1 failed" in str(warning_calls[0])
        assert "Batch storage attempt 2 failed" in str(warning_calls[1])


class TestBatchOperationsEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_store_batch_missing_required_fields(
        self, batch_operations, mock_artifact_store
    ):
        """Test batch storage with items missing required fields."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id

        # Item missing required fields
        invalid_items = [
            {"data": b"test", "mime": "text/plain"},  # Missing summary
            {"data": b"test", "summary": "test"},  # Missing mime
            {"mime": "text/plain", "summary": "test"},  # Missing data
        ]

        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        # Mock storage operations to track if they're called
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

        with patch("chuk_artifacts.batch.logger") as mock_logger:
            result = await batch_operations.store_batch(invalid_items)

        # All items should fail
        assert result == [None, None, None]

        # Should have logged errors (exact count may vary based on which step fails)
        assert mock_logger.error.call_count >= 3
        assert mock_logger.warning.call_count >= 1  # Final warning about failures

    @pytest.mark.asyncio
    async def test_store_batch_none_filename(
        self, batch_operations, mock_artifact_store
    ):
        """Test batch storage with None filename."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        items = [
            {
                "data": b"test data",
                "mime": "text/plain",
                "summary": "Test file",
                "filename": None,
            }
        ]

        # Capture storage call
        storage_calls = []
        mock_s3 = AsyncMock()

        def capture_put_object(**kwargs):
            storage_calls.append(kwargs)
            return AsyncMock()

        mock_s3.put_object.side_effect = capture_put_object
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await batch_operations.store_batch(items)

        # Should succeed with empty filename
        assert len(result) == 1
        assert result[0] is not None

        # Storage call should have empty filename
        assert storage_calls[0]["Metadata"]["filename"] == ""

    @pytest.mark.asyncio
    async def test_store_batch_large_data(self, batch_operations, mock_artifact_store):
        """Test batch storage with large data items."""
        session_id = "test-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid, aid, mime_type=None, filename=None: f"grid/{sid}/{aid}"
        )

        # Create large data item
        large_data = b"x" * (10 * 1024 * 1024)  # 10MB
        items = [
            {
                "data": large_data,
                "mime": "application/octet-stream",
                "summary": "Large file",
            }
        ]

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

        result = await batch_operations.store_batch(items)

        # Should handle large data
        assert len(result) == 1
        assert result[0] is not None

        # Verify storage call received large data
        put_object_call = mock_s3.put_object.call_args[1]
        assert len(put_object_call["Body"]) == len(large_data)


class TestBatchOperationsIntegration:
    """Integration tests for batch operations."""

    @pytest.mark.asyncio
    async def test_batch_operations_workflow(
        self, batch_operations, mock_artifact_store, sample_batch_items
    ):
        """Test complete batch operations workflow."""
        # Setup mocks for complete workflow
        session_id = "integration-session"
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.side_effect = (
            lambda sid,
            aid,
            mime_type=None,
            filename=None: f"grid/{mock_artifact_store.sandbox_id}/{sid}/{aid}"
        )

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

        # Execute batch operation
        result = await batch_operations.store_batch(sample_batch_items, ttl=1200)

        # Verify complete workflow
        assert len(result) == len(sample_batch_items)
        assert all(aid is not None for aid in result)

        # Verify session management
        mock_artifact_store._session_manager.allocate_session.assert_called_once()

        # Verify storage operations
        assert mock_s3.put_object.call_count == len(sample_batch_items)
        assert mock_session.setex.call_count == len(sample_batch_items)

        # Verify artifact key generation
        assert mock_artifact_store.generate_artifact_key.call_count == len(
            sample_batch_items
        )


class TestDefaultConstants:
    """Test default constants and configuration."""

    def test_default_ttl_constant(self):
        """Test that default TTL constant is defined correctly."""
        assert _DEFAULT_TTL == 900
        assert isinstance(_DEFAULT_TTL, int)
        assert _DEFAULT_TTL > 0
