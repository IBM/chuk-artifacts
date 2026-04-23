# -*- coding: utf-8 -*-
# tests/test_admin.py
"""
Tests for chuk_artifacts.admin module.

Tests administrative and debugging operations for the artifact store.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from chuk_artifacts.admin import AdminOperations


@pytest.fixture
def mock_artifact_store():
    """Create a mock ArtifactStore for testing."""
    store = Mock()
    store.bucket = "test-bucket"
    store.sandbox_id = "test-sandbox"
    store.max_retries = 3
    store.session_ttl_hours = 24
    store._closed = False
    store._storage_provider_name = "memory"
    store._session_provider_name = "memory"

    # Mock session manager
    store._session_manager = AsyncMock()

    # Mock factories
    store._s3_factory = Mock()
    store._session_factory = Mock()

    # Mock grid operations
    store.get_session_prefix_pattern = Mock()
    store.get_session_prefix_pattern.return_value = "grid/test-sandbox/"

    return store


@pytest.fixture
def admin_operations(mock_artifact_store):
    """Create AdminOperations instance for testing."""
    return AdminOperations(mock_artifact_store)


class TestAdminOperationsInitialization:
    """Test AdminOperations initialization."""

    def test_initialization(self, mock_artifact_store):
        """Test that AdminOperations initializes correctly."""
        admin_ops = AdminOperations(mock_artifact_store)

        assert admin_ops.artifact_store is mock_artifact_store
        assert admin_ops.store is mock_artifact_store  # backward compatibility

    def test_initialization_with_none_store(self):
        """Test initialization with None store."""
        admin_ops = AdminOperations(None)
        assert admin_ops.artifact_store is None
        assert admin_ops.store is None


class TestValidateConfiguration:
    """Test the validate_configuration method."""

    @pytest.mark.asyncio
    async def test_validate_configuration_all_success(
        self, admin_operations, mock_artifact_store
    ):
        """Test successful validation of all components."""
        # Mock successful session provider test
        mock_session = AsyncMock()
        mock_session.setex = AsyncMock()
        mock_session.get = AsyncMock(return_value="test_value")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage provider test
        mock_s3 = AsyncMock()
        mock_s3.head_bucket = AsyncMock()

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock successful session manager test
        test_session_id = "test-session-123"
        mock_artifact_store._session_manager.allocate_session.return_value = (
            test_session_id
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Check result structure
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)

        # Check session provider validation
        assert result["session"]["status"] == "ok"
        assert result["session"]["provider"] == "memory"

        # Check storage provider validation
        assert result["storage"]["status"] == "ok"
        assert result["storage"]["bucket"] == "test-bucket"
        assert result["storage"]["provider"] == "memory"

        # Check session manager validation
        assert result["session_manager"]["status"] == "ok"
        assert result["session_manager"]["sandbox_id"] == "test-sandbox"
        assert result["session_manager"]["test_session"] == test_session_id

        # Verify cleanup was called
        mock_artifact_store._session_manager.delete_session.assert_called_once_with(
            test_session_id
        )

    @pytest.mark.asyncio
    async def test_validate_configuration_session_provider_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when session provider fails."""
        # Mock failing session provider
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session connection failed")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage provider
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock successful session manager
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Check session provider failed
        assert result["session"]["status"] == "error"
        assert "Session connection failed" in result["session"]["message"]
        assert result["session"]["provider"] == "memory"

        # Check others succeeded
        assert result["storage"]["status"] == "ok"
        assert result["session_manager"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_validate_configuration_storage_provider_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when storage provider fails."""
        # Mock successful session provider
        mock_session = AsyncMock()
        mock_session.get.return_value = "test_value"
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock failing storage provider
        mock_s3 = AsyncMock()
        mock_s3.head_bucket.side_effect = Exception("Bucket not found")
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock successful session manager
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Check storage provider failed
        assert result["storage"]["status"] == "error"
        assert "Bucket not found" in result["storage"]["message"]
        assert result["storage"]["provider"] == "memory"

        # Check others succeeded
        assert result["session"]["status"] == "ok"
        assert result["session_manager"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_validate_configuration_session_manager_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when session manager fails."""
        # Mock successful session provider
        mock_session = AsyncMock()
        mock_session.get.return_value = "test_value"
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage provider
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock failing session manager
        mock_artifact_store._session_manager.allocate_session.side_effect = Exception(
            "Session manager failed"
        )

        result = await admin_operations.validate_configuration()

        # Check session manager failed
        assert result["session_manager"]["status"] == "error"
        assert "Session manager failed" in result["session_manager"]["message"]

        # Check others succeeded
        assert result["session"]["status"] == "ok"
        assert result["storage"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_validate_configuration_session_test_value_mismatch(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when session test returns wrong value."""
        # Mock session provider returning wrong value
        mock_session = AsyncMock()
        mock_session.setex = AsyncMock()
        mock_session.get = AsyncMock(return_value="wrong_value")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage provider
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock successful session manager
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Check session provider failed due to value mismatch
        assert result["session"]["status"] == "error"
        assert "Session store test failed" in result["session"]["message"]
        assert result["session"]["provider"] == "memory"

    @pytest.mark.asyncio
    async def test_validate_configuration_session_manager_validation_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when session manager validation returns False."""
        # Mock successful session provider
        mock_session = AsyncMock()
        mock_session.get.return_value = "test_value"
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage provider
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session manager with failed validation
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = (
            False  # Validation fails
        )
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Check session manager failed validation
        assert result["session_manager"]["status"] == "error"
        assert "Session validation failed" in result["session_manager"]["message"]


class TestGetStats:
    """Test the get_stats method."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, admin_operations, mock_artifact_store):
        """Test successful stats collection."""
        # Mock session manager stats (synchronous method)
        session_stats = {"cache_hits": 100, "cache_misses": 10, "total_sessions": 50}
        mock_artifact_store._session_manager.get_cache_stats = Mock(
            return_value=session_stats
        )

        result = await admin_operations.get_stats()

        # Check base stats
        expected_base_stats = {
            "storage_provider": "memory",
            "session_provider": "memory",
            "bucket": "test-bucket",
            "max_retries": 3,
            "closed": False,
            "sandbox_id": "test-sandbox",
            "session_ttl_hours": 24,
        }

        for key, value in expected_base_stats.items():
            assert result[key] == value

        # Check session manager stats
        assert result["session_manager"] == session_stats

    @pytest.mark.asyncio
    async def test_get_stats_session_manager_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test stats collection when session manager fails."""
        # Mock session manager stats failure (synchronous method)
        mock_artifact_store._session_manager.get_cache_stats = Mock(
            side_effect=Exception("Stats unavailable")
        )

        result = await admin_operations.get_stats()

        # Check that base stats are still returned
        assert result["storage_provider"] == "memory"
        assert result["bucket"] == "test-bucket"

        # Check session manager error handling
        assert result["session_manager"]["error"] == "Stats unavailable"
        assert result["session_manager"]["status"] == "unavailable"

    @pytest.mark.asyncio
    async def test_get_stats_different_values(self, mock_artifact_store):
        """Test stats with different store values."""
        # Configure store with different values
        mock_artifact_store.bucket = "production-bucket"
        mock_artifact_store.sandbox_id = "prod-sandbox"
        mock_artifact_store.max_retries = 5
        mock_artifact_store.session_ttl_hours = 48
        mock_artifact_store._closed = True
        mock_artifact_store._storage_provider_name = "s3"
        mock_artifact_store._session_provider_name = "redis"

        mock_artifact_store._session_manager.get_cache_stats = Mock(
            return_value={"sessions": 25}
        )

        admin_ops = AdminOperations(mock_artifact_store)
        result = await admin_ops.get_stats()

        assert result["bucket"] == "production-bucket"
        assert result["sandbox_id"] == "prod-sandbox"
        assert result["max_retries"] == 5
        assert result["session_ttl_hours"] == 48
        assert result["closed"] is True
        assert result["storage_provider"] == "s3"
        assert result["session_provider"] == "redis"


class TestCleanupAllExpired:
    """Test the cleanup_all_expired method."""

    @pytest.mark.asyncio
    async def test_cleanup_all_expired_success(
        self, admin_operations, mock_artifact_store
    ):
        """Test successful cleanup of expired resources."""
        # Mock session manager cleanup
        mock_artifact_store._session_manager.cleanup_expired_sessions.return_value = 5

        result = await admin_operations.cleanup_all_expired()

        # Check result structure
        assert "timestamp" in result
        assert isinstance(result["timestamp"], str)

        # Check cleanup results
        assert result["expired_sessions_cleaned"] == 5
        assert result["expired_artifacts_cleaned"] == 0  # Placeholder
        assert "session_cleanup_error" not in result

        # Verify cleanup was called
        mock_artifact_store._session_manager.cleanup_expired_sessions.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_all_expired_session_failure(
        self, admin_operations, mock_artifact_store
    ):
        """Test cleanup when session cleanup fails."""
        # Mock session manager cleanup failure
        mock_artifact_store._session_manager.cleanup_expired_sessions.side_effect = (
            Exception("Cleanup failed")
        )

        result = await admin_operations.cleanup_all_expired()

        # Check error handling
        assert result["session_cleanup_error"] == "Cleanup failed"
        assert result["expired_sessions_cleaned"] == 0
        assert result["expired_artifacts_cleaned"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_all_expired_timestamp_format(
        self, admin_operations, mock_artifact_store
    ):
        """Test that cleanup returns properly formatted timestamp."""
        mock_artifact_store._session_manager.cleanup_expired_sessions.return_value = 3

        # Mock datetime to control timestamp
        with patch("chuk_artifacts.admin.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.isoformat.return_value.replace.return_value = (
                "2023-12-01T10:30:00Z"
            )
            mock_datetime.now.return_value = mock_now

            result = await admin_operations.cleanup_all_expired()

        assert result["timestamp"] == "2023-12-01T10:30:00Z"


class TestGetSandboxInfo:
    """Test the get_sandbox_info method."""

    @pytest.mark.asyncio
    async def test_get_sandbox_info(self, admin_operations, mock_artifact_store):
        """Test getting sandbox information."""
        result = await admin_operations.get_sandbox_info()

        expected_result = {
            "sandbox_id": "test-sandbox",
            "session_prefix_pattern": "grid/test-sandbox/",
            "grid_architecture": {
                "enabled": True,
                "pattern": "grid/{sandbox_id}/{session_id}/{artifact_id}",
                "mandatory_sessions": True,
                "federation_ready": True,
            },
        }

        assert result == expected_result

        # Verify get_session_prefix_pattern was called
        mock_artifact_store.get_session_prefix_pattern.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sandbox_info_different_sandbox(self, mock_artifact_store):
        """Test sandbox info with different sandbox ID."""
        mock_artifact_store.sandbox_id = "production-env"
        mock_artifact_store.get_session_prefix_pattern.return_value = (
            "grid/production-env/"
        )

        admin_ops = AdminOperations(mock_artifact_store)
        result = await admin_ops.get_sandbox_info()

        assert result["sandbox_id"] == "production-env"
        assert result["session_prefix_pattern"] == "grid/production-env/"
        assert result["grid_architecture"]["enabled"] is True


class TestAdminOperationsIntegration:
    """Integration tests for admin operations."""

    @pytest.mark.asyncio
    async def test_complete_admin_workflow(self, admin_operations, mock_artifact_store):
        """Test complete admin workflow."""
        # Setup mocks for all operations
        mock_session = AsyncMock()
        mock_session.get.return_value = "test_value"
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True
        mock_artifact_store._session_manager.get_cache_stats = Mock(
            return_value={"sessions": 10}
        )
        mock_artifact_store._session_manager.cleanup_expired_sessions.return_value = 2

        # Test validation
        validation_result = await admin_operations.validate_configuration()
        assert validation_result["session"]["status"] == "ok"
        assert validation_result["storage"]["status"] == "ok"
        assert validation_result["session_manager"]["status"] == "ok"

        # Test stats
        stats_result = await admin_operations.get_stats()
        assert stats_result["storage_provider"] == "memory"
        assert stats_result["session_manager"]["sessions"] == 10

        # Test cleanup
        cleanup_result = await admin_operations.cleanup_all_expired()
        assert cleanup_result["expired_sessions_cleaned"] == 2

        # Test sandbox info
        sandbox_result = await admin_operations.get_sandbox_info()
        assert sandbox_result["sandbox_id"] == "test-sandbox"


class TestAdminOperationsEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_validate_configuration_with_none_session_response(
        self, admin_operations, mock_artifact_store
    ):
        """Test validation when session get returns None."""
        mock_session = AsyncMock()
        mock_session.setex = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock successful storage and session manager
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        result = await admin_operations.validate_configuration()

        # Should treat None as test failure
        assert result["session"]["status"] == "error"
        assert "Session store test failed" in result["session"]["message"]

    @pytest.mark.asyncio
    async def test_get_stats_with_closed_store(
        self, admin_operations, mock_artifact_store
    ):
        """Test stats collection with closed store."""
        mock_artifact_store._closed = True
        mock_artifact_store._session_manager.get_cache_stats = Mock(
            return_value={"closed": True}
        )

        result = await admin_operations.get_stats()

        assert result["closed"] is True
        assert result["session_manager"]["closed"] is True

    def test_backward_compatibility_store_reference(
        self, admin_operations, mock_artifact_store
    ):
        """Test that both artifact_store and store references work."""
        assert admin_operations.artifact_store is mock_artifact_store
        assert admin_operations.store is mock_artifact_store
        assert admin_operations.artifact_store is admin_operations.store


class TestUniqueKeyGeneration:
    """Test unique key generation in validation."""

    @pytest.mark.asyncio
    async def test_unique_test_keys(self, admin_operations, mock_artifact_store):
        """Test that validation uses unique test keys."""
        # Capture the test keys used
        test_keys = []

        mock_session = AsyncMock()
        mock_session.get.return_value = "test_value"

        def capture_setex(key, ttl, value):
            test_keys.append(key)
            return AsyncMock()

        mock_session.setex.side_effect = capture_setex

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock other components
        mock_s3 = AsyncMock()
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store._session_manager.validate_session.return_value = True
        mock_artifact_store._session_manager.delete_session.return_value = True

        # Run validation multiple times
        await admin_operations.validate_configuration()
        await admin_operations.validate_configuration()

        # Should have used unique keys
        assert len(test_keys) == 2
        assert test_keys[0] != test_keys[1]
        assert all(key.startswith("test_") for key in test_keys)
        assert all(len(key) == 37 for key in test_keys)  # "test_" + 32 char UUID hex
