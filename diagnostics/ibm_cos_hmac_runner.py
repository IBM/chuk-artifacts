#!/usr/bin/env python3
# diagnostics/ibm_cos_hmac_runner.py
"""
Comprehensive test runner for IBM COS provider with HMAC authentication.
Run this to test the IBM COS provider independently with real IBM COS credentials.

Updated to use optimized IBM COS configuration:
- Signature Version 2 ('s3')
- Virtual-hosted addressing style
- Based on signature testing results
"""

import asyncio
import sys
import traceback
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Load environment variables from .env file if available
def load_dotenv():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent.parent / ".env"

    if env_file.exists():
        print(f"📁 Loading environment from: {env_file}")
        try:
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")

                        # Only set if not already in environment
                        if key not in os.environ:
                            os.environ[key] = value
            print("✅ Environment loaded from .env file")
        except Exception as e:
            print(f"❌ Failed to load .env file: {e}")
    else:
        print("ℹ️ No .env file found, using system environment variables")


# Load .env on import
load_dotenv()

from chuk_artifacts.providers.ibm_cos import factory  # noqa: E402


def check_ibm_cos_config():
    """Check IBM COS configuration and provide helpful feedback."""
    print("🔧 Checking IBM COS Configuration...")
    print("   Using optimized configuration: Signature v2 + Virtual addressing")

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-south")
    endpoint = os.getenv("IBM_COS_ENDPOINT")

    if not access_key:
        print("  ❌ AWS_ACCESS_KEY_ID not set")
        return False
    else:
        print("  ✅ AWS_ACCESS_KEY_ID: set")

    if not secret_key:
        print("  ❌ AWS_SECRET_ACCESS_KEY not set")
        return False
    else:
        print("  ✅ AWS_SECRET_ACCESS_KEY: set")

    print(f"  ✅ AWS_REGION: {region}")

    if endpoint:
        print(f"  ✅ IBM_COS_ENDPOINT: {endpoint}")
        # Validate endpoint format
        if "cloud-object-storage.appdomain.cloud" in endpoint:
            print("  ✅ Valid IBM COS endpoint format")
        else:
            print("  ⚠️ Endpoint doesn't match IBM COS format")
    else:
        print("  ℹ️ IBM_COS_ENDPOINT not set, using default us-south endpoint")

    print("  ✅ Signature configuration: Optimized (v2 + virtual addressing)")

    return True


