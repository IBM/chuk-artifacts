"""
Comprehensive tests for types.py module.

Tests all enums, constants, and response models for full coverage.
"""

from chuk_artifacts.types import (
    # Enums
    StorageScope,
    StorageProvider,
    SessionProvider,
    OperationStatus,
    # Constants
    DEFAULT_TTL,
    DEFAULT_PRESIGN_EXPIRES,
    DEFAULT_SESSION_TTL_HOURS,
    DEFAULT_BUCKET,
    DEFAULT_SANDBOX_PREFIX,
    # Response Models
    ProviderStatus,
    ValidationResponse,
    SessionStats,
    StorageStats,
    StatsResponse,
    SessionInfo,
    SandboxInfo,
    PresignedUploadResponse,
    MultipartUploadInitResponse,
    UpdateMetadataResponse,
    BatchStoreResponse,
)


class TestEnums:
    """Test enum definitions and values."""

    def test_storage_scope_enum(self):
        """Test StorageScope enum values."""
        assert StorageScope.SESSION == "session"
        assert StorageScope.USER == "user"
        assert StorageScope.SANDBOX == "sandbox"

        # Test from string
        assert StorageScope("session") == StorageScope.SESSION
        assert StorageScope("user") == StorageScope.USER
        assert StorageScope("sandbox") == StorageScope.SANDBOX

    def test_storage_provider_enum(self):
        """Test StorageProvider enum values."""
        assert StorageProvider.MEMORY == "memory"
        assert StorageProvider.FILESYSTEM == "filesystem"
        assert StorageProvider.S3 == "s3"
        assert StorageProvider.IBM_COS == "ibm_cos"
        assert StorageProvider.VFS == "vfs"
        assert StorageProvider.VFS_MEMORY == "vfs-memory"
        assert StorageProvider.VFS_FILESYSTEM == "vfs-filesystem"
        assert StorageProvider.VFS_S3 == "vfs-s3"
        assert StorageProvider.VFS_SQLITE == "vfs-sqlite"

    def test_session_provider_enum(self):
        """Test SessionProvider enum values."""
        assert SessionProvider.MEMORY == "memory"
        assert SessionProvider.REDIS == "redis"

    def test_operation_status_enum(self):
        """Test OperationStatus enum values."""
        assert OperationStatus.SUCCESS == "success"
        assert OperationStatus.FAILED == "failed"
        assert OperationStatus.HEALTHY == "healthy"
        assert OperationStatus.UNHEALTHY == "unhealthy"
        assert OperationStatus.UNKNOWN == "unknown"
        assert OperationStatus.OK == "ok"
        assert OperationStatus.ERROR == "error"


class TestConstants:
    """Test constant values."""

    def test_constants(self):
        """Test all constants are defined correctly."""
        assert DEFAULT_TTL == 900
        assert DEFAULT_PRESIGN_EXPIRES == 3600
        assert DEFAULT_SESSION_TTL_HOURS == 24
        assert DEFAULT_BUCKET == "artifacts"
        assert DEFAULT_SANDBOX_PREFIX == "sandbox"


class TestProviderStatus:
    """Test ProviderStatus model."""

    def test_provider_status_creation(self):
        """Test creating ProviderStatus."""
        status = ProviderStatus(
            status=OperationStatus.HEALTHY,
            provider="memory",
            message="All good",
            details={"bucket": "test"},
        )
        assert status.status == OperationStatus.HEALTHY
        assert status.provider == "memory"
        assert status.message == "All good"
        assert status.details == {"bucket": "test"}

    def test_provider_status_dict_access(self):
        """Test dict-style access to ProviderStatus."""
        status = ProviderStatus(
            status=OperationStatus.OK, provider="memory", details={"bucket": "test"}
        )

        # Test __getitem__
        assert status["status"] == OperationStatus.OK
        assert status["provider"] == "memory"
        assert status["bucket"] == "test"  # From details

        # Test .get()
        assert status.get("status") == OperationStatus.OK
        assert status.get("nonexistent", "default") == "default"

        # Test __contains__
        assert "status" in status
        assert "provider" in status
        assert "bucket" in status  # From details
        assert "nonexistent" not in status

    def test_provider_status_optional_fields(self):
        """Test optional fields in ProviderStatus."""
        status = ProviderStatus(status=OperationStatus.SUCCESS, provider="s3")
        assert status.message is None
        assert status.details == {}


