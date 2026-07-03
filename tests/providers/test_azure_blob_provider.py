# -*- coding: utf-8 -*-
"""
Unit tests for Azure Blob Storage provider with mocked Azure SDK.

These tests verify the provider implementation without requiring a real Azure account.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


@pytest.fixture
def mock_blob_properties():
    """Mock blob properties returned by Azure."""
    props = MagicMock()
    props.etag = "abc123"
    props.size = 100
    props.last_modified = datetime.now(timezone.utc)
    props.metadata = {"test": "value"}
    props.content_settings = MagicMock()
    props.content_settings.content_type = "text/plain"
    return props


@pytest.fixture
def mock_blob_client(mock_blob_properties):
    """Mock Azure BlobClient."""
    mock_client = AsyncMock()
    mock_client.upload_blob = AsyncMock()
    mock_client.download_blob = AsyncMock()
    mock_client.get_blob_properties = AsyncMock(return_value=mock_blob_properties)
    mock_client.delete_blob = AsyncMock()
    return mock_client


@pytest.fixture
def mock_container_client(mock_blob_client):
    """Mock Azure ContainerClient."""
    mock_client = AsyncMock()
    mock_client.create_container = AsyncMock()
    mock_client.get_blob_client = AsyncMock(return_value=mock_blob_client)
    mock_client.get_container_properties = AsyncMock()

    # Mock list_blobs to return async iterator
    mock_blob = MagicMock()
    mock_blob.name = "test/file.txt"
    mock_blob.size = 100
    mock_blob.last_modified = datetime.now(timezone.utc)
    mock_blob.etag = "abc123"

    async def async_iter():
        yield mock_blob

    mock_client.list_blobs = MagicMock(return_value=async_iter())

    return mock_client


@pytest.fixture
def mock_blob_service_client(mock_container_client):
    """Mock Azure BlobServiceClient."""
    mock_client = AsyncMock()
    mock_client.get_container_client = AsyncMock(return_value=mock_container_client)
    mock_client.close = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_factory_with_connection_string():
    """Test factory initialization with connection string."""
    connection_string = (
        "DefaultEndpointsProtocol=https;"
        "AccountName=testaccount;"
        "AccountKey=dGVzdGtleQ==;"
        "EndpointSuffix=core.windows.net"
    )

    with patch.dict("os.environ", {"AZURE_STORAGE_CONNECTION_STRING": connection_string}):
        with patch("azure.storage.blob.aio.BlobServiceClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client_class.from_connection_string.return_value = mock_client

            # Import after patching
            import sys
            if "chuk_artifacts.providers.azure_blob" in sys.modules:
                del sys.modules["chuk_artifacts.providers.azure_blob"]

            from chuk_artifacts.providers.azure_blob import factory

            # Create factory
            client_factory = factory()

            # Use context manager
            async with client_factory() as client:
                assert client is not None
                assert not client._closed


@pytest.mark.asyncio
async def test_factory_with_account_credentials():
    """Test factory initialization with account name and key."""
    with patch.dict("os.environ", {
        "AZURE_STORAGE_ACCOUNT_NAME": "testaccount",
        "AZURE_STORAGE_ACCOUNT_KEY": "dGVzdGtleQ=="
    }):
        with patch("azure.storage.blob.aio.BlobServiceClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            from chuk_artifacts.providers.azure_blob import factory

            # Create factory
            client_factory = factory()

            # Use context manager
            async with client_factory() as client:
                assert client is not None


@pytest.mark.asyncio
async def test_factory_missing_credentials():
    """Test factory fails with missing credentials."""
    with patch.dict("os.environ", {}, clear=True):
        from chuk_artifacts.providers.azure_blob import factory

        with pytest.raises(RuntimeError, match="Azure credentials missing"):
            factory()


@pytest.mark.asyncio
async def test_put_object(mock_blob_service_client, mock_blob_properties):
    """Test uploading an object."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    result = await adapter.put_object(
        Bucket="test-container",
        Key="test-file.txt",
        Body=b"test content",
        ContentType="text/plain",
        Metadata={"author": "test"}
    )

    # Verify result
    assert result["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert "ETag" in result

    # Verify Azure SDK was called correctly
    mock_blob_service_client.get_container_client.assert_called_with("test-container")


@pytest.mark.asyncio
async def test_get_object(mock_blob_service_client):
    """Test downloading an object."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    # Setup mock download
    mock_download_stream = AsyncMock()
    mock_download_stream.readall = AsyncMock(return_value=b"test content")

    container_client = mock_blob_service_client.get_container_client.return_value
    blob_client = container_client.get_blob_client.return_value
    blob_client.download_blob = AsyncMock(return_value=mock_download_stream)

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    result = await adapter.get_object(
        Bucket="test-container",
        Key="test-file.txt"
    )

    # Verify result
    assert result["Body"] == b"test content"
    assert result["ContentType"] == "text/plain"
    assert result["Metadata"] == {"test": "value"}
    assert result["ContentLength"] == 100


@pytest.mark.asyncio
async def test_get_object_not_found(mock_blob_service_client):
    """Test downloading non-existent object."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter
    from azure.core.exceptions import ResourceNotFoundError

    container_client = mock_blob_service_client.get_container_client.return_value
    blob_client = container_client.get_blob_client.return_value
    blob_client.download_blob = AsyncMock(side_effect=ResourceNotFoundError("Not found"))

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    with pytest.raises(Exception, match="NoSuchKey"):
        await adapter.get_object(
            Bucket="test-container",
            Key="nonexistent.txt"
        )


@pytest.mark.asyncio
async def test_delete_object(mock_blob_service_client):
    """Test deleting an object."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    result = await adapter.delete_object(
        Bucket="test-container",
        Key="test-file.txt"
    )

    # Verify result
    assert result["ResponseMetadata"]["HTTPStatusCode"] == 204

    # Verify Azure SDK was called
    container_client = mock_blob_service_client.get_container_client.return_value
    blob_client = container_client.get_blob_client.return_value
    blob_client.delete_blob.assert_called_once()


@pytest.mark.asyncio
async def test_list_objects_v2(mock_blob_service_client):
    """Test listing objects."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    result = await adapter.list_objects_v2(
        Bucket="test-container",
        Prefix="test/",
        MaxKeys=1000
    )

    # Verify result
    assert result["KeyCount"] == 1
    assert len(result["Contents"]) == 1
    assert result["Contents"][0]["Key"] == "test/file.txt"
    assert result["Contents"][0]["Size"] == 100
    assert "ETag" in result["Contents"][0]