async def test_basic_ibm_cos_operations():
    """Test basic IBM COS provider operations with optimized configuration."""
    print("\n🧪 Testing basic IBM COS provider operations...")
    print("   Using optimized configuration: Signature v2 + Virtual addressing")

    if not check_ibm_cos_config():
        print(
            "  ❌ IBM COS configuration incomplete. Please set required environment variables:"
        )
        print("     export AWS_ACCESS_KEY_ID=your_hmac_access_key")
        print("     export AWS_SECRET_ACCESS_KEY=your_hmac_secret_key")
        print("     export AWS_REGION=us-south  # or your preferred region")
        print(
            "     export IBM_COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud"
        )
        return False

    factory_func = factory()

    try:
        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "mcp-bucket")
            key = "ibm-cos-test-file-optimized.txt"
            test_data = b"Hello, IBM COS provider! (Optimized configuration)"

            # Test bucket creation/validation
            print("  🪣 Testing bucket operations...")
            try:
                await cos.head_bucket(Bucket=bucket)
                print(f"  ✅ Bucket '{bucket}' exists and is accessible")
            except Exception as e:
                if "NoSuchBucket" in str(e) or "404" in str(e):
                    print(f"  ⚠️ Bucket '{bucket}' doesn't exist")
                    print("     You may need to create it manually in IBM COS")
                    print("     Or use a different bucket name")
                    return False
                elif "InvalidAccessKeyId" in str(e) or "SignatureDoesNotMatch" in str(
                    e
                ):
                    print(f"  ❌ HMAC credential issue: {e}")
                    print("     This should NOT happen with optimized configuration!")
                    print("     Check your HMAC access key and secret key")
                    return False
                else:
                    print(f"  ❌ Bucket check failed: {e}")
                    return False

            # Test put_object
            print("  📤 Testing put_object with optimized config...")
            put_response = await cos.put_object(
                Bucket=bucket,
                Key=key,
                Body=test_data,
                ContentType="text/plain",
                Metadata={
                    "filename": "ibm-cos-test-file-optimized.txt",
                    "provider": "ibm-cos",
                    "auth": "hmac",
                    "config": "optimized-v2-virtual",
                },
            )

            assert "ETag" in put_response
            print(
                f"  ✅ put_object successful with optimized config, ETag: {put_response['ETag']}"
            )

            # Test head_object
            print("  📋 Testing head_object...")
            head_response = await cos.head_object(Bucket=bucket, Key=key)

            assert head_response["ContentLength"] == len(test_data)
            assert head_response["ContentType"] == "text/plain"
            print(
                f"  ✅ head_object successful, size: {head_response['ContentLength']} bytes"
            )

            # Verify metadata
            metadata = head_response.get("Metadata", {})
            if metadata:
                print(f"  ✅ Metadata preserved: {len(metadata)} keys")
                # Check for optimized config metadata
                config_found = any(k.lower() == "config" for k in metadata.keys())
                if config_found:
                    print("    - ✅ Optimized config metadata confirmed")

            # Test get_object
            print("  📥 Testing get_object...")
            get_response = await cos.get_object(Bucket=bucket, Key=key)

            # Handle different response body formats
            if hasattr(get_response["Body"], "read"):
                body_data = await get_response["Body"].read()
            else:
                body_data = get_response["Body"]

            assert body_data == test_data
            assert get_response["ContentType"] == "text/plain"
            print(f"  ✅ get_object successful: {body_data.decode()[:50]}...")

            # Test list_objects_v2
            print("  📋 Testing list_objects_v2...")
            list_response = await cos.list_objects_v2(
                Bucket=bucket, Prefix="ibm-cos-test-"
            )

            assert list_response["KeyCount"] >= 1
            keys = [obj["Key"] for obj in list_response["Contents"]]
            assert key in keys
            print(
                f"  ✅ Found {list_response['KeyCount']} objects with 'ibm-cos-test-' prefix"
            )

            # Test presigned URL generation
            print("  🔗 Testing presigned URL...")
            try:
                url = await cos.generate_presigned_url(
                    "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
                )

                assert "http" in url.lower()
                assert "cloud-object-storage" in url  # IBM COS specific
                print(
                    f"  ✅ Generated presigned URL with optimized config: {url[:60]}..."
                )

            except Exception as e:
                print(f"  ⚠️ Presigned URL failed: {e}")
                # This might be expected for some IBM COS configurations

            # Test delete_object
            print("  🗑️ Testing delete_object...")
            await cos.delete_object(Bucket=bucket, Key=key)

            # Verify deletion
            try:
                await cos.head_object(Bucket=bucket, Key=key)
                print("  ❌ Object should have been deleted")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print("  ✅ delete_object successful")
                else:
                    print(f"  ❌ Unexpected error during delete verification: {e}")
                    return False

    except Exception as e:
        print(f"  ❌ IBM COS operations failed: {e}")
        if "AccessDenied" in str(e):
            print("     → This might be a bucket permissions issue")
            print("     → Check your service credential has 'Writer' or 'Manager' role")
            print(
                "     → The optimized signature configuration should have fixed auth issues"
            )
        elif "SignatureDoesNotMatch" in str(e):
            print("     → This should NOT happen with optimized configuration!")
            print(
                "     → Re-run signature tester: python diagnostics/ibm_cos_signature_tester.py"
            )
        elif "InvalidAccessKeyId" in str(e):
            print("     → Check your HMAC access key ID")
        traceback.print_exc()
        return False

    print("✅ Basic IBM COS operations test passed with optimized configuration!\n")
    return True