class TestValidationResponse:
    """Test ValidationResponse model."""

    def test_validation_response_creation(self):
        """Test creating ValidationResponse."""
        response = ValidationResponse(
            storage=ProviderStatus(status=OperationStatus.OK, provider="memory"),
            session=ProviderStatus(status=OperationStatus.OK, provider="memory"),
            overall=OperationStatus.SUCCESS,
            timestamp="2025-01-01T00:00:00Z",
            session_manager={"status": "ok"},
        )
        assert response.overall == OperationStatus.SUCCESS
        assert response.timestamp == "2025-01-01T00:00:00Z"
        assert response.session_manager == {"status": "ok"}

    def test_validation_response_dict_access(self):
        """Test dict-style access."""
        response = ValidationResponse(
            storage=ProviderStatus(status=OperationStatus.OK, provider="memory"),
            session=ProviderStatus(status=OperationStatus.OK, provider="memory"),
            overall=OperationStatus.SUCCESS,
        )

        assert response["storage"].status == OperationStatus.OK
        assert response["session"].status == OperationStatus.OK
        assert response["overall"] == OperationStatus.SUCCESS

        assert response.get("storage") is not None
        assert response.get("nonexistent", "default") == "default"

        assert "storage" in response
        assert "session" in response
        assert "overall" in response
        assert "nonexistent" not in response


class TestSessionStats:
    """Test SessionStats model."""

    def test_session_stats_creation(self):
        """Test creating SessionStats."""
        stats = SessionStats(
            cache_hits=10, cache_misses=5, total_requests=15, hit_rate=0.67
        )
        assert stats.cache_hits == 10
        assert stats.cache_misses == 5
        assert stats.total_requests == 15
        assert stats.hit_rate == 0.67

    def test_session_stats_defaults(self):
        """Test default values."""
        stats = SessionStats()
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0
        assert stats.total_requests == 0
        assert stats.hit_rate == 0.0

    def test_session_stats_dict_equality(self):
        """Test equality with dicts."""
        stats = SessionStats(cache_hits=10, cache_misses=5)

        # Should match dict with same fields
        assert stats == {"cache_hits": 10, "cache_misses": 5}

        # Extra fields in model should be ignored when comparing to dict
        assert stats == {"cache_hits": 10}


class TestStorageStats:
    """Test StorageStats model."""

    def test_storage_stats_creation(self):
        """Test creating StorageStats."""
        stats = StorageStats(
            provider="memory",
            bucket="test-bucket",
            total_artifacts=100,
            total_bytes=1000000,
        )
        assert stats.provider == "memory"
        assert stats.bucket == "test-bucket"
        assert stats.total_artifacts == 100
        assert stats.total_bytes == 1000000

    def test_storage_stats_dict_access(self):
        """Test dict-style access."""
        stats = StorageStats(provider="memory", bucket="test")

        assert stats["provider"] == "memory"
        assert stats["bucket"] == "test"
        assert stats.get("provider") == "memory"
        assert stats.get("nonexistent", "default") == "default"

    def test_storage_stats_empty_dict_equality(self):
        """Test equality with empty dict."""
        stats = StorageStats()
        assert stats == {}  # All fields are None


class TestStatsResponse:
    """Test StatsResponse model."""

    def test_stats_response_creation(self):
        """Test creating StatsResponse."""
        response = StatsResponse(
            storage_provider="memory",
            session_provider="memory",
            bucket="test",
            sandbox_id="sandbox-123",
            total_artifacts=100,
            total_bytes=1000000,
        )
        assert response.storage_provider == "memory"
        assert response.session_provider == "memory"
        assert response.bucket == "test"
        assert response.sandbox_id == "sandbox-123"
        assert response.total_artifacts == 100
        assert response.total_bytes == 1000000

    def test_stats_response_dict_methods(self):
        """Test dict-like methods."""
        response = StatsResponse(
            storage_provider="memory",
            session_provider="memory",
            bucket="test",
            sandbox_id="sandbox-123",
        )

        # Test __getitem__
        assert response["storage_provider"] == "memory"

        # Test .get()
        assert response.get("storage_provider") == "memory"
        assert response.get("nonexistent", "default") == "default"

        # Test __contains__
        assert "storage_provider" in response
        assert "nonexistent" not in response

        # Test .keys(), .values(), .items()
        assert "storage_provider" in response.keys()
        assert "memory" in response.values()
        assert ("storage_provider", "memory") in response.items()


