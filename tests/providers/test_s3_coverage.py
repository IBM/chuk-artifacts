"""
Additional tests for S3 provider to increase coverage to 90%+.
"""

import pytest
import os
from unittest.mock import patch, AsyncMock, MagicMock
from chuk_artifacts.providers.s3 import factory, client


class TestS3FactoryCredentials:
    """Test S3 factory credential handling."""

    def test_factory_missing_credentials(self):
        """Test factory raises error when credentials are missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(RuntimeError, match="AWS credentials missing"):
                factory()

    def test_factory_with_access_key_only(self):
        """Test factory raises error when only access key is provided."""
        with patch.dict(os.environ, {"AWS_ACCESS_KEY_ID": "test"}, clear=True):
            with pytest.raises(RuntimeError, match="AWS credentials missing"):
                factory()

    def test_factory_with_secret_key_only(self):
        """Test factory raises error when only secret key is provided."""
        with patch.dict(os.environ, {"AWS_SECRET_ACCESS_KEY": "test"}, clear=True):
            with pytest.raises(RuntimeError, match="AWS credentials missing"):
                factory()

    @pytest.mark.asyncio
    async def test_factory_creates_client(self):
        """Test factory creates a working client context."""
        with patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "test_key",
                "AWS_SECRET_ACCESS_KEY": "test_secret",
                "AWS_REGION": "us-east-1",
            },
        ):
            factory_func = factory()

            # Mock aioboto3.Session to avoid actual AWS calls
            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_client = AsyncMock()
                mock_session.client.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_session.client.return_value.__aexit__ = AsyncMock(
                    return_value=None
                )
                mock_session_class.return_value = mock_session

                async with factory_func() as s3_client:
                    assert s3_client is mock_client

                # Verify session.client was called with correct parameters
                mock_session.client.assert_called_once()
                call_kwargs = mock_session.client.call_args.kwargs
                assert call_kwargs["aws_access_key_id"] == "test_key"
                assert call_kwargs["aws_secret_access_key"] == "test_secret"
                assert call_kwargs["region_name"] == "us-east-1"

    @pytest.mark.asyncio
    async def test_factory_with_endpoint_url(self):
        """Test factory with custom endpoint URL."""
        with patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "test_key",
                "AWS_SECRET_ACCESS_KEY": "test_secret",
                "S3_ENDPOINT_URL": "https://minio.example.com",
            },
        ):
            factory_func = factory()

            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_client = AsyncMock()
                mock_session.client.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_session.client.return_value.__aexit__ = AsyncMock(
                    return_value=None
                )
                mock_session_class.return_value = mock_session

                async with factory_func() as s3_client:
                    assert s3_client is mock_client

                call_kwargs = mock_session.client.call_args.kwargs
                assert call_kwargs["endpoint_url"] == "https://minio.example.com"

    @pytest.mark.asyncio
    async def test_factory_with_parameters(self):
        """Test factory with explicit parameters."""
        factory_func = factory(
            endpoint_url="https://custom.s3.com",
            region="eu-west-1",
            access_key="param_key",
            secret_key="param_secret",
        )

        with patch(
            "chuk_artifacts.providers.s3.aioboto3.Session"
        ) as mock_session_class:
            mock_session = MagicMock()
            mock_client = AsyncMock()
            mock_session.client.return_value.__aenter__ = AsyncMock(
                return_value=mock_client
            )
            mock_session.client.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_session_class.return_value = mock_session

            async with factory_func() as s3_client:
                assert s3_client is mock_client

            call_kwargs = mock_session.client.call_args.kwargs
            assert call_kwargs["endpoint_url"] == "https://custom.s3.com"
            assert call_kwargs["region_name"] == "eu-west-1"
            assert call_kwargs["aws_access_key_id"] == "param_key"
            assert call_kwargs["aws_secret_access_key"] == "param_secret"


class TestS3ClientFunction:
    """Test the client() convenience function."""

    def test_client_function_with_env_vars(self):
        """Test client() function reads from environment."""
        with patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "env_key",
                "AWS_SECRET_ACCESS_KEY": "env_secret",
                "AWS_REGION": "ap-southeast-1",
                "S3_ENDPOINT_URL": "https://env.s3.com",
            },
        ):
            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session

                client()

                mock_session.client.assert_called_once()
                call_kwargs = mock_session.client.call_args.kwargs
                assert call_kwargs["aws_access_key_id"] == "env_key"
                assert call_kwargs["aws_secret_access_key"] == "env_secret"
                assert call_kwargs["region_name"] == "ap-southeast-1"
                assert call_kwargs["endpoint_url"] == "https://env.s3.com"

    def test_client_function_with_parameters(self):
        """Test client() function with explicit parameters."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session

                client(
                    endpoint_url="https://param.s3.com",
                    region="eu-central-1",
                    access_key="param_key",
                    secret_key="param_secret",
                )

                call_kwargs = mock_session.client.call_args.kwargs
                assert call_kwargs["endpoint_url"] == "https://param.s3.com"
                assert call_kwargs["region_name"] == "eu-central-1"
                assert call_kwargs["aws_access_key_id"] == "param_key"
                assert call_kwargs["aws_secret_access_key"] == "param_secret"

    def test_client_function_defaults(self):
        """Test client() function with default values."""
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_session_class.return_value = mock_session

                client()

                call_kwargs = mock_session.client.call_args.kwargs
                assert call_kwargs["region_name"] == "us-east-1"  # Default region
                assert call_kwargs["endpoint_url"] is None
                assert call_kwargs["aws_access_key_id"] is None
                assert call_kwargs["aws_secret_access_key"] is None