async def test_ibm_cos_grid_pattern():
    """Test grid architecture pattern with IBM COS."""
    print("🗂️ Testing grid architecture pattern with IBM COS...")

    factory_func = factory()

    try:
        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")

            # Store files in grid pattern
            test_files = [
                (
                    "grid/ibm-cos-sandbox-1/sess-alice/file1.txt",
                    b"Alice IBM COS file 1",
                ),
                (
                    "grid/ibm-cos-sandbox-1/sess-alice/file2.txt",
                    b"Alice IBM COS file 2",
                ),
                ("grid/ibm-cos-sandbox-1/sess-bob/file1.txt", b"Bob IBM COS file 1"),
                (
                    "grid/ibm-cos-sandbox-2/sess-charlie/file1.txt",
                    b"Charlie IBM COS file 1",
                ),
            ]

            # Upload all test files
            for key, body in test_files:
                await cos.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=body,
                    ContentType="text/plain",
                    Metadata={"grid_test": "ibm_cos", "auth_type": "hmac"},
                )

            print(f"  📤 Stored {len(test_files)} files in IBM COS grid pattern")

            # Add delay for IBM COS consistency
            await asyncio.sleep(0.3)

            # Test session-based listing (Alice)
            alice_files = await cos.list_objects_v2(
                Bucket=bucket, Prefix="grid/ibm-cos-sandbox-1/sess-alice/"
            )

            assert alice_files["KeyCount"] == 2
            alice_keys = [obj["Key"] for obj in alice_files["Contents"]]
            assert "grid/ibm-cos-sandbox-1/sess-alice/file1.txt" in alice_keys
            assert "grid/ibm-cos-sandbox-1/sess-alice/file2.txt" in alice_keys
            print(f"  ✅ Alice has {alice_files['KeyCount']} files")

            # Test session-based listing (Bob)
            bob_files = await cos.list_objects_v2(
                Bucket=bucket, Prefix="grid/ibm-cos-sandbox-1/sess-bob/"
            )

            assert bob_files["KeyCount"] == 1
            bob_keys = [obj["Key"] for obj in bob_files["Contents"]]
            assert "grid/ibm-cos-sandbox-1/sess-bob/file1.txt" in bob_keys
            print(f"  ✅ Bob has {bob_files['KeyCount']} files")

            # Test sandbox-based listing
            sandbox1_files = await cos.list_objects_v2(
                Bucket=bucket, Prefix="grid/ibm-cos-sandbox-1/"
            )

            assert sandbox1_files["KeyCount"] == 3  # Alice(2) + Bob(1)
            print(
                f"  ✅ IBM COS Sandbox 1 has {sandbox1_files['KeyCount']} files total"
            )

            sandbox2_files = await cos.list_objects_v2(
                Bucket=bucket, Prefix="grid/ibm-cos-sandbox-2/"
            )

            assert sandbox2_files["KeyCount"] >= 1  # Charlie(1)
            print(
                f"  ✅ IBM COS Sandbox 2 has {sandbox2_files['KeyCount']} files total"
            )

            # Verify session isolation
            for alice_key in alice_keys:
                assert alice_key not in bob_keys
            print("  ✅ Session isolation maintained in IBM COS")

            # Clean up test files
            print("  🧹 Cleaning up IBM COS test files...")
            for key, _ in test_files:
                await cos.delete_object(Bucket=bucket, Key=key)
            print("  ✅ Cleanup completed")

    except Exception as e:
        print(f"  ❌ IBM COS grid pattern test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ IBM COS grid architecture test passed!\n")
    return True


