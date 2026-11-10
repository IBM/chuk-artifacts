#!/usr/bin/env python3
# diagnostics/s3_runner.py
"""
Comprehensive test runner for S3 provider to understand its behavior.
Run this to test the S3 provider independently with real S3 or MinIO.
"""

import asyncio
import sys
import traceback
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chuk_artifacts.providers.s3 import factory


def check_s3_config():
    """Check S3 configuration and provide helpful feedback."""
    print("🔧 Checking S3 Configuration...")

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint = os.getenv("S3_ENDPOINT_URL")

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
        print(f"  ✅ S3_ENDPOINT_URL: {endpoint}")
    else:
        print("  ℹ️ S3_ENDPOINT_URL not set (using AWS S3)")

    return True


async def test_basic_s3_operations():
    """Test basic S3 provider operations."""
    print("\n🧪 Testing basic S3 provider operations...")

    if not check_s3_config():
        print(
            "  ❌ S3 configuration incomplete. Please set required environment variables:"
        )
        print("     export AWS_ACCESS_KEY_ID=your_access_key")
        print("     export AWS_SECRET_ACCESS_KEY=your_secret_key")
        print("     export AWS_REGION=us-east-1  # optional")
        print("     export S3_ENDPOINT_URL=http://localhost:9000  # for MinIO")
        return False

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "chuk-sandbox-2"
            key = "test-file.txt"
            test_data = b"Hello, S3 provider!"

            # Test bucket creation/validation
            print("  🪣 Testing bucket operations...")
            try:
                await s3.head_bucket(Bucket=bucket)
                print(f"  ✅ Bucket '{bucket}' exists")
            except Exception as e:
                if "NoSuchBucket" in str(e) or "404" in str(e):
                    print(f"  ⚠️ Bucket '{bucket}' doesn't exist")
                    print("     You may need to create it manually in S3/MinIO")
                    print("     Or use a different bucket name")
                    return False
                else:
                    print(f"  ❌ Bucket check failed: {e}")
                    return False

            # Test put_object
            print("  📤 Testing put_object...")
            put_response = await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=test_data,
                ContentType="text/plain",
                Metadata={"filename": "test-file.txt", "test": "true"},
            )

            assert "ETag" in put_response
            print(f"  ✅ put_object successful, ETag: {put_response['ETag']}")

            # Test head_object
            print("  📋 Testing head_object...")
            head_response = await s3.head_object(Bucket=bucket, Key=key)

            assert head_response["ContentLength"] == len(test_data)
            assert head_response["ContentType"] == "text/plain"
            print(
                f"  ✅ head_object successful, size: {head_response['ContentLength']} bytes"
            )

            # Test get_object
            print("  📥 Testing get_object...")
            get_response = await s3.get_object(Bucket=bucket, Key=key)

            # Handle different response body formats
            if hasattr(get_response["Body"], "read"):
                body_data = await get_response["Body"].read()
            else:
                body_data = get_response["Body"]

            assert body_data == test_data
            assert get_response["ContentType"] == "text/plain"
            print(f"  ✅ get_object successful: {body_data.decode()}")

            # Test list_objects_v2
            print("  📋 Testing list_objects_v2...")
            list_response = await s3.list_objects_v2(Bucket=bucket, Prefix="test-")

            assert list_response["KeyCount"] >= 1
            keys = [obj["Key"] for obj in list_response["Contents"]]
            assert key in keys
            print(f"  ✅ Found {list_response['KeyCount']} objects with 'test-' prefix")

            # Test presigned URL generation
            print("  🔗 Testing presigned URL...")
            try:
                url = await s3.generate_presigned_url(
                    "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
                )

                assert "http" in url.lower()
                print(f"  ✅ Generated presigned URL: {url[:50]}...")

            except Exception as e:
                if "oauth" in str(e).lower() or "credential" in str(e).lower():
                    print(f"  ⚠️ Presigned URL failed (credential type issue): {e}")
                else:
                    print(f"  ❌ Presigned URL failed: {e}")
                    return False

            # Test delete_object
            print("  🗑️ Testing delete_object...")
            await s3.delete_object(Bucket=bucket, Key=key)

            # Verify deletion
            try:
                await s3.head_object(Bucket=bucket, Key=key)
                print("  ❌ Object should have been deleted")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print("  ✅ delete_object successful")
                else:
                    print(f"  ❌ Unexpected error during delete verification: {e}")
                    return False

    except Exception as e:
        print(f"  ❌ S3 operations failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Basic S3 operations test passed!\n")
    return True


