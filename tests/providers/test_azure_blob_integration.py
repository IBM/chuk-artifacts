# -*- coding: utf-8 -*-
"""
Integration tests for Azure Blob Storage with Azure AD authentication.

These tests require Azure AD credentials to be configured.
Set AZURE_USE_AD=true to run these tests.
"""

import os
import pytest


class TestAzureBlobAzureAD:
    """Integration tests for Azure AD authentication."""

    @pytest.mark.asyncio
    async def test_azure_ad_authentication(self, test_container_name):
        """Test Azure AD authentication (if configured)."""
        # Only run if Azure AD credentials are configured
        if not os.getenv("AZURE_USE_AD"):
            pytest.skip("Azure AD not configured (set AZURE_USE_AD=true to test)")

        from chuk_artifacts.providers.azure_blob import factory

        # Create factory with Azure AD
        client_factory = factory(use_azure_ad=True)

        # Test connection
        async with client_factory() as adapter:
            assert adapter is not None
            assert adapter._use_azure_ad is True
            assert not adapter._closed

            # Test basic operations
            test_key = "azure-ad-test/test-file.txt"
            test_data = b"Azure AD authentication test"

            # Upload
            put_result = await adapter.put_object(
                Bucket=test_container_name,
                Key=test_key,
                Body=test_data,
                ContentType="text/plain",
                Metadata={"auth": "azure_ad"},
            )

            assert put_result["ResponseMetadata"]["HTTPStatusCode"] == 200

            # Download
            get_result = await adapter.get_object(
                Bucket=test_container_name, Key=test_key
            )

            assert get_result["Body"] == test_data
            assert get_result["Metadata"]["auth"] == "azure_ad"

            # Presigned URL (User Delegation SAS)
            url = await adapter.generate_presigned_url(
                operation="get_object",
                Params={"Bucket": test_container_name, "Key": test_key},
                ExpiresIn=3600,
            )

            assert adapter._account_name in url
            assert test_container_name in url
            assert test_key in url
            assert "sig=" in url

            # Cleanup
            await adapter.delete_object(Bucket=test_container_name, Key=test_key)


@pytest.fixture
def test_container_name():
    """Provide a test container name."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"chuk-test-{timestamp}"