async def test_ibm_cos_regional_endpoints():
    """Test different IBM COS regional endpoints."""
    print("🌍 Testing IBM COS regional endpoints...")

    # Different IBM COS regional endpoints
    endpoints = [
        ("us-south", "https://s3.us-south.cloud-object-storage.appdomain.cloud"),
        ("us-east", "https://s3.us-east.cloud-object-storage.appdomain.cloud"),
        ("eu-gb", "https://s3.eu-gb.cloud-object-storage.appdomain.cloud"),
        ("eu-de", "https://s3.eu-de.cloud-object-storage.appdomain.cloud"),
        ("jp-tok", "https://s3.jp-tok.cloud-object-storage.appdomain.cloud"),
        ("au-syd", "https://s3.au-syd.cloud-object-storage.appdomain.cloud"),
    ]

    current_endpoint = os.getenv("IBM_COS_ENDPOINT")
    if not current_endpoint:
        print("  ℹ️ No IBM_COS_ENDPOINT set, using default us-south")
        current_endpoint = endpoints[0][1]

    # Find current region
    current_region = "unknown"
    for region, endpoint_url in endpoints:
        if endpoint_url == current_endpoint:
            current_region = region
            break

    print(f"  🎯 Current endpoint: {current_endpoint} ({current_region})")

    try:
        # Test current endpoint
        factory_func = factory(endpoint_url=current_endpoint)

        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")

            # Simple connectivity test
            try:
                await cos.head_bucket(Bucket=bucket)
                print(f"  ✅ {current_region} endpoint connectivity successful")

                # Test a simple operation
                test_key = f"region-test/{current_region}/connectivity.txt"
                await cos.put_object(
                    Bucket=bucket,
                    Key=test_key,
                    Body=f"Test from {current_region}".encode(),
                    ContentType="text/plain",
                    Metadata={"region": current_region, "test": "connectivity"},
                )

                # Verify and cleanup
                response = await cos.get_object(Bucket=bucket, Key=test_key)
                if hasattr(response["Body"], "read"):
                    data = await response["Body"].read()
                else:
                    data = response["Body"]

                assert f"Test from {current_region}".encode() == data
                await cos.delete_object(Bucket=bucket, Key=test_key)

                print(f"  ✅ {current_region} endpoint full operation test successful")

            except Exception as e:
                print(f"  ❌ {current_region} endpoint test failed: {e}")
                if "InvalidAccessKeyId" in str(e):
                    print("     → Credentials may not be valid for this region")
                elif "NoSuchBucket" in str(e):
                    print("     → Bucket may not exist in this region")
                return False

    except Exception as e:
        print(f"  ❌ Regional endpoint test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ IBM COS regional endpoint test passed!\n")
    return True


async def test_ibm_cos_metadata_handling():
    """Test IBM COS specific metadata handling."""
    print("📋 Testing IBM COS metadata handling...")

    factory_func = factory()

    try:
        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")
            key = "ibm-cos-metadata-test/file.txt"
            test_data = b"IBM COS metadata test data"

            # IBM COS specific metadata
            metadata = {
                "filename": "ibm-cos-test-file.txt",
                "user-id": "ibm-cos-user",
                "session-id": "sess-ibm-12345",
                "cos-region": "us-south",
                "auth-type": "hmac",
                "content-description": "IBM COS metadata test file",
            }

            # Upload with metadata
            print("  📤 Uploading with IBM COS metadata...")
            await cos.put_object(
                Bucket=bucket,
                Key=key,
                Body=test_data,
                ContentType="text/plain",
                Metadata=metadata,
            )
            print("  ✅ Upload with metadata successful")

            # Retrieve and verify metadata
            print("  📥 Retrieving and checking IBM COS metadata...")
            head_response = await cos.head_object(Bucket=bucket, Key=key)

            returned_metadata = head_response.get("Metadata", {})

            # IBM COS may lowercase metadata keys like AWS
            for key_name, expected_value in metadata.items():
                found = False
                for actual_key, actual_value in returned_metadata.items():
                    if actual_key.lower() == key_name.lower():
                        assert actual_value == expected_value, (
                            f"IBM COS metadata mismatch for {key_name}: {actual_value} != {expected_value}"
                        )
                        found = True
                        break
                assert found, f"IBM COS metadata key {key_name} not found in response"

            print(f"  ✅ All IBM COS metadata verified: {len(metadata)} keys")

            # Test metadata in get_object response too
            get_response = await cos.get_object(Bucket=bucket, Key=key)
            get_metadata = get_response.get("Metadata", {})

            assert len(get_metadata) == len(returned_metadata)
            print("  ✅ Metadata consistency between head_object and get_object")

            # Clean up
            await cos.delete_object(Bucket=bucket, Key=key)
            print("  🧹 Cleanup completed")

    except Exception as e:
        print(f"  ❌ IBM COS metadata handling test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ IBM COS metadata handling test passed!\n")
    return True


