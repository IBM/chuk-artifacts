#!/usr/bin/env python3
# diagnostics/ibm_cos_signature_tester.py
"""
Comprehensive IBM COS Signature Version Tester

This script systematically tests all possible signature configurations
to definitively determine what works with your specific IBM COS instance.

IBM COS signature requirements can vary by:
- Region (us-south, eu-gb, etc.)
- Instance configuration
- Service plan (Lite vs Standard)
- When the instance was created
"""

import asyncio
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Load .env
def load_dotenv():
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        print(f"📁 Loading environment from: {env_file}")
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = value
        print("✅ Environment loaded from .env file")


load_dotenv()

import aioboto3  # noqa: E402
from aioboto3.session import AioConfig  # noqa: E402


class SignatureTestResult:
    """Container for signature test results."""

    def __init__(self, name, config, success=False, operations=None, error=None):
        self.name = name
        self.config = config
        self.success = success
        self.operations = operations or {}
        self.error = error
        self.score = 0  # Success score

    def calculate_score(self):
        """Calculate success score based on working operations."""
        weights = {
            "head_bucket": 1,
            "list_objects": 2,
            "get_object": 2,
            "put_object": 4,
            "delete_object": 1,
        }

        score = 0
        for op, success in self.operations.items():
            if success:
                score += weights.get(op, 1)
        self.score = score
        return score


async def test_signature_configuration(
    config_name, config, endpoint, region, access_key, secret_key, bucket
):
    """Test a specific signature configuration comprehensively."""
    print(f"\n🔬 Testing: {config_name}")
    print(f"   Configuration: {config}")

    result = SignatureTestResult(config_name, config)
    session = aioboto3.Session()

    try:
        client_kwargs = {
            "service_name": "s3",
            "endpoint_url": endpoint,
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }

        if config:
            client_kwargs["config"] = config

        async with session.client(**client_kwargs) as client:
            # Test 1: Head Bucket (basic connectivity)
            print("   📋 Testing head_bucket...")
            try:
                await client.head_bucket(Bucket=bucket)
                result.operations["head_bucket"] = True
                print("      ✅ SUCCESS")
            except Exception as e:
                result.operations["head_bucket"] = False
                error_type = type(e).__name__
                if "SignatureDoesNotMatch" in str(e):
                    error_type = "SignatureDoesNotMatch"
                elif "AccessDenied" in str(e):
                    error_type = "AccessDenied"
                elif "NoSuchBucket" in str(e):
                    error_type = "NoSuchBucket"
                print(f"      ❌ {error_type}")
                result.error = error_type
                return result

            # Test 2: List Objects (read permission)
            print("   📂 Testing list_objects_v2...")
            try:
                response = await client.list_objects_v2(Bucket=bucket, MaxKeys=1)
                result.operations["list_objects"] = True
                object_count = response.get("KeyCount", 0)
                print(f"      ✅ SUCCESS ({object_count} objects)")
            except Exception as e:
                result.operations["list_objects"] = False
                error_type = type(e).__name__
                if "AccessDenied" in str(e):
                    error_type = "AccessDenied"
                print(f"      ❌ {error_type}")

            # Test 3: Get Object (if any objects exist)
            print("   📥 Testing get_object...")
            try:
                # First, list to find an object
                list_response = await client.list_objects_v2(Bucket=bucket, MaxKeys=1)
                if list_response.get("KeyCount", 0) > 0:
                    existing_key = list_response["Contents"][0]["Key"]
                    await client.head_object(Bucket=bucket, Key=existing_key)
                    result.operations["get_object"] = True
                    print(f"      ✅ SUCCESS (tested with {existing_key})")
                else:
                    print("      ⏭️ SKIPPED (no existing objects)")
                    result.operations["get_object"] = None
            except Exception as e:
                result.operations["get_object"] = False
                error_type = type(e).__name__
                print(f"      ❌ {error_type}")

            # Test 4: Put Object (write permission)
            print("   📤 Testing put_object...")
            test_key = f"signature-test/{config_name.replace(' ', '-').replace('(', '').replace(')', '')}-{datetime.now().strftime('%H%M%S')}.txt"
            try:
                put_response = await client.put_object(
                    Bucket=bucket,
                    Key=test_key,
                    Body=f"Signature test for {config_name}".encode(),
                    ContentType="text/plain",
                    Metadata={"test": "signature", "config": config_name},
                )
                result.operations["put_object"] = True
                etag = put_response.get("ETag", "unknown")
                print(f"      ✅ SUCCESS (ETag: {etag})")

                # Test 5: Delete Object (cleanup and delete permission)
                print("   🗑️ Testing delete_object...")
                try:
                    await client.delete_object(Bucket=bucket, Key=test_key)
                    result.operations["delete_object"] = True
                    print("      ✅ SUCCESS")
                except Exception as e:
                    result.operations["delete_object"] = False
                    error_type = type(e).__name__
                    print(f"      ❌ {error_type}")

            except Exception as e:
                result.operations["put_object"] = False
                error_type = type(e).__name__
                if "AccessDenied" in str(e):
                    error_type = "AccessDenied"
                elif "SignatureDoesNotMatch" in str(e):
                    error_type = "SignatureDoesNotMatch"
                print(f"      ❌ {error_type}")
                result.error = error_type

        result.calculate_score()
        result.success = result.score > 0

    except Exception as e:
        result.operations["connection"] = False
        result.error = type(e).__name__
        print(f"   ❌ Connection failed: {result.error}")

    return result