async def test_s3_grid_pattern():
    """Test grid architecture pattern with S3."""
    print("🗂️ Testing grid architecture pattern with S3...")

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "chuk-sandbox-2"

            # Store files in grid pattern
            test_files = [
                ("grid/sandbox-1/sess-alice/file1.txt", b"Alice file 1"),
                ("grid/sandbox-1/sess-alice/file2.txt", b"Alice file 2"),
                ("grid/sandbox-1/sess-bob/file1.txt", b"Bob file 1"),
                ("grid/sandbox-2/sess-charlie/file1.txt", b"Charlie file 1"),
            ]

            # Upload all test files
            for key, body in test_files:
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=body,
                    ContentType="text/plain",
                    Metadata={"grid_test": "true"},
                )

            print(f"  📤 Stored {len(test_files)} files in grid pattern")

            # Test session-based listing (Alice)
            alice_files = await s3.list_objects_v2(
                Bucket=bucket, Prefix="grid/sandbox-1/sess-alice/"
            )

            assert alice_files["KeyCount"] == 2
            alice_keys = [obj["Key"] for obj in alice_files["Contents"]]
            assert "grid/sandbox-1/sess-alice/file1.txt" in alice_keys
            assert "grid/sandbox-1/sess-alice/file2.txt" in alice_keys
            print(f"  ✅ Alice has {alice_files['KeyCount']} files")

            # Test session-based listing (Bob)
            bob_files = await s3.list_objects_v2(
                Bucket=bucket, Prefix="grid/sandbox-1/sess-bob/"
            )

            assert bob_files["KeyCount"] == 1
            bob_keys = [obj["Key"] for obj in bob_files["Contents"]]
            assert "grid/sandbox-1/sess-bob/file1.txt" in bob_keys
            print(f"  ✅ Bob has {bob_files['KeyCount']} files")

            # Test sandbox-based listing
            sandbox1_files = await s3.list_objects_v2(
                Bucket=bucket, Prefix="grid/sandbox-1/"
            )

            assert sandbox1_files["KeyCount"] == 3  # Alice(2) + Bob(1)
            print(f"  ✅ Sandbox 1 has {sandbox1_files['KeyCount']} files total")

            sandbox2_files = await s3.list_objects_v2(
                Bucket=bucket, Prefix="grid/sandbox-2/"
            )

            assert sandbox2_files["KeyCount"] == 1  # Charlie(1)
            print(f"  ✅ Sandbox 2 has {sandbox2_files['KeyCount']} files total")

            # Verify session isolation
            for alice_key in alice_keys:
                assert alice_key not in bob_keys
            print("  ✅ Session isolation maintained")

            # Clean up test files
            print("  🧹 Cleaning up test files...")
            for key, _ in test_files:
                await s3.delete_object(Bucket=bucket, Key=key)
            print("  ✅ Cleanup completed")

    except Exception as e:
        print(f"  ❌ Grid pattern test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Grid architecture test passed!\n")
    return True