class TestSessionInfo:
    """Test SessionInfo model."""

    def test_session_info_creation(self):
        """Test creating SessionInfo."""
        info = SessionInfo(
            session_id="sess-123",
            sandbox_id="sandbox-123",
            user_id="user-123",
            created_at="2025-01-01T00:00:00Z",
            expires_at="2025-01-02T00:00:00Z",
            ttl_hours=24,
            metadata={"key": "value"},
        )
        assert info.session_id == "sess-123"
        assert info.sandbox_id == "sandbox-123"
        assert info.user_id == "user-123"
        assert info.created_at == "2025-01-01T00:00:00Z"
        assert info.expires_at == "2025-01-02T00:00:00Z"
        assert info.ttl_hours == 24
        assert info.metadata == {"key": "value"}

    def test_session_info_dict_methods(self):
        """Test dict-like methods."""
        info = SessionInfo(session_id="sess-123", sandbox_id="sandbox-123")

        # Test __getitem__
        assert info["session_id"] == "sess-123"

        # Test .get()
        assert info.get("session_id") == "sess-123"

        # Test .keys(), .values(), .items()
        assert "session_id" in info.keys()
        assert "sess-123" in info.values()
        assert ("session_id", "sess-123") in info.items()

    def test_session_info_dict_equality(self):
        """Test equality with dicts."""
        info = SessionInfo(session_id="sess-123", sandbox_id="sandbox-123")

        # Should match dict with subset of fields
        assert info == {"session_id": "sess-123"}


class TestSandboxInfo:
    """Test SandboxInfo model."""

    def test_sandbox_info_creation(self):
        """Test creating SandboxInfo."""
        info = SandboxInfo(
            sandbox_id="sandbox-123",
            bucket="test-bucket",
            storage_provider="memory",
            session_provider="memory",
            session_ttl_hours=24,
            max_retries=3,
            grid_prefix_pattern="grid/sandbox-123/",
            created_at="2025-01-01T00:00:00Z",
            closed=False,
        )
        assert info.sandbox_id == "sandbox-123"
        assert info.bucket == "test-bucket"
        assert info.closed is False

    def test_sandbox_info_dict_methods(self):
        """Test dict-like methods."""
        info = SandboxInfo(
            sandbox_id="sandbox-123",
            bucket="test",
            storage_provider="memory",
            session_provider="memory",
            session_ttl_hours=24,
            max_retries=3,
            grid_prefix_pattern="grid/",
            created_at="2025-01-01",
        )

        assert info["sandbox_id"] == "sandbox-123"
        assert info.get("sandbox_id") == "sandbox-123"
        assert "sandbox_id" in info
        assert "sandbox_id" in info.keys()
        assert info.values() is not None
        assert info.items() is not None


class TestPresignedUploadResponse:
    """Test PresignedUploadResponse model."""

    def test_presigned_upload_response(self):
        """Test creating PresignedUploadResponse."""
        response = PresignedUploadResponse(
            upload_url="https://example.com/upload",
            artifact_id="artifact-123",
            expires_in=3600,
        )
        assert response.upload_url == "https://example.com/upload"
        assert response.artifact_id == "artifact-123"
        assert response.expires_in == 3600


class TestMultipartUploadInitResponse:
    """Test MultipartUploadInitResponse model."""

    def test_multipart_upload_init_response(self):
        """Test creating MultipartUploadInitResponse."""
        response = MultipartUploadInitResponse(
            upload_id="upload-123",
            artifact_id="artifact-123",
            key="grid/path/to/artifact",
            session_id="sess-123",
            expires_in=86400,
        )
        assert response.upload_id == "upload-123"
        assert response.artifact_id == "artifact-123"
        assert response.key == "grid/path/to/artifact"
        assert response.session_id == "sess-123"
        assert response.expires_in == 86400

    def test_multipart_upload_init_response_dict_access(self):
        """Test dict-style access."""
        response = MultipartUploadInitResponse(
            upload_id="upload-123",
            artifact_id="artifact-123",
            key="grid/path",
            session_id="sess-123",
            expires_in=86400,
        )

        assert response["upload_id"] == "upload-123"
        assert response.get("upload_id") == "upload-123"
        assert response.get("nonexistent", "default") == "default"


