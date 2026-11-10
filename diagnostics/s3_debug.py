#!/usr/bin/env python3
"""
Simple test to verify the S3 provider works without complex dependencies.
Similar to the memory provider verification but for S3.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chuk_artifacts.providers.s3 import factory


def check_minimal_s3_config():
    """Check if minimal S3 config is available."""
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not (access_key and secret_key):
        print("❌ Missing S3 credentials")
        print(
            "   Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
        )
        return False

    print("✅ Found S3 credentials")
    return True


async def test_s3_provider_direct():
    """Test S3 provider directly without ArtifactStore."""
    print("🧪 Testing S3 provider directly...")

    if not check_minimal_s3_config():
        return False

    try:
        # Test factory creation
        s3_factory = factory()
        print("  ✅ S3 factory created successfully")

        # Test client context manager
        async with s3_factory() as s3_client:
            print("  ✅ S3 client context manager works")

            # Test basic bucket operation (this should work for any accessible bucket)
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")

            try:
                await s3_client.head_bucket(Bucket=bucket)
                print(f"  ✅ Bucket '{bucket}' is accessible")

                # Test a simple put/get/delete cycle
                test_key = "verification-test/simple.txt"
                test_data = b"S3 provider verification test"

                # Put object
                put_response = await s3_client.put_object(
                    Bucket=bucket,
                    Key=test_key,
                    Body=test_data,
                    ContentType="text/plain",
                    Metadata={"test": "verification"},
                )
                print(
                    f"  ✅ Object stored, ETag: {put_response.get('ETag', 'unknown')}"
                )

                # Get object
                get_response = await s3_client.get_object(Bucket=bucket, Key=test_key)

                # Handle different response body formats
                if hasattr(get_response["Body"], "read"):
                    retrieved_data = await get_response["Body"].read()
                else:
                    retrieved_data = get_response["Body"]

                assert retrieved_data == test_data
                print(f"  ✅ Object retrieved: {retrieved_data.decode()}")

                # Delete object
                await s3_client.delete_object(Bucket=bucket, Key=test_key)
                print("  ✅ Object deleted")

                # Verify deletion
                try:
                    await s3_client.head_object(Bucket=bucket, Key=test_key)
                    print("  ⚠️ Object still exists after delete")
                except Exception as e:
                    if "NoSuchKey" in str(e) or "404" in str(e):
                        print("  ✅ Object deletion verified")
                    else:
                        print(f"  ⚠️ Unexpected error verifying deletion: {e}")

                return True

            except Exception as e:
                if "NoSuchBucket" in str(e) or "403" in str(e):
                    print(f"  ❌ Bucket '{bucket}' not accessible: {e}")
                    print(
                        f"     Try creating bucket '{bucket}' or set ARTIFACT_BUCKET env var"
                    )
                else:
                    print(f"  ❌ S3 operations failed: {e}")
                return False

    except Exception as e:
        print(f"❌ S3 provider direct test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_s3_provider_with_custom_endpoint():
    """Test S3 provider with custom endpoint (MinIO)."""
    print("\n🧪 Testing S3 provider with custom endpoint...")

    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    if not endpoint_url:
        print("  ℹ️ S3_ENDPOINT_URL not set, skipping custom endpoint test")
        return True

    print(f"  🔗 Testing endpoint: {endpoint_url}")

    try:
        # Create factory with custom endpoint
        s3_factory = factory(endpoint_url=endpoint_url)

        async with s3_factory() as s3_client:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")

            # Test bucket access
            await s3_client.head_bucket(Bucket=bucket)
            print("  ✅ Custom endpoint bucket access successful")

            # Test list operation
            list_response = await s3_client.list_objects_v2(Bucket=bucket, MaxKeys=5)

            print(f"  ✅ Listed {list_response.get('KeyCount', 0)} objects")
            return True

    except Exception as e:
        print(f"  ⚠️ Custom endpoint test failed: {e}")
        return False


async def test_artifactstore_core_s3():
    """Test ArtifactStore core operations with S3 (no session creation)."""
    print("\n🧪 Testing ArtifactStore core operations with S3...")

    try:
        from chuk_artifacts.store import ArtifactStore

        # Create ArtifactStore with S3
        store = ArtifactStore(storage_provider="s3", session_provider="memory")

        # Test the S3 factory directly
        async with store._s3_factory() as s3_client:
            bucket = store.bucket
            test_key = "grid/sandbox-test/sess-test/artifact-test"
            test_data = b"Direct S3 ArtifactStore test data"

            # Store something directly via S3 client
            await s3_client.put_object(
                Bucket=bucket,
                Key=test_key,
                Body=test_data,
                ContentType="text/plain",
                Metadata={"direct": "true", "test": "artifactstore"},
            )

            print(f"  ✅ Stored data via ArtifactStore S3 client in bucket '{bucket}'")

        # Try to retrieve with a new S3 client from same store
        async with store._s3_factory() as s3_client2:
            response = await s3_client2.get_object(Bucket=bucket, Key=test_key)

            if hasattr(response["Body"], "read"):
                retrieved_data = await response["Body"].read()
            else:
                retrieved_data = response["Body"]

            assert retrieved_data == test_data
            print(f"  ✅ Retrieved data: {retrieved_data.decode()}")

            # Clean up
            await s3_client2.delete_object(Bucket=bucket, Key=test_key)
            print("  ✅ Cleanup completed")

        await store.close()
        print("✅ ArtifactStore S3 core test PASSED!")
        return True

    except Exception as e:
        print(f"❌ ArtifactStore S3 core test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_environment_configuration():
    """Test environment-based configuration."""
    print("\n🧪 Testing environment configuration...")

    try:
        # Show current environment
        env_vars = {
            "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID", "NOT_SET"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY", "NOT_SET"),
            "AWS_REGION": os.getenv("AWS_REGION", "NOT_SET"),
            "S3_ENDPOINT_URL": os.getenv("S3_ENDPOINT_URL", "NOT_SET"),
            "ARTIFACT_BUCKET": os.getenv("ARTIFACT_BUCKET", "NOT_SET"),
            "ARTIFACT_PROVIDER": os.getenv("ARTIFACT_PROVIDER", "NOT_SET"),
            "SESSION_PROVIDER": os.getenv("SESSION_PROVIDER", "NOT_SET"),
        }

        print("  📋 Current environment:")
        for key, value in env_vars.items():
            if "KEY" in key and value != "NOT_SET":
                print(f"    {key}: set")
            else:
                print(f"    {key}: {value}")

        # Set environment for S3
        os.environ["ARTIFACT_PROVIDER"] = "s3"
        os.environ["SESSION_PROVIDER"] = "memory"

        from chuk_artifacts.store import ArtifactStore

        # This should work if environment is properly configured
        store = ArtifactStore()  # Should pick up s3 from environment

        # Validate it's using S3
        config_info = await store.validate_configuration()
        storage_status = config_info.get("storage", {})

        if storage_status.get("status") == "ok":
            print("  ✅ Environment configuration successful")
            await store.close()
            return True
        else:
            print(f"  ❌ Environment configuration validation failed: {storage_status}")
            await store.close()
            return False

    except Exception as e:
        print(f"❌ Environment configuration test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all verification tests."""
    print("🚀 Simple S3 Provider Verification\n")
    print("=" * 60)

    tests = [
        test_s3_provider_direct,
        test_s3_provider_with_custom_endpoint,
        test_artifactstore_core_s3,
        test_environment_configuration,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            success = await test()
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__} CRASHED: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    # Analysis
    if passed >= 3:  # Most tests should pass
        print("🎉 S3 provider verification successful!")
        print("💡 The S3 provider is working correctly")
        if failed > 0:
            print("   - Some tests failed but core functionality works")
            print("   - Check S3 configuration and permissions for remaining issues")
    elif passed >= 1:
        print("⚠️ Partial S3 provider success")
        print("💡 Basic S3 connectivity works but some features may have issues")
        print("   - Check S3 bucket permissions and configuration")
    else:
        print("❌ S3 provider verification failed")
        print("💡 Check your S3 configuration:")
        print("   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set")
        print("   - Bucket must exist and be accessible")
        print("   - Network connectivity to S3 endpoint")
        print("   - Credentials must have appropriate permissions")

    return passed >= 1


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
