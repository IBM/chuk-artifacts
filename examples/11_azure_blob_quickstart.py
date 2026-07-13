#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Azure Blob Storage Quickstart Example

Demonstrates using Azure Blob Storage as the artifact backend.
"""

import asyncio
import os


async def azure_blob_example():
    """Example using Azure Blob Storage provider."""
    from chuk_artifacts import ArtifactStore

    # Configure Azure Blob Storage
    # Credentials should be set in your environment before running this script:
    # Option 1: Connection String (recommended)
    #   export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=...;AccountKey=...;EndpointSuffix=core.windows.net"
    # Option 2: Account Name + Key
    #   export AZURE_STORAGE_ACCOUNT_NAME="your_account"
    #   export AZURE_STORAGE_ACCOUNT_KEY="your_key"

    os.environ["ARTIFACT_PROVIDER"] = "azure_blob"
    os.environ["ARTIFACT_BUCKET"] = "my-artifacts-container"
    os.environ["SESSION_PROVIDER"] = "memory"

    # Create store
    store = ArtifactStore(
        storage_provider="azure_blob",
        session_provider="memory",
        bucket="my-artifacts-container",
    )

    print("✓ Connected to Azure Blob Storage")

    # Store an artifact
    artifact_id = await store.store(
        data=b"Hello from Azure!",
        mime="text/plain",
        summary="Test artifact",
        session_id="demo-session",
    )
    print(f"✓ Stored artifact: {artifact_id}")

    # Retrieve it
    data = await store.retrieve(artifact_id)
    print(f"✓ Retrieved: {data.decode('utf-8')}")

    # List files
    files = await store.list_files(session_id="demo-session")
    print(f"✓ Found {len(files)} file(s) in session")

    # Delete
    await store.delete(artifact_id)
    print("✓ Deleted artifact")

    print("\n✅ Azure Blob Storage example complete!")


async def azure_with_programmatic_config():
    """Example using programmatic configuration."""
    from chuk_artifacts import ArtifactStore

    # Programmatic configuration (no environment variables needed)
    _ = ArtifactStore(
        storage_provider="azure_blob",
        session_provider="memory",
        bucket="my-container",
        # Azure credentials can be passed via environment or connection string
    )

    print("✓ Created store with programmatic config")


async def azure_with_azure_ad():
    """Example using Azure AD authentication."""
    from chuk_artifacts import ArtifactStore

    # Azure AD configuration (no account key needed!)
    os.environ["ARTIFACT_PROVIDER"] = "azure_blob"
    os.environ["AZURE_STORAGE_ACCOUNT_NAME"] = "your_account"
    os.environ["AZURE_USE_AD"] = "true"

    # Option 1: Service Principal (for applications)
    # os.environ["AZURE_CLIENT_ID"] = "your-client-id"
    # os.environ["AZURE_CLIENT_SECRET"] = "your-client-secret"
    # os.environ["AZURE_TENANT_ID"] = "your-tenant-id"

    # Option 2: Managed Identity (if running on Azure VM/AKS/Functions)
    # No credentials needed - identity is automatic!

    # Option 3: Azure CLI (for local development)
    # Just run: az login

    os.environ["ARTIFACT_BUCKET"] = "my-artifacts-container"
    os.environ["SESSION_PROVIDER"] = "memory"

    store = ArtifactStore(
        storage_provider="azure_blob",
        session_provider="memory",
        bucket="my-artifacts-container",
    )

    print("✓ Connected to Azure Blob Storage with Azure AD")

    # Store an artifact
    artifact_id = await store.store(
        data=b"Hello from Azure AD!",
        mime="text/plain",
        summary="Test artifact",
        session_id="demo-session",
    )
    print(f"✓ Stored artifact: {artifact_id}")

    # Generate presigned URL (User Delegation SAS)
    # Works WITHOUT "Allow Blob public access" enabled!
    presigned = await store.presign(artifact_id, expires=3600)
    print(f"✓ Presigned URL generated: {presigned[:80]}...")
    print("  (This works without 'Allow Blob public access' setting!)")

    # Cleanup
    await store.delete(artifact_id)
    print("✓ Deleted artifact")

    print("\n✅ Azure AD authentication example complete!")


async def main():
    """Run examples."""
    print("Azure Blob Storage Examples")
    print("=" * 50)

    # Check if Azure AD is configured
    azure_ad_configured = os.getenv("AZURE_USE_AD", "").lower() == "true"

    # Check if account key credentials are set
    account_key_configured = bool(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        or (
            os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
            and os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
        )
    )

    if not (azure_ad_configured or account_key_configured):
        print("\n⚠️  Azure credentials not configured")
        print("\nOption 1: Account Key Authentication")
        print("  Set AZURE_STORAGE_CONNECTION_STRING or")
        print("  AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY")
        print("\nOption 2: Azure AD Authentication")
        print("  Set AZURE_STORAGE_ACCOUNT_NAME")
        print("  Set AZURE_USE_AD=true")
        print("  Plus: AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID")
        print("  Or: az login (for Azure CLI authentication)")
        print("\nTo run this example:")
        print('  export AZURE_STORAGE_CONNECTION_STRING="..."')
        print("  python examples/11_azure_blob_quickstart.py")
        return

    try:
        if azure_ad_configured:
            print("\n🔐 Using Azure AD Authentication\n")
            await azure_with_azure_ad()
        else:
            print("\n🔑 Using Account Key Authentication\n")
            await azure_blob_example()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure:")
        print("1. Azure credentials are correct")
        print("2. Container exists or you have permission to create it")
        print("3. azure-storage-blob and azure-identity packages are installed")
        if azure_ad_configured:
            print("4. Azure AD identity has proper RBAC roles:")
            print("   - Storage Blob Data Contributor")
            print("   - Storage Blob Delegator (for presigned URLs)")


if __name__ == "__main__":
    asyncio.run(main())