async def run_comprehensive_signature_test():
    """Run comprehensive signature testing for IBM COS."""
    print("🔬 Comprehensive IBM COS Signature Version Tester")
    print("=" * 70)

    # Get configuration
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    endpoint = os.getenv(
        "IBM_COS_ENDPOINT", "https://s3.us-south.cloud-object-storage.appdomain.cloud"
    )
    region = os.getenv("AWS_REGION", "us-south")
    bucket = os.getenv("ARTIFACT_BUCKET", "mcp-bucket")

    print("📋 Test Configuration:")
    print(f"   Endpoint: {endpoint}")
    print(f"   Region: {region}")
    print(f"   Bucket: {bucket}")
    print(f"   Access Key: {'set' if access_key else 'NOT SET'}")

    if not (access_key and secret_key):
        print("\n❌ Cannot run tests - missing credentials")
        print("Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file")
        return False, []

    # Define test configurations
    test_configs = [
        # Core IBM COS configurations
        (
            "Signature v2 + Path (IBM COS Classic)",
            AioConfig(signature_version="s3", s3={"addressing_style": "path"}),
        ),
        (
            "Signature v2 + Virtual (IBM COS Alt)",
            AioConfig(signature_version="s3", s3={"addressing_style": "virtual"}),
        ),
        # AWS-style configurations (some IBM COS instances support these)
        (
            "Signature v4 + Path (AWS Style)",
            AioConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        ),
        (
            "Signature v4 + Virtual (AWS Default)",
            AioConfig(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        ),
        # Legacy/alternative configurations
        ("Signature v2 Only", AioConfig(signature_version="s3")),
        ("Signature v4 Only", AioConfig(signature_version="s3v4")),
        # Default configurations
        ("aioboto3 Default", AioConfig()),
        ("No Config (boto3 default)", None),
        # Regional variants (some regions may have different requirements)
        (
            "v2 + Path + Region Override",
            AioConfig(
                signature_version="s3",
                s3={"addressing_style": "path"},
                region_name=region,
            ),
        ),
        (
            "v4 + Path + Region Override",
            AioConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                region_name=region,
            ),
        ),
    ]

    print(f"\n🧪 Running {len(test_configs)} signature configuration tests...")
    print("=" * 70)

    results = []

    for config_name, config in test_configs:
        result = await test_signature_configuration(
            config_name, config, endpoint, region, access_key, secret_key, bucket
        )
        results.append(result)

        # Brief pause between tests to avoid rate limiting
        await asyncio.sleep(0.5)

    return True, results