class TestS3FactoryEnvironmentPriority:
    """Test that factory parameters override environment variables."""

    @pytest.mark.asyncio
    async def test_parameters_override_environment(self):
        """Test that explicit parameters override environment variables."""
        with patch.dict(
            os.environ,
            {
                "AWS_ACCESS_KEY_ID": "env_key",
                "AWS_SECRET_ACCESS_KEY": "env_secret",
                "AWS_REGION": "us-east-1",
                "S3_ENDPOINT_URL": "https://env.s3.com",
            },
        ):
            # Factory with explicit parameters
            factory_func = factory(
                endpoint_url="https://override.s3.com",
                region="eu-west-1",
                access_key="override_key",
                secret_key="override_secret",
            )

            with patch(
                "chuk_artifacts.providers.s3.aioboto3.Session"
            ) as mock_session_class:
                mock_session = MagicMock()
                mock_client = AsyncMock()
                mock_session.client.return_value.__aenter__ = AsyncMock(
                    return_value=mock_client
                )
                mock_session.client.return_value.__aexit__ = AsyncMock(
                    return_value=None
                )
                mock_session_class.return_value = mock_session

                async with factory_func():
                    pass

                call_kwargs = mock_session.client.call_args.kwargs
                # Parameters should override environment
                assert call_kwargs["aws_access_key_id"] == "override_key"
                assert call_kwargs["aws_secret_access_key"] == "override_secret"
                assert call_kwargs["region_name"] == "eu-west-1"
                assert call_kwargs["endpoint_url"] == "https://override.s3.com"


class TestSignatureVersion:
    """Presigned URLs must use SigV4 by default (required by e.g. ap-south-1)."""

    def _config_for(self, **kwargs):
        with patch.dict(os.environ, {}, clear=True):
            with patch("chuk_artifacts.providers.s3.aioboto3.Session") as mock_cls:
                mock_cls.return_value.client.return_value = MagicMock()
                client(access_key="k", secret_key="s", **kwargs)
                return mock_cls.return_value.client.call_args.kwargs["config"]

    def test_default_is_sigv4(self):
        assert self._config_for().signature_version == "s3v4"

    def test_explicit_override(self):
        assert self._config_for(signature_version="s3").signature_version == "s3"

    def test_env_override(self):
        with patch.dict(os.environ, {"S3_SIGNATURE_VERSION": "s3"}):
            with patch("chuk_artifacts.providers.s3.aioboto3.Session") as mock_cls:
                client(access_key="k", secret_key="s")
                cfg = mock_cls.return_value.client.call_args.kwargs["config"]
        assert cfg.signature_version == "s3"
