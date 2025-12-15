# -*- coding: utf-8 -*-
# tests/test_presigned.py
"""
Tests for chuk_artifacts.presigned module.

Tests presigned URL operations for download and upload.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from chuk_artifacts.presigned import (
    PresignedURLOperations,
    _DEFAULT_TTL,
    _DEFAULT_PRESIGN_EXPIRES,
)
from chuk_artifacts.exceptions import (
    ArtifactStoreError,
    ArtifactNotFoundError,
    ProviderError,
    SessionError,
)
from chuk_artifacts.models import ArtifactMetadata


@pytest.fixture
def mock_artifact_store():
    """Create a mock ArtifactStore for testing."""
    store = Mock()
    store.bucket = "test-bucket"
    store.sandbox_id = "test-sandbox"
    store._closed = False
    store._storage_provider_name = "memory"
    store._session_provider_name = "memory"

    # Mock session manager
    store._session_manager = AsyncMock()

    # Mock factories
    store._s3_factory = Mock()
    store._session_factory = Mock()

    # Mock grid operations
    store.generate_artifact_key = Mock()

    return store


@pytest.fixture
def presigned_operations(mock_artifact_store):
    """Create PresignedURLOperations instance for testing."""
    return PresignedURLOperations(mock_artifact_store)


class TestPresignedOperationsInitialization:
    """Test PresignedURLOperations initialization."""

    def test_initialization(self, mock_artifact_store):
        """Test that PresignedURLOperations initializes correctly."""
        presigned_ops = PresignedURLOperations(mock_artifact_store)
        assert presigned_ops.artifact_store is mock_artifact_store

    def test_initialization_with_none_store(self):
        """Test initialization with None store."""
        presigned_ops = PresignedURLOperations(None)
        assert presigned_ops.artifact_store is None


class TestPresign:
    """Test the presign method for download URLs."""

    @pytest.mark.asyncio
    async def test_presign_success(self, presigned_operations, mock_artifact_store):
        """Test successful presigned URL generation."""
        artifact_id = "test123"
        test_url = "https://example.com/presigned-url"

        # Mock record retrieval
        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key/path",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        # Mock S3 operations
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = test_url

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("chuk_artifacts.presigned.logger") as mock_logger:
            result = await presigned_operations.presign(artifact_id)

        assert result == test_url

        # Verify S3 call
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "test-bucket", "Key": "test/key/path"},
            ExpiresIn=_DEFAULT_PRESIGN_EXPIRES,
        )

        # Verify logging
        mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_presign_custom_expires(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presigned URL with custom expiration."""
        artifact_id = "test123"
        custom_expires = 7200

        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key/path",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/url"

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        await presigned_operations.presign(artifact_id, expires=custom_expires)

        # Verify custom expiration was used
        call_args = mock_s3.generate_presigned_url.call_args[1]
        assert call_args["ExpiresIn"] == custom_expires

    @pytest.mark.asyncio
    async def test_presign_closed_store(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presign when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await presigned_operations.presign("test123")

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_presign_artifact_not_found(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presign when artifact not found."""
        presigned_operations._get_record = AsyncMock(
            side_effect=ArtifactNotFoundError("Not found")
        )

        with pytest.raises(ArtifactNotFoundError):
            await presigned_operations.presign("nonexistent123")

    @pytest.mark.asyncio
    async def test_presign_oauth_credential_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presign with OAuth credential error."""
        test_record = ArtifactMetadata(
            artifact_id="test123",
            key="test/key/path",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception(
            "OAuth credentials not supported"
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(NotImplementedError) as exc_info:
            await presigned_operations.presign("test123")

        assert "OAuth" in str(exc_info.value)
        assert "HMAC creds" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_presign_general_provider_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presign with general provider error."""
        test_record = ArtifactMetadata(
            artifact_id="test123",
            key="test/key/path",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception("S3 service unavailable")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.presign("test123")

        assert "Presigned URL generation failed" in str(exc_info.value)


class TestPresignConvenienceMethods:
    """Test convenience methods for different TTLs."""

    @pytest.mark.asyncio
    async def test_presign_short(self, presigned_operations):
        """Test presign_short uses correct TTL."""
        with patch.object(presigned_operations, "presign") as mock_presign:
            mock_presign.return_value = "short-url"

            result = await presigned_operations.presign_short("test123")

            assert result == "short-url"
            mock_presign.assert_called_once_with("test123", expires=900)

    @pytest.mark.asyncio
    async def test_presign_medium(self, presigned_operations):
        """Test presign_medium uses correct TTL."""
        with patch.object(presigned_operations, "presign") as mock_presign:
            mock_presign.return_value = "medium-url"

            result = await presigned_operations.presign_medium("test123")

            assert result == "medium-url"
            mock_presign.assert_called_once_with("test123", expires=3600)

    @pytest.mark.asyncio
    async def test_presign_long(self, presigned_operations):
        """Test presign_long uses correct TTL."""
        with patch.object(presigned_operations, "presign") as mock_presign:
            mock_presign.return_value = "long-url"

            result = await presigned_operations.presign_long("test123")

            assert result == "long-url"
            mock_presign.assert_called_once_with("test123", expires=86400)


class TestPresignUpload:
    """Test the presign_upload method."""

    @pytest.mark.asyncio
    async def test_presign_upload_success(
        self, presigned_operations, mock_artifact_store
    ):
        """Test successful upload URL generation."""
        session_id = "test-session"
        test_url = "https://example.com/upload-url"

        # Mock session allocation
        mock_artifact_store._session_manager.allocate_session.return_value = session_id

        # Mock key generation
        test_key = "grid/test-sandbox/test-session/abc123"
        mock_artifact_store.generate_artifact_key.return_value = test_key

        # Mock S3 operations
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = test_url

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abc123def456"

            result_url, result_id = await presigned_operations.presign_upload()

        assert result_url == test_url
        assert result_id == "abc123def456"

        # Verify session allocation
        mock_artifact_store._session_manager.allocate_session.assert_called_once()

        # Verify S3 call
        mock_s3.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": "test-bucket",
                "Key": test_key,
                "ContentType": "application/octet-stream",
            },
            ExpiresIn=_DEFAULT_PRESIGN_EXPIRES,
        )

    @pytest.mark.asyncio
    async def test_presign_upload_with_existing_session(
        self, presigned_operations, mock_artifact_store
    ):
        """Test upload URL with existing session."""
        existing_session = "existing-session-123"

        mock_artifact_store._session_manager.allocate_session.return_value = (
            existing_session
        )
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "upload-url"

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        url, artifact_id = await presigned_operations.presign_upload(
            session_id=existing_session
        )

        # Verify session allocation with existing session
        mock_artifact_store._session_manager.allocate_session.assert_called_once_with(
            session_id=existing_session
        )

    @pytest.mark.asyncio
    async def test_presign_upload_custom_parameters(
        self, presigned_operations, mock_artifact_store
    ):
        """Test upload URL with custom parameters."""
        custom_mime = "image/jpeg"
        custom_expires = 7200

        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "upload-url"

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        await presigned_operations.presign_upload(
            filename="test.jpg", mime_type=custom_mime, expires=custom_expires
        )

        # Verify custom parameters
        call_args = mock_s3.generate_presigned_url.call_args[1]
        assert call_args["Params"]["ContentType"] == custom_mime
        assert call_args["ExpiresIn"] == custom_expires

    @pytest.mark.asyncio
    async def test_presign_upload_closed_store(
        self, presigned_operations, mock_artifact_store
    ):
        """Test upload URL when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await presigned_operations.presign_upload()

        assert "Store is closed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_presign_upload_provider_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test upload URL with provider error."""
        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception("Upload failed")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.presign_upload()

        assert "Upload presigned URL generation failed" in str(exc_info.value)


class TestRegisterUploadedArtifact:
    """Test the register_uploaded_artifact method."""

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_success(
        self, presigned_operations, mock_artifact_store
    ):
        """Test successful artifact registration."""
        artifact_id = "test123"
        session_id = "test-session"
        file_size = 1024

        # Mock session allocation
        mock_artifact_store._session_manager.allocate_session.return_value = session_id

        # Mock key generation
        test_key = "grid/test-sandbox/test-session/test123"
        mock_artifact_store.generate_artifact_key.return_value = test_key

        # Mock storage head_object
        mock_s3 = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": file_size}

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

        result = await presigned_operations.register_uploaded_artifact(
            artifact_id,
            mime="text/plain",
            summary="Test file",
            filename="test.txt",
            meta={"type": "test"},
        )

        assert result is True

        # Verify head_object call
        mock_s3.head_object.assert_called_once_with(Bucket="test-bucket", Key=test_key)

        # Verify metadata storage
        mock_session.setex.assert_called_once()
        setex_args = mock_session.setex.call_args[0]
        assert setex_args[0] == artifact_id
        assert setex_args[1] == _DEFAULT_TTL

        # Verify metadata content
        metadata = json.loads(setex_args[2])
        assert metadata["artifact_id"] == artifact_id
        assert metadata["session_id"] == session_id
        assert metadata["key"] == test_key
        assert metadata["mime"] == "text/plain"
        assert metadata["summary"] == "Test file"
        assert metadata["filename"] == "test.txt"
        assert metadata["meta"] == {"type": "test"}
        assert metadata["bytes"] == file_size
        assert metadata["sha256"] is None
        assert metadata["uploaded_via_presigned"] is True
        assert "stored_at" in metadata

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_not_found(
        self, presigned_operations, mock_artifact_store
    ):
        """Test registration when artifact not found in storage."""
        artifact_id = "test123"

        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock storage head_object failure
        mock_s3 = AsyncMock()
        mock_s3.head_object.side_effect = Exception("Not found")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await presigned_operations.register_uploaded_artifact(
            artifact_id, mime="text/plain", summary="Test file"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_session_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test registration with session error."""
        artifact_id = "test123"

        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock successful storage
        mock_s3 = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": 1024}

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session failure
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Redis connection failed")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(SessionError) as exc_info:
            await presigned_operations.register_uploaded_artifact(
                artifact_id, mime="text/plain", summary="Test file"
            )

        assert "Metadata registration failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_closed_store(
        self, presigned_operations, mock_artifact_store
    ):
        """Test registration when store is closed."""
        mock_artifact_store._closed = True

        with pytest.raises(ArtifactStoreError) as exc_info:
            await presigned_operations.register_uploaded_artifact(
                "test123", mime="text/plain", summary="Test file"
            )

        assert "Store is closed" in str(exc_info.value)


class TestPresignUploadAndRegister:
    """Test the presign_upload_and_register convenience method."""

    @pytest.mark.asyncio
    async def test_presign_upload_and_register_success(self, presigned_operations):
        """Test successful upload URL generation and registration."""
        test_url = "https://example.com/upload"
        test_artifact_id = "abc123"

        # Mock the constituent methods
        with patch.object(
            presigned_operations, "presign_upload"
        ) as mock_presign_upload:
            with patch.object(
                presigned_operations, "register_uploaded_artifact"
            ) as mock_register:
                mock_presign_upload.return_value = (test_url, test_artifact_id)
                mock_register.return_value = True

                (
                    result_url,
                    result_id,
                ) = await presigned_operations.presign_upload_and_register(
                    mime="image/jpeg",
                    summary="Test image",
                    filename="test.jpg",
                    meta={"category": "photo"},
                )

        assert result_url == test_url
        assert result_id == test_artifact_id

        # Verify presign_upload call
        mock_presign_upload.assert_called_once_with(
            session_id=None,
            filename="test.jpg",
            mime_type="image/jpeg",
            expires=_DEFAULT_PRESIGN_EXPIRES,
        )

        # Verify register_uploaded_artifact call
        mock_register.assert_called_once_with(
            test_artifact_id,
            mime="image/jpeg",
            summary="Test image",
            meta={"category": "photo"},
            filename="test.jpg",
            session_id=None,
            ttl=_DEFAULT_TTL,
        )

    @pytest.mark.asyncio
    async def test_presign_upload_and_register_custom_params(
        self, presigned_operations
    ):
        """Test upload and register with custom parameters."""
        test_url = "https://example.com/upload"
        test_artifact_id = "abc123"
        custom_session = "custom-session"
        custom_ttl = 3600
        custom_expires = 7200

        with patch.object(
            presigned_operations, "presign_upload"
        ) as mock_presign_upload:
            with patch.object(
                presigned_operations, "register_uploaded_artifact"
            ) as mock_register:
                mock_presign_upload.return_value = (test_url, test_artifact_id)
                mock_register.return_value = True

                await presigned_operations.presign_upload_and_register(
                    mime="application/pdf",
                    summary="Document",
                    session_id=custom_session,
                    ttl=custom_ttl,
                    expires=custom_expires,
                )

        # Verify custom parameters were passed
        mock_presign_upload.assert_called_once_with(
            session_id=custom_session,
            filename=None,
            mime_type="application/pdf",
            expires=custom_expires,
        )

        mock_register.assert_called_once_with(
            test_artifact_id,
            mime="application/pdf",
            summary="Document",
            meta=None,
            filename=None,
            session_id=custom_session,
            ttl=custom_ttl,
        )


class TestGetRecord:
    """Test the _get_record method."""

    @pytest.mark.asyncio
    async def test_get_record_success(self, presigned_operations, mock_artifact_store):
        """Test successful record retrieval."""
        artifact_id = "test123"
        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        # Mock session operations
        mock_session = AsyncMock()
        mock_session.get.return_value = test_record.model_dump_json()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await presigned_operations._get_record(artifact_id)

        assert result == test_record
        mock_session.get.assert_called_once_with(artifact_id)

    @pytest.mark.asyncio
    async def test_get_record_not_found(
        self, presigned_operations, mock_artifact_store
    ):
        """Test record retrieval when not found."""
        artifact_id = "nonexistent"

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ArtifactNotFoundError) as exc_info:
            await presigned_operations._get_record(artifact_id)

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_record_corrupted_data(
        self, presigned_operations, mock_artifact_store
    ):
        """Test record retrieval with corrupted JSON."""
        artifact_id = "test123"

        mock_session = AsyncMock()
        mock_session.get.return_value = "invalid json {"

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations._get_record(artifact_id)

        assert "Corrupted metadata" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_record_session_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test record retrieval with session error."""
        artifact_id = "test123"

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session failed")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(SessionError) as exc_info:
            await presigned_operations._get_record(artifact_id)

        assert "Session error" in str(exc_info.value)


class TestPresignedOperationsIntegration:
    """Integration tests for presigned operations."""

    @pytest.mark.asyncio
    async def test_complete_upload_workflow(
        self, presigned_operations, mock_artifact_store
    ):
        """Test complete upload workflow: generate URL, register artifact."""
        session_id = "integration-session"
        artifact_id = "integration-artifact"

        # Setup mocks for complete workflow
        mock_artifact_store._session_manager.allocate_session.return_value = session_id
        mock_artifact_store.generate_artifact_key.return_value = (
            f"grid/test-sandbox/{session_id}/{artifact_id}"
        )

        # Mock S3 for upload URL
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "https://upload.example.com"
        mock_s3.head_object.return_value = {"ContentLength": 2048}

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session for metadata
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = artifact_id

            # Generate upload URL
            upload_url, returned_id = await presigned_operations.presign_upload(
                session_id=session_id, mime_type="text/plain"
            )

            # Register the artifact
            registration_result = await presigned_operations.register_uploaded_artifact(
                returned_id, mime="text/plain", summary="Integration test file"
            )

        # Verify workflow
        assert upload_url == "https://upload.example.com"
        assert returned_id == artifact_id
        assert registration_result is True

        # Verify calls were made
        assert mock_s3.generate_presigned_url.call_count == 1
        assert mock_s3.head_object.call_count == 1
        assert mock_session.setex.call_count == 1

    @pytest.mark.asyncio
    async def test_download_url_workflow(
        self, presigned_operations, mock_artifact_store
    ):
        """Test download URL generation workflow."""
        artifact_id = "download-test"

        # Mock existing artifact record
        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key=f"grid/test-sandbox/session/{artifact_id}",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="image/jpeg",
            summary="Download test",
            meta={},
            bytes=1024,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )

        mock_session = AsyncMock()
        mock_session.get.return_value = test_record.model_dump_json()

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 for download URL
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "https://download.example.com"

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Test different TTL methods
        short_url = await presigned_operations.presign_short(artifact_id)
        medium_url = await presigned_operations.presign_medium(artifact_id)
        long_url = await presigned_operations.presign_long(artifact_id)

        # All should return the same URL (in this test setup)
        assert short_url == "https://download.example.com"
        assert medium_url == "https://download.example.com"
        assert long_url == "https://download.example.com"

        # Verify different expiration times were used
        generate_calls = mock_s3.generate_presigned_url.call_args_list
        assert len(generate_calls) == 3

        # Check expiration times
        short_expires = generate_calls[0][1]["ExpiresIn"]
        medium_expires = generate_calls[1][1]["ExpiresIn"]
        long_expires = generate_calls[2][1]["ExpiresIn"]

        assert short_expires == 900  # 15 minutes
        assert medium_expires == 3600  # 1 hour
        assert long_expires == 86400  # 24 hours


class TestLogging:
    """Test logging behavior in presigned operations."""

    @pytest.mark.asyncio
    async def test_presign_logging(self, presigned_operations, mock_artifact_store):
        """Test that presign operations log appropriately."""
        artifact_id = "log-test"

        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "test-url"

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("chuk_artifacts.presigned.logger") as mock_logger:
            await presigned_operations.presign(artifact_id)

            # Should log success
            mock_logger.info.assert_called_once()
            log_call = mock_logger.info.call_args
            assert "Presigned URL generated" in str(log_call)

    @pytest.mark.asyncio
    async def test_presign_error_logging(
        self, presigned_operations, mock_artifact_store
    ):
        """Test that presign errors are logged."""
        artifact_id = "error-test"

        test_record = ArtifactMetadata(
            artifact_id=artifact_id,
            key="test/key",
            session_id="session123",
            sandbox_id="test-sandbox",
            mime="text/plain",
            summary="Test",
            meta={},
            bytes=100,
            sha256="abc123",
            stored_at="2025-01-01T00:00:00Z",
            ttl=900,
            storage_provider="memory",
            session_provider="memory",
        )
        presigned_operations._get_record = AsyncMock(return_value=test_record)

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception("Test error")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with patch("chuk_artifacts.presigned.logger") as mock_logger:
            with pytest.raises(ProviderError):
                await presigned_operations.presign(artifact_id)

            # Should log error
            mock_logger.error.assert_called_once()
            log_call = mock_logger.error.call_args
            assert "Presigned URL generation failed" in str(log_call)


class TestPresignUploadOAuthError:
    """Test OAuth error handling in presign_upload."""

    @pytest.mark.asyncio
    async def test_presign_upload_oauth_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test upload URL with OAuth credential error."""
        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception(
            "OAuth credentials not supported"
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(NotImplementedError) as exc_info:
            await presigned_operations.presign_upload()

        assert "OAuth" in str(exc_info.value)
        assert "HMAC creds" in str(exc_info.value)


class TestRegisterUploadedArtifactProviderError:
    """Test provider error handling in register_uploaded_artifact."""

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_provider_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test registration with general provider error."""
        artifact_id = "test123"

        mock_artifact_store._session_manager.allocate_session.return_value = "session"
        mock_artifact_store.generate_artifact_key.return_value = "test/key"

        # Mock successful storage
        mock_s3 = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": 1024}

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session failure with generic error
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Storage failure")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.register_uploaded_artifact(
                artifact_id, mime="text/plain", summary="Test file"
            )

        assert "Metadata registration failed" in str(exc_info.value)


class TestMultipartUploadInitiate:
    """Test multipart upload initiation."""

    @pytest.mark.asyncio
    async def test_initiate_multipart_upload_user_scope(
        self, presigned_operations, mock_artifact_store
    ):
        """Test multipart upload initiation with user scope."""
        from chuk_artifacts.models import MultipartUploadInitRequest

        request = MultipartUploadInitRequest(
            filename="video.mp4",
            mime_type="video/mp4",
            user_id="alice",
            scope="user",
        )

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "session123"
        )

        # Mock S3 with multipart support
        mock_s3 = AsyncMock()
        mock_s3.create_multipart_upload = AsyncMock(
            return_value={"UploadId": "upload-123"}
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session storage
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "artifact123"

            result = await presigned_operations.initiate_multipart_upload(request)

        assert result["upload_id"] == "upload-123"
        assert result["artifact_id"] == "artifact123"
        assert "users/alice" in result["key"]
        mock_s3.create_multipart_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_multipart_upload_sandbox_scope(
        self, presigned_operations, mock_artifact_store
    ):
        """Test multipart upload with sandbox scope."""
        from chuk_artifacts.models import MultipartUploadInitRequest

        request = MultipartUploadInitRequest(
            filename="shared.pdf",
            mime_type="application/pdf",
            scope="sandbox",
        )

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "session123"
        )

        mock_s3 = AsyncMock()
        mock_s3.create_multipart_upload = AsyncMock(
            return_value={"UploadId": "upload-456"}
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "artifact456"

            result = await presigned_operations.initiate_multipart_upload(request)

        assert "shared" in result["key"]

    @pytest.mark.asyncio
    async def test_initiate_multipart_upload_without_native_support(
        self, presigned_operations, mock_artifact_store
    ):
        """Test multipart upload without native multipart support."""
        from chuk_artifacts.models import MultipartUploadInitRequest

        request = MultipartUploadInitRequest(
            filename="file.bin",
            mime_type="application/octet-stream",
        )

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "session123"
        )

        # Mock S3 WITHOUT create_multipart_upload
        mock_s3 = AsyncMock()
        # Don't set create_multipart_upload attribute

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await presigned_operations.initiate_multipart_upload(request)

        # Should generate pseudo upload_id
        assert result["upload_id"].startswith("upload-")

    @pytest.mark.asyncio
    async def test_initiate_multipart_upload_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test error handling in multipart upload initiation."""
        from chuk_artifacts.models import MultipartUploadInitRequest

        request = MultipartUploadInitRequest(
            filename="file.bin",
            mime_type="application/octet-stream",
        )

        mock_artifact_store._session_manager.allocate_session.return_value = (
            "session123"
        )

        # Mock S3 failure
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.side_effect = Exception("S3 failure")
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.initiate_multipart_upload(request)

        assert "Multipart upload initiation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_initiate_multipart_upload_user_scope_validation(
        self, presigned_operations, mock_artifact_store
    ):
        """Test user scope requires user_id."""
        from chuk_artifacts.models import MultipartUploadInitRequest

        request = MultipartUploadInitRequest(
            filename="file.bin",
            mime_type="application/octet-stream",
            scope="user",
            # Missing user_id
        )

        with pytest.raises(ValueError) as exc_info:
            await presigned_operations.initiate_multipart_upload(request)

        assert "user_id is required" in str(exc_info.value)


class TestGetPartUploadUrl:
    """Test get_part_upload_url method."""

    @pytest.mark.asyncio
    async def test_get_part_upload_url_success(
        self, presigned_operations, mock_artifact_store
    ):
        """Test successful part upload URL generation."""
        upload_id = "upload-123"
        part_number = 1

        # Mock session with multipart metadata
        multipart_meta = {
            "upload_id": upload_id,
            "artifact_id": "artifact123",
            "key": "test/key/artifact123",
            "session_id": "session123",
            "filename": "video.mp4",
            "mime_type": "video/mp4",
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 with presigned URL support
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url = AsyncMock(
            return_value="https://example.com/part-url"
        )

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        url = await presigned_operations.get_part_upload_url(upload_id, part_number)

        assert url == "https://example.com/part-url"
        mock_s3.generate_presigned_url.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_part_upload_url_fallback(
        self, presigned_operations, mock_artifact_store
    ):
        """Test part upload URL fallback without native support."""
        upload_id = "upload-123"
        part_number = 2

        multipart_meta = {
            "upload_id": upload_id,
            "key": "test/key",
            "mime_type": "application/pdf",
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 WITHOUT generate_presigned_url - should raise ProviderError
        mock_s3 = AsyncMock()
        # Remove the attribute to trigger error
        delattr(mock_s3, "generate_presigned_url")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # This should raise ProviderError
        with pytest.raises(ProviderError):
            await presigned_operations.get_part_upload_url(upload_id, part_number)

    @pytest.mark.asyncio
    async def test_get_part_upload_url_invalid_part_number(
        self, presigned_operations, mock_artifact_store
    ):
        """Test invalid part number validation."""
        with pytest.raises(ValueError) as exc_info:
            await presigned_operations.get_part_upload_url("upload-123", 0)

        assert "Part number must be between 1 and 10,000" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            await presigned_operations.get_part_upload_url("upload-123", 10001)

        assert "Part number must be between 1 and 10,000" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_part_upload_url_not_found(
        self, presigned_operations, mock_artifact_store
    ):
        """Test part URL generation when upload not found."""
        mock_session = AsyncMock()
        mock_session.get.return_value = None

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ArtifactNotFoundError) as exc_info:
            await presigned_operations.get_part_upload_url("nonexistent", 1)

        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_part_upload_url_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test error handling in part URL generation."""
        multipart_meta = {"key": "test/key"}

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 failure
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.side_effect = Exception("S3 error")
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.get_part_upload_url("upload-123", 1)

        assert "Part upload URL generation failed" in str(exc_info.value)


class TestCompleteMultipartUpload:
    """Test complete_multipart_upload method."""

    @pytest.mark.asyncio
    async def test_complete_multipart_upload_success(
        self, presigned_operations, mock_artifact_store
    ):
        """Test successful multipart upload completion."""
        from chuk_artifacts.models import (
            MultipartUploadCompleteRequest,
            MultipartUploadPart,
        )

        request = MultipartUploadCompleteRequest(
            upload_id="upload-123",
            parts=[
                MultipartUploadPart(PartNumber=1, ETag="etag1"),
                MultipartUploadPart(PartNumber=2, ETag="etag2"),
            ],
            summary="Large file upload",
        )

        multipart_meta = {
            "upload_id": "upload-123",
            "artifact_id": "artifact123",
            "key": "test/key/artifact123",
            "session_id": "session123",
            "filename": "video.mp4",
            "mime_type": "video/mp4",
            "ttl": 900,
            "meta": {},
        }

        # Mock session operations
        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 with native multipart support
        mock_s3 = AsyncMock()
        mock_s3.complete_multipart_upload = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": 10240}

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        artifact_id = await presigned_operations.complete_multipart_upload(request)

        assert artifact_id == "artifact123"
        mock_s3.complete_multipart_upload.assert_called_once()
        mock_session.delete.assert_called_once_with("multipart:upload-123")

    @pytest.mark.asyncio
    async def test_complete_multipart_upload_fallback(
        self, presigned_operations, mock_artifact_store
    ):
        """Test multipart completion fallback without native support."""
        from chuk_artifacts.models import (
            MultipartUploadCompleteRequest,
            MultipartUploadPart,
        )

        request = MultipartUploadCompleteRequest(
            upload_id="upload-123",
            parts=[
                MultipartUploadPart(PartNumber=1, ETag="etag1"),
            ],
            summary="File upload",
        )

        multipart_meta = {
            "upload_id": "upload-123",
            "artifact_id": "artifact123",
            "key": "test/key",
            "session_id": "session123",
            "mime_type": "text/plain",
            "ttl": 900,
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Mock S3 WITHOUT native multipart support
        mock_s3 = AsyncMock()
        # Ensure complete_multipart_upload doesn't exist
        if hasattr(mock_s3, "complete_multipart_upload"):
            delattr(mock_s3, "complete_multipart_upload")

        # create mock part data
        mock_part_body = AsyncMock()
        mock_part_body.read.return_value = b"part data"
        mock_s3.get_object.return_value = {"Body": mock_part_body}
        mock_s3.put_object = AsyncMock()
        mock_s3.delete_object = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": 100}

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        artifact_id = await presigned_operations.complete_multipart_upload(request)

        assert artifact_id == "artifact123"
        mock_s3.put_object.assert_called_once()
        mock_s3.delete_object.assert_called()

    @pytest.mark.asyncio
    async def test_complete_multipart_upload_not_found(
        self, presigned_operations, mock_artifact_store
    ):
        """Test completion when upload not found."""
        from chuk_artifacts.models import (
            MultipartUploadCompleteRequest,
            MultipartUploadPart,
        )

        request = MultipartUploadCompleteRequest(
            upload_id="nonexistent",
            parts=[MultipartUploadPart(PartNumber=1, ETag="etag1")],
            summary="Test",
        )

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ArtifactNotFoundError):
            await presigned_operations.complete_multipart_upload(request)

    @pytest.mark.asyncio
    async def test_complete_multipart_upload_head_object_failure(
        self, presigned_operations, mock_artifact_store
    ):
        """Test completion when head_object fails."""
        from chuk_artifacts.models import (
            MultipartUploadCompleteRequest,
            MultipartUploadPart,
        )

        request = MultipartUploadCompleteRequest(
            upload_id="upload-123",
            parts=[MultipartUploadPart(PartNumber=1, ETag="etag1")],
            summary="Test",
        )

        multipart_meta = {
            "upload_id": "upload-123",
            "artifact_id": "artifact123",
            "key": "test/key",
            "session_id": "session123",
            "ttl": 900,
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        mock_s3 = AsyncMock()
        mock_s3.complete_multipart_upload = AsyncMock()
        mock_s3.head_object.side_effect = Exception("Head failed")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Should still succeed but with file_size = 0
        artifact_id = await presigned_operations.complete_multipart_upload(request)
        assert artifact_id == "artifact123"

    @pytest.mark.asyncio
    async def test_complete_multipart_upload_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test error handling in multipart completion."""
        from chuk_artifacts.models import (
            MultipartUploadCompleteRequest,
            MultipartUploadPart,
        )

        request = MultipartUploadCompleteRequest(
            upload_id="upload-123",
            parts=[MultipartUploadPart(PartNumber=1, ETag="etag1")],
            summary="Test",
        )

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session error")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        with pytest.raises(ProviderError) as exc_info:
            await presigned_operations.complete_multipart_upload(request)

        assert "Multipart upload completion failed" in str(exc_info.value)


class TestAbortMultipartUpload:
    """Test abort_multipart_upload method."""

    @pytest.mark.asyncio
    async def test_abort_multipart_upload_success(
        self, presigned_operations, mock_artifact_store
    ):
        """Test successful multipart upload abort."""
        upload_id = "upload-123"

        multipart_meta = {
            "upload_id": upload_id,
            "key": "test/key",
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        mock_s3 = AsyncMock()
        mock_s3.abort_multipart_upload = AsyncMock()

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await presigned_operations.abort_multipart_upload(upload_id)

        assert result is True
        mock_s3.abort_multipart_upload.assert_called_once()
        mock_session.delete.assert_called_once_with(f"multipart:{upload_id}")

    @pytest.mark.asyncio
    async def test_abort_multipart_upload_already_cleaned(
        self, presigned_operations, mock_artifact_store
    ):
        """Test abort when upload already cleaned up."""
        upload_id = "upload-123"

        mock_session = AsyncMock()
        mock_session.get.return_value = None

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await presigned_operations.abort_multipart_upload(upload_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_abort_multipart_upload_s3_error_ignored(
        self, presigned_operations, mock_artifact_store
    ):
        """Test abort when S3 abort fails (should be ignored)."""
        upload_id = "upload-123"

        multipart_meta = {
            "upload_id": upload_id,
            "key": "test/key",
        }

        mock_session = AsyncMock()
        mock_session.get.return_value = str(multipart_meta)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        mock_s3 = AsyncMock()
        mock_s3.abort_multipart_upload.side_effect = Exception("Already aborted")

        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        result = await presigned_operations.abort_multipart_upload(upload_id)

        # Should still succeed
        assert result is True

    @pytest.mark.asyncio
    async def test_abort_multipart_upload_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test error handling in abort."""
        upload_id = "upload-123"

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.side_effect = Exception("Session error")
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        result = await presigned_operations.abort_multipart_upload(upload_id)

        # Should return False on error
        assert result is False


class TestDefaultConstants:
    """Test default constants."""

    def test_default_constants(self):
        """Test that default constants are defined correctly."""
        assert _DEFAULT_TTL == 900
        assert _DEFAULT_PRESIGN_EXPIRES == 3600
        assert isinstance(_DEFAULT_TTL, int)
        assert isinstance(_DEFAULT_PRESIGN_EXPIRES, int)


class TestPresignedErrorPaths:
    """Test error handling paths in presigned operations."""

    @pytest.mark.asyncio
    async def test_presign_upload_oauth_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test presign_upload with OAuth credential error."""
        # Setup session allocation
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )

        # Mock S3 to raise OAuth error
        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.side_effect = Exception(
            "OAuth credentials not supported"
        )
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Should raise NotImplementedError for OAuth
        with pytest.raises(NotImplementedError, match="OAuth"):
            await presigned_operations.presign_upload(
                filename="test.txt",
                mime_type="text/plain",
                session_id="test-session",
            )

    @pytest.mark.asyncio
    async def test_register_uploaded_artifact_metadata_error(
        self, presigned_operations, mock_artifact_store
    ):
        """Test register_uploaded_artifact with metadata storage error."""
        # Setup session allocation
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "test-session"
        )
        mock_artifact_store.generate_artifact_key.return_value = "grid/test/key"

        # Mock S3 head_object success
        mock_s3 = AsyncMock()
        mock_s3.head_object.return_value = {"ContentLength": 1000}
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Mock session to raise error on setex
        mock_session = AsyncMock()
        mock_session.setex.side_effect = Exception("Redis connection failed")
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session
        mock_session_ctx.__aexit__.return_value = None
        mock_artifact_store._session_factory.return_value = mock_session_ctx

        # Should raise SessionError
        from chuk_artifacts.exceptions import SessionError

        with pytest.raises(SessionError, match="Metadata registration failed"):
            await presigned_operations.register_uploaded_artifact(
                artifact_id="test-id",
                mime="text/plain",
                summary="Test",
                session_id="test-session",
            )


class TestPresignedSessionAllocation:
    """Test session allocation in presigned operations."""

    @pytest.mark.asyncio
    async def test_presign_upload_allocates_session_if_none(
        self, presigned_operations, mock_artifact_store
    ):
        """Test that presign_upload allocates session when session_id is None."""
        # Setup
        mock_artifact_store._session_manager.allocate_session.return_value = (
            "auto-allocated-session"
        )

        mock_s3 = AsyncMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/upload"
        mock_storage_ctx = AsyncMock()
        mock_storage_ctx.__aenter__.return_value = mock_s3
        mock_storage_ctx.__aexit__.return_value = None
        mock_artifact_store._s3_factory.return_value = mock_storage_ctx

        # Call without session_id
        upload_url, artifact_id = await presigned_operations.presign_upload(
            filename="test.txt", mime_type="text/plain"
        )

        # Verify session was allocated
        mock_artifact_store._session_manager.allocate_session.assert_called_once()
        assert upload_url == "https://example.com/upload"
        assert artifact_id is not None