def analyze_results(results):
    """Analyze test results and provide recommendations."""
    print("\n📊 Signature Test Results Analysis")
    print("=" * 70)

    # Sort by score (best first)
    results.sort(key=lambda r: r.score, reverse=True)

    # Results table
    print(f"{'Configuration':<35} {'Score':<6} {'Operations':<50}")
    print("-" * 91)

    working_configs = []
    partial_configs = []
    failed_configs = []

    for result in results:
        # Format operations
        ops = []
        for op, success in result.operations.items():
            if success is True:
                ops.append(f"✅{op}")
            elif success is False:
                ops.append(f"❌{op}")
            # None (skipped) operations not shown

        ops_str = " ".join(ops)[:48]

        print(f"{result.name:<35} {result.score:<6} {ops_str}")

        # Categorize results
        if result.score >= 8:  # Can read and write
            working_configs.append(result)
        elif result.score >= 3:  # Can at least read
            partial_configs.append(result)
        else:
            failed_configs.append(result)

    # Analysis
    print("\n🔍 Analysis:")
    print(f"   ✅ Fully working: {len(working_configs)} configurations")
    print(f"   ⚠️ Partially working: {len(partial_configs)} configurations")
    print(f"   ❌ Failed: {len(failed_configs)} configurations")

    # Recommendations
    print("\n💡 Recommendations:")

    if working_configs:
        best = working_configs[0]
        print(f"🏆 BEST CONFIGURATION: {best.name}")
        print(f"   Score: {best.score}/10")
        print("   Use this configuration for your IBM COS provider")

        # Show config details
        if best.config:
            print("   Configuration details:")
            if hasattr(best.config, "signature_version"):
                print(f"     signature_version = '{best.config.signature_version}'")
            if hasattr(best.config, "s3") and best.config.s3:
                addressing = best.config.s3.get("addressing_style")
                if addressing:
                    print(f"     addressing_style = '{addressing}'")

        return best

    elif partial_configs:
        best_partial = partial_configs[0]
        print(f"⚠️ PARTIAL SUCCESS: {best_partial.name}")
        print(f"   Score: {best_partial.score}/10")
        print("   Signature works but limited by permissions")
        print("   Focus on fixing bucket permissions rather than signature")

        return best_partial

    else:
        print("❌ NO WORKING CONFIGURATIONS FOUND")
        print("   Possible issues:")
        print("   - Invalid HMAC credentials")
        print("   - Incorrect endpoint URL")
        print("   - Network connectivity issues")
        print("   - Bucket doesn't exist or wrong region")

        return None


def generate_provider_code(best_result):
    """Generate the correct provider code based on test results."""
    if not best_result or not best_result.config:
        return None

    config = best_result.config

    # Extract configuration
    signature_version = getattr(config, "signature_version", "s3")
    addressing_style = "path"  # default

    if hasattr(config, "s3") and config.s3:
        addressing_style = config.s3.get("addressing_style", "path")

    provider_code = f'''# -*- coding: utf-8 -*-
# chuk_artifacts/providers/ibm_cos.py
"""
Factory for an aioboto3 client wired for IBM Cloud Object Storage (COS).

AUTO-GENERATED by IBM COS Signature Tester
Best configuration: {best_result.name}
Score: {best_result.score}/10
Tested on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

from __future__ import annotations
import os, aioboto3
from aioboto3.session import AioConfig
from typing import Optional, Callable, AsyncContextManager


def factory(
    *,
    endpoint_url: Optional[str] = None,
    region: str = "us-south",
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
) -> Callable[[], AsyncContextManager]:
    """
    Return an async-context S3 client for IBM COS (HMAC only).
    
    Tested configuration: {best_result.name}
    """
    endpoint_url = endpoint_url or os.getenv(
        "IBM_COS_ENDPOINT",
        "https://s3.us-south.cloud-object-storage.appdomain.cloud",
    )
    access_key = access_key or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
    
    # Extract region from endpoint
    if endpoint_url:
        if "us-south" in endpoint_url:
            region = "us-south"
        elif "us-east" in endpoint_url:
            region = "us-east"
        elif "eu-gb" in endpoint_url:
            region = "eu-gb"
        elif "eu-de" in endpoint_url:
            region = "eu-de"
        elif "jp-tok" in endpoint_url:
            region = "jp-tok"
        elif "au-syd" in endpoint_url:
            region = "au-syd"
    
    env_region = os.getenv('AWS_REGION')
    if env_region:
        region = env_region

    if not (access_key and secret_key):
        raise RuntimeError(
            "HMAC credentials missing. "
            "Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY "
            "or generate an HMAC key for your COS instance."
        )

    def _make() -> AsyncContextManager:
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=AioConfig(
                signature_version='{signature_version}',
                s3={{'addressing_style': '{addressing_style}'}},
                read_timeout=60,
                connect_timeout=30,
                retries={{
                    'max_attempts': 3,
                    'mode': 'adaptive'
                }}
            )
        )

    return _make


def client(
    *,
    endpoint_url: Optional[str] = None,
    region: Optional[str] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
):
    """Return an aioboto3 S3 client context manager for IBM COS."""
    session = aioboto3.Session()
    
    endpoint_url = endpoint_url or os.getenv(
        "IBM_COS_ENDPOINT",
        "https://s3.us-south.cloud-object-storage.appdomain.cloud"
    )
    
    if not region:
        if "us-south" in endpoint_url:
            region = "us-south"
        elif "us-east" in endpoint_url:
            region = "us-east"
        elif "eu-gb" in endpoint_url:
            region = "eu-gb"
        else:
            region = "us-south"
    
    return session.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region,
        aws_access_key_id=access_key or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=secret_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=AioConfig(
            signature_version='{signature_version}',
            s3={{'addressing_style': '{addressing_style}'}},
            read_timeout=60,
            connect_timeout=30
        )
    )
'''

    return provider_code