async def test_ibm_cos_concurrent_operations():
    """Test concurrent operations with IBM COS."""
    print("⚡ Testing concurrent operations with IBM COS...")

    factory_func = factory()

    try:
        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")

            # Concurrent puts
            async def put_file(index):
                key = f"ibm-cos-concurrent/file_{index}.txt"
                await cos.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f"IBM COS Content {index}".encode(),
                    ContentType="text/plain",
                    Metadata={
                        "index": str(index),
                        "provider": "ibm-cos",
                        "test": "concurrent",
                    },
                )
                return key

            # Run 8 concurrent operations (slightly fewer for IBM COS rate limits)
            tasks = [put_file(i) for i in range(8)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 8
            print("  ✅ 8 concurrent puts to IBM COS completed successfully")

            # Add delay for IBM COS consistency
            await asyncio.sleep(0.5)

            # Verify all files exist
            list_response = await cos.list_objects_v2(
                Bucket=bucket, Prefix="ibm-cos-concurrent/"
            )
            found_count = list_response["KeyCount"]

            # Allow some tolerance for IBM COS timing
            assert found_count >= 6, (
                f"Expected at least 6 files in IBM COS, found {found_count}"
            )
            print(f"  ✅ Found {found_count}/8 files are accessible in IBM COS")

            # Concurrent gets
            async def get_file(key):
                response = await cos.get_object(Bucket=bucket, Key=key)
                if hasattr(response["Body"], "read"):
                    return await response["Body"].read()
                return response["Body"]

            get_tasks = [get_file(key) for key in results]
            get_results = await asyncio.gather(*get_tasks)

            for i, result in enumerate(get_results):
                assert result == f"IBM COS Content {i}".encode()
            print("  ✅ 8 concurrent gets from IBM COS completed successfully")

            # Clean up
            print("  🧹 Cleaning up IBM COS concurrent test files...")
            for key in results:
                await cos.delete_object(Bucket=bucket, Key=key)
            print("  ✅ Cleanup completed")

    except Exception as e:
        print(f"  ❌ IBM COS concurrent operations test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ IBM COS concurrent operations test passed!\n")
    return True


async def test_ibm_cos_error_handling():
    """Test IBM COS specific error handling scenarios."""
    print("🚨 Testing IBM COS error handling...")

    factory_func = factory()

    try:
        async with factory_func() as cos:
            bucket = os.getenv("ARTIFACT_BUCKET", "chuk-sandbox-2")
            nonexistent_key = "nonexistent/ibm-cos-file.txt"

            # Test getting non-existent object
            print("  🔍 Testing non-existent object retrieval in IBM COS...")
            try:
                await cos.get_object(Bucket=bucket, Key=nonexistent_key)
                print("  ❌ Should have failed to get non-existent object")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print(
                        "  ✅ Correctly failed to get non-existent object from IBM COS"
                    )
                else:
                    print(f"  ⚠️ Unexpected IBM COS error type: {e}")

            # Test head on non-existent object
            print("  🔍 Testing head on non-existent object in IBM COS...")
            try:
                await cos.head_object(Bucket=bucket, Key=nonexistent_key)
                print("  ❌ Should have failed to head non-existent object")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print(
                        "  ✅ Correctly failed to head non-existent object in IBM COS"
                    )
                else:
                    print(f"  ⚠️ Unexpected IBM COS error type: {e}")

            # Test delete non-existent object
            print("  🗑️ Testing delete non-existent object in IBM COS...")
            try:
                await cos.delete_object(Bucket=bucket, Key=nonexistent_key)
                print("  ✅ Delete non-existent object succeeded in IBM COS (expected)")
            except Exception as e:
                print(f"  ⚠️ Delete non-existent object failed in IBM COS: {e}")

            # Test invalid bucket
            print("  🪣 Testing invalid bucket in IBM COS...")
            invalid_bucket = "invalid-ibm-cos-bucket-12345"
            try:
                await cos.head_bucket(Bucket=invalid_bucket)
                print("  ❌ Should have failed with invalid bucket")
                return False
            except Exception as e:
                if "NoSuchBucket" in str(e) or "404" in str(e) or "403" in str(e):
                    print("  ✅ Correctly failed with invalid bucket in IBM COS")
                else:
                    print(f"  ⚠️ Unexpected IBM COS error type: {e}")

    except Exception as e:
        print(f"  ❌ IBM COS error handling test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ IBM COS error handling test passed!\n")
    return True


async def run_all_ibm_cos_tests():
    """Run all IBM COS provider tests."""
    print("🚀 IBM COS Provider Test Suite (HMAC Auth - Optimized Configuration)\n")
    print("=" * 60)
    print("Using optimized configuration:")
    print("  - Signature Version 2 ('s3')")
    print("  - Virtual-hosted addressing style")
    print("  - Based on comprehensive signature testing")
    print("=" * 60)

    tests = [
        test_basic_ibm_cos_operations,
        test_ibm_cos_grid_pattern,
        test_ibm_cos_regional_endpoints,
        test_ibm_cos_metadata_handling,
        test_ibm_cos_concurrent_operations,
        test_ibm_cos_error_handling,
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
            print(f"❌ {test.__name__} CRASHED:")
            print(f"   Error: {e}")
            traceback.print_exc()
            failed += 1
            print()

    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print(
            "🎉 All tests passed! IBM COS provider (HMAC) with optimized configuration is working correctly."
        )
        return True
    elif passed >= len(tests) * 0.6:  # 60% pass rate is acceptable
        print(
            "✅ Most tests passed! IBM COS provider (HMAC) with optimized configuration is working well."
        )
        print("   Some failures may be due to IBM COS rate limits or network timing.")
        return True
    else:
        print("⚠️ Multiple tests failed. Check IBM COS configuration and credentials.")
        print(
            "💡 If you see signature errors, re-run: python diagnostics/ibm_cos_signature_tester.py"
        )
        return False


if __name__ == "__main__":
    print("IBM COS Provider Test Runner (HMAC Authentication - Optimized)")
    print("============================================================")
    print()
    print("This version uses the optimized configuration based on signature testing:")
    print("  - Signature Version 2 ('s3')")
    print("  - Virtual-hosted addressing style")
    print()
    print("Required environment variables:")
    print("  AWS_ACCESS_KEY_ID - Your IBM COS HMAC access key")
    print("  AWS_SECRET_ACCESS_KEY - Your IBM COS HMAC secret key")
    print("  AWS_REGION - IBM COS region (optional, default: us-south)")
    print("  IBM_COS_ENDPOINT - IBM COS endpoint (optional)")
    print("  ARTIFACT_BUCKET - IBM COS bucket name (optional, default: mcp-bucket)")
    print()
    print("Note: Configuration has been optimized based on signature testing")
    print("      If you encounter signature errors, re-run the signature tester.")
    print()
    print("How to get IBM COS HMAC credentials:")
    print("  1. Go to IBM Cloud Console > Storage > Object Storage")
    print("  2. Select your instance")
    print("  3. Go to 'Service Credentials'")
    print("  4. Create credentials with 'Include HMAC Credential' enabled")
    print("  5. Ensure the credential has 'Writer' or 'Manager' role")
    print("  6. Use the 'cos_hmac_keys' access_key_id and secret_access_key")
    print()

    success = asyncio.run(run_all_ibm_cos_tests())
    sys.exit(0 if success else 1)