async def test_s3_concurrent_operations():
    """Test concurrent operations with S3."""
    print("⚡ Testing concurrent operations with S3...")

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "chuk-sandbox-2"

            # Concurrent puts
            async def put_file(index):
                key = f"concurrent/file_{index}.txt"
                await s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f"Content {index}".encode(),
                    ContentType="text/plain",
                    Metadata={"index": str(index)},
                )
                return key

            # Run 10 concurrent operations
            tasks = [put_file(i) for i in range(10)]
            results = await asyncio.gather(*tasks)

            assert len(results) == 10
            print("  ✅ 10 concurrent puts completed successfully")

            # Verify all files exist
            list_response = await s3.list_objects_v2(
                Bucket=bucket, Prefix="concurrent/"
            )
            assert list_response["KeyCount"] == 10
            print(f"  ✅ All {list_response['KeyCount']} files are accessible")

            # Concurrent gets
            async def get_file(key):
                response = await s3.get_object(Bucket=bucket, Key=key)
                if hasattr(response["Body"], "read"):
                    return await response["Body"].read()
                return response["Body"]

            get_tasks = [get_file(key) for key in results]
            get_results = await asyncio.gather(*get_tasks)

            for i, result in enumerate(get_results):
                assert result == f"Content {i}".encode()
            print("  ✅ 10 concurrent gets completed successfully")

            # Clean up
            print("  🧹 Cleaning up concurrent test files...")
            for key in results:
                await s3.delete_object(Bucket=bucket, Key=key)
            print("  ✅ Cleanup completed")

    except Exception as e:
        print(f"  ❌ Concurrent operations test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Concurrent operations test passed!\n")
    return True


async def test_s3_error_handling():
    """Test error handling scenarios."""
    print("🚨 Testing S3 error handling...")

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "chuk-sandbox-2"
            nonexistent_key = "nonexistent/file.txt"

            # Test getting non-existent object
            print("  🔍 Testing non-existent object retrieval...")
            try:
                await s3.get_object(Bucket=bucket, Key=nonexistent_key)
                print("  ❌ Should have failed to get non-existent object")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print("  ✅ Correctly failed to get non-existent object")
                else:
                    print(f"  ⚠️ Unexpected error type: {e}")

            # Test head on non-existent object
            print("  🔍 Testing head on non-existent object...")
            try:
                await s3.head_object(Bucket=bucket, Key=nonexistent_key)
                print("  ❌ Should have failed to head non-existent object")
                return False
            except Exception as e:
                if "NoSuchKey" in str(e) or "404" in str(e):
                    print("  ✅ Correctly failed to head non-existent object")
                else:
                    print(f"  ⚠️ Unexpected error type: {e}")

            # Test delete non-existent object (should succeed silently)
            print("  🗑️ Testing delete non-existent object...")
            try:
                await s3.delete_object(Bucket=bucket, Key=nonexistent_key)
                print("  ✅ Delete non-existent object succeeded (expected)")
            except Exception as e:
                print(f"  ⚠️ Delete non-existent object failed: {e}")

            # Test invalid bucket
            print("  🪣 Testing invalid bucket...")
            invalid_bucket = "this-bucket-definitely-does-not-exist-12345"
            try:
                await s3.head_bucket(Bucket=invalid_bucket)
                print("  ❌ Should have failed with invalid bucket")
                return False
            except Exception as e:
                if "NoSuchBucket" in str(e) or "404" in str(e) or "403" in str(e):
                    print("  ✅ Correctly failed with invalid bucket")
                else:
                    print(f"  ⚠️ Unexpected error type: {e}")

    except Exception as e:
        print(f"  ❌ Error handling test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Error handling test passed!\n")
    return True