@pytest.mark.asyncio
async def test_head_object(mock_blob_service_client):
    """Test getting object metadata."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    result = await adapter.head_object(
        Bucket="test-container",
        Key="test-file.txt"
    )

    # Verify result
    assert result["ContentType"] == "text/plain"
    assert result["ContentLength"] == 100
    assert result["Metadata"] == {"test": "value"}


@pytest.mark.asyncio
async def test_generate_presigned_url(mock_blob_service_client):
    """Test generating presigned URL."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    with patch("azure.storage.blob.generate_blob_sas") as mock_sas:
        mock_sas.return_value = "sig=abc123&st=2024-01-01&se=2024-01-02"

        adapter = AzureBlobAdapter(
            mock_blob_service_client,
            account_name="testaccount",
            account_key="testkey"
        )

        url = await adapter.generate_presigned_url(
            operation="get_object",
            Params={"Bucket": "test-container", "Key": "test-file.txt"},
            ExpiresIn=3600
        )

        # Verify URL structure
        assert "testaccount.blob.core.windows.net" in url
        assert "test-container" in url
        assert "test-file.txt" in url
        assert "sig=" in url


@pytest.mark.asyncio
async def test_generate_presigned_url_without_credentials(mock_blob_service_client):
    """Test generating presigned URL fails without credentials."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name=None,
        account_key=None
    )

    with pytest.raises(RuntimeError, match="Presigned URL generation requires"):
        await adapter.generate_presigned_url(
            operation="get_object",
            Params={"Bucket": "test-container", "Key": "test-file.txt"},
            ExpiresIn=3600
        )


@pytest.mark.asyncio
async def test_close(mock_blob_service_client):
    """Test closing the adapter."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    await adapter.close()

    assert adapter._closed is True
    mock_blob_service_client.close.assert_called_once()


@pytest.mark.asyncio
async def test_operations_fail_after_close(mock_blob_service_client):
    """Test operations fail after closing."""
    from chuk_artifacts.providers.azure_blob import AzureBlobAdapter

    adapter = AzureBlobAdapter(
        mock_blob_service_client,
        account_name="testaccount",
        account_key="testkey"
    )

    await adapter.close()

    with pytest.raises(RuntimeError, match="Client has been closed"):
        await adapter.put_object(
            Bucket="test",
            Key="test",
            Body=b"data",
            ContentType="text/plain",
            Metadata={}
        )