class TestUpdateMetadataResponse:
    """Test UpdateMetadataResponse model."""

    def test_update_metadata_response(self):
        """Test creating UpdateMetadataResponse."""
        response = UpdateMetadataResponse(
            artifact_id="artifact-123",
            updated_at="2025-01-01T00:00:00Z",
            summary="Updated summary",
            meta={"key": "value"},
        )
        assert response.artifact_id == "artifact-123"
        assert response.updated_at == "2025-01-01T00:00:00Z"
        assert response.summary == "Updated summary"
        assert response.meta == {"key": "value"}

    def test_update_metadata_response_dict_access(self):
        """Test dict-style access."""
        response = UpdateMetadataResponse(
            artifact_id="artifact-123", updated_at="2025-01-01T00:00:00Z"
        )

        assert response["artifact_id"] == "artifact-123"
        assert response.get("artifact_id") == "artifact-123"


class TestBatchStoreResponse:
    """Test BatchStoreResponse model."""

    def test_batch_store_response(self):
        """Test creating BatchStoreResponse."""
        response = BatchStoreResponse(
            artifact_ids=["id1", "id2", None], total=3, successful=2, failed=1
        )
        assert response.artifact_ids == ["id1", "id2", None]
        assert response.total == 3
        assert response.successful == 2
        assert response.failed == 1

    def test_batch_store_response_empty(self):
        """Test empty batch response."""
        response = BatchStoreResponse(artifact_ids=[], total=0, successful=0, failed=0)
        assert response.artifact_ids == []
        assert response.total == 0


class TestBackwardCompatibility:
    """Test backward compatibility features across all models."""

    def test_all_response_models_support_extra_fields(self):
        """Test that all models support extra fields."""
        # Test a few key models with extra fields
        stats = StatsResponse(
            storage_provider="memory",
            session_provider="memory",
            bucket="test",
            sandbox_id="test",
            custom_field="custom_value",
        )
        # Extra fields should be stored
        assert stats.model_config["extra"] == "allow"

    def test_enum_string_conversion(self):
        """Test converting enums to/from strings."""
        # All enums should work as strings
        scope = StorageScope.SESSION
        assert scope.value == "session"
        assert scope == "session"  # String enum comparison

        # Can create from string
        scope2 = StorageScope("session")
        assert scope2 == scope

        # Enum is string
        assert isinstance(scope, str)


class TestDictStyleAccessEdgeCases:
    """Test edge cases for dict-style access on Pydantic models."""

    def test_getitem_with_extra_fields(self):
        """Test __getitem__ access to extra fields."""
        stats = StorageStats(provider="test", extra_field="extra_value")

        # Regular field access
        assert stats["provider"] == "test"

        # Extra field access via __getitem__
        assert stats["extra_field"] == "extra_value"

    def test_getitem_missing_key_raises_keyerror(self):
        """Test that accessing missing key raises KeyError."""
        stats = StorageStats(provider="test")

        # Accessing non-existent key should raise KeyError
        import pytest

        with pytest.raises(KeyError):
            _ = stats["nonexistent"]

    def test_get_with_default(self):
        """Test .get() method with default value."""
        stats = StorageStats(provider="test")

        # Existing key
        assert stats.get("provider") == "test"

        # Non-existing key with default
        assert stats.get("nonexistent", "default") == "default"

        # Non-existing key without default returns None
        assert stats.get("nonexistent") is None


class TestModelEquality:
    """Test custom __eq__ implementation for backward compatibility."""

    def test_pydantic_model_equality_with_dict(self):
        """Test comparing Pydantic model to dict (backward compatibility)."""
        from chuk_artifacts.types import SessionStats

        session_stats = SessionStats(total_sessions=10, active_sessions=5)

        # Should be equal to dict with same values
        assert session_stats == {"total_sessions": 10, "active_sessions": 5}

        # Should not be equal to dict with different values
        assert session_stats != {"total_sessions": 20, "active_sessions": 5}

    def test_pydantic_model_equality_with_extra_dict_fields(self):
        """Test that extra dict fields are ignored in comparison."""
        from chuk_artifacts.types import SessionStats

        session_stats = SessionStats(total_sessions=10, active_sessions=5)

        # Dict with extra fields should not match
        assert session_stats != {
            "total_sessions": 10,
            "active_sessions": 5,
            "extra_field": "value",
        }

    def test_pydantic_model_equality_with_model(self):
        """Test comparing Pydantic model to another model."""
        from chuk_artifacts.types import SessionStats

        session_stats1 = SessionStats(total_sessions=10, active_sessions=5)
        session_stats2 = SessionStats(total_sessions=10, active_sessions=5)
        session_stats3 = SessionStats(total_sessions=20, active_sessions=5)

        # Same values should be equal
        assert session_stats1 == session_stats2

        # Different values should not be equal
        assert session_stats1 != session_stats3