async def test_s3_metadata_handling():
    """Test metadata handling with S3."""
    print("📋 Testing S3 metadata handling...")

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "chuk-sandbox-2"
            key = "metadata-test/file.txt"
            test_data = b"Test data with metadata"

            metadata = {
                "filename": "test-file.txt",
                "user-id": "test-user",
                "session-id": "sess-12345",
                "content-description": "Test file with metadata",
            }

            # Upload with metadata
            print("  📤 Uploading with metadata...")
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=test_data,
                ContentType="text/plain",
                Metadata=metadata,
            )
            print("  ✅ Upload with metadata successful")

            # Retrieve and verify metadata
            print("  📥 Retrieving and checking metadata...")
            head_response = await s3.head_object(Bucket=bucket, Key=key)

            returned_metadata = head_response.get("Metadata", {})

            # AWS/S3 may lowercase metadata keys
            for key_name, expected_value in metadata.items():
                # Check both original case and lowercase
                found = False
                for actual_key, actual_value in returned_metadata.items():
                    if actual_key.lower() == key_name.lower():
                        assert actual_value == expected_value, (
                            f"Metadata mismatch for {key_name}: {actual_value} != {expected_value}"
                        )
                        found = True
                        break
                assert found, f"Metadata key {key_name} not found in response"

            print(f"  ✅ All metadata verified: {len(metadata)} keys")

            # Clean up
            await s3.delete_object(Bucket=bucket, Key=key)
            print("  🧹 Cleanup completed")

    except Exception as e:
        print(f"  ❌ Metadata handling test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Metadata handling test passed!\n")
    return True


async def test_s3_large_file_handling():
    """Test handling of larger files."""
    print("📦 Testing large file handling...")

    factory_func = factory()

    try:
        async with factory_func() as s3:
            bucket = "test-artifacts-bucket"
            key = "large-file-test/big.dat"

            # Create a moderately large file (1MB)
            large_data = b"0123456789" * 104857  # ~1MB

            print(f"  📤 Uploading large file ({len(large_data):,} bytes)...")
            start_time = asyncio.get_event_loop().time()

            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=large_data,
                ContentType="application/octet-stream",
                Metadata={"size": str(len(large_data))},
            )

            upload_time = asyncio.get_event_loop().time() - start_time
            print(f"  ✅ Upload completed in {upload_time:.2f} seconds")

            # Verify size
            print("  📋 Verifying file size...")
            head_response = await s3.head_object(Bucket=bucket, Key=key)
            assert head_response["ContentLength"] == len(large_data)
            print(f"  ✅ Size verified: {head_response['ContentLength']:,} bytes")

            # Download and verify content
            print("  📥 Downloading and verifying content...")
            start_time = asyncio.get_event_loop().time()

            get_response = await s3.get_object(Bucket=bucket, Key=key)

            if hasattr(get_response["Body"], "read"):
                downloaded_data = await get_response["Body"].read()
            else:
                downloaded_data = get_response["Body"]

            download_time = asyncio.get_event_loop().time() - start_time

            assert downloaded_data == large_data
            print(
                f"  ✅ Download and verification completed in {download_time:.2f} seconds"
            )

            # Clean up
            await s3.delete_object(Bucket=bucket, Key=key)
            print("  🧹 Cleanup completed")

    except Exception as e:
        print(f"  ❌ Large file handling test failed: {e}")
        traceback.print_exc()
        return False

    print("✅ Large file handling test passed!\n")
    return True


async def run_all_s3_tests():
    """Run all S3 provider tests."""
    print("🚀 S3 Provider Test Suite\n")
    print("=" * 60)

    tests = [
        test_basic_s3_operations,
        test_s3_grid_pattern,
        test_s3_concurrent_operations,
        test_s3_error_handling,
        test_s3_metadata_handling,
        test_s3_large_file_handling,
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
        print("🎉 All tests passed! S3 provider is working correctly.")
        return True
    else:
        print("⚠️ Some tests failed. Check S3 configuration and connectivity.")
        return False


if __name__ == "__main__":
    print("S3 Provider Test Runner")
    print("=======================")
    print()
    print("Required environment variables:")
    print("  AWS_ACCESS_KEY_ID - Your S3 access key")
    print("  AWS_SECRET_ACCESS_KEY - Your S3 secret key")
    print("  AWS_REGION - AWS region (optional, default: us-east-1)")
    print("  S3_ENDPOINT_URL - Custom endpoint for MinIO/other S3-compatible services")
    print()
    print("Note: You need a bucket named 'chuk-sandbox-2' to exist in your S3/MinIO")
    print("      or modify the bucket name in the tests.")
    print()

    success = asyncio.run(run_all_s3_tests())
    sys.exit(0 if success else 1)