async def save_provider_file(provider_code):
    """Save the generated provider code to file."""
    provider_file = Path("src/chuk_artifacts/providers/ibm_cos.py")

    try:
        # Backup existing file
        if provider_file.exists():
            backup_file = provider_file.with_suffix(
                f".py.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            provider_file.rename(backup_file)
            print(f"💾 Backed up existing provider to: {backup_file}")

        # Write new provider
        provider_file.write_text(provider_code, encoding="utf-8")
        print(f"✅ Created optimized provider: {provider_file}")
        return True

    except Exception as e:
        print(f"❌ Failed to save provider: {e}")
        return False


def save_test_results(results):
    """Save test results to JSON for future reference."""
    results_file = (
        Path("diagnostics")
        / f"signature_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    try:
        results_data = []
        for result in results:
            results_data.append(
                {
                    "name": result.name,
                    "config": str(result.config) if result.config else None,
                    "success": result.success,
                    "score": result.score,
                    "operations": result.operations,
                    "error": result.error,
                }
            )

        with open(results_file, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "endpoint": os.getenv("IBM_COS_ENDPOINT"),
                    "region": os.getenv("AWS_REGION"),
                    "bucket": os.getenv("ARTIFACT_BUCKET"),
                    "results": results_data,
                },
                f,
                indent=2,
            )

        print(f"💾 Saved test results to: {results_file}")

    except Exception as e:
        print(f"⚠️ Could not save test results: {e}")


async def main():
    """Main test routine."""
    print("🔬 IBM COS Signature Version Tester")
    print("Systematically tests all signature configurations to find the optimal one")
    print("=" * 70)

    # Run comprehensive tests
    success, results = await run_comprehensive_signature_test()

    if not success:
        return False

    # Analyze results
    best_result = analyze_results(results)

    # Save results for reference
    save_test_results(results)

    # Generate and save provider if we found a working config
    if best_result and best_result.score >= 8:
        print("\n🔧 Generating Optimized Provider")
        print("=" * 70)

        provider_code = generate_provider_code(best_result)
        if provider_code:
            saved = await save_provider_file(provider_code)

            if saved:
                print("\n🎉 SUCCESS!")
                print(f"✅ Found optimal configuration: {best_result.name}")
                print("✅ Generated and saved optimized provider")
                print("\n🚀 Next Steps:")
                print("1. Test the optimized provider:")
                print("   python diagnostics/quick_cos_check.py")
                print("2. Run full test suite:")
                print("   uv run diagnostics/ibm_cos_hmac_runner.py")
                return True

    elif best_result and best_result.score >= 3:
        print("\n⚠️ Partial Success")
        print("Signature configuration works for reading but write access is blocked")
        print("This is likely a permissions issue, not a signature issue")
        print("💡 Run: python diagnostics/ibm_cos_permissions_diagnostic.py")

    else:
        print("\n❌ No Working Configuration Found")
        print("Check your credentials, endpoint, and network connectivity")

    return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
