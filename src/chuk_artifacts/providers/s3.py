# -*- coding: utf-8 -*-
# chuk_artifacts/providers/s3.py
"""
AWS S3 provider for artifact storage.

Uses aioboto3 to provide S3-compatible storage with full async support.
Supports standard AWS credentials and S3-compatible endpoints.
"""

from __future__ import annotations
import os
import aioboto3
from aioboto3.session import AioConfig
from contextlib import asynccontextmanager
from typing import Optional, Callable, AsyncContextManager


def _make_config(signature_version: Optional[str] = None) -> AioConfig:
    """Build the AioConfig, defaulting to SigV4 so presigned URLs work in all regions."""
    return AioConfig(
        signature_version=signature_version
        or os.getenv("S3_SIGNATURE_VERSION")
        or "s3v4"
    )


def factory(
    *,
    endpoint_url: Optional[str] = None,
    region: Optional[str] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    signature_version: Optional[str] = None,
) -> Callable[[], AsyncContextManager]:
    """
    Create an S3 client factory.

    Parameters
    ----------
    endpoint_url : str, optional
        Custom S3 endpoint (for MinIO, DigitalOcean Spaces, etc.)
    region : str, optional
        AWS region (default: us-east-1)
    access_key : str, optional
        AWS access key ID (falls back to environment)
    secret_key : str, optional
        AWS secret access key (falls back to environment)
    signature_version : str, optional
        Request signing version (falls back to S3_SIGNATURE_VERSION, then
        "s3v4"). SigV4 is required by newer regions (e.g. ap-south-1) and
        is used for presigned URLs too.

    Returns
    -------
    Callable[[], AsyncContextManager]
        Factory function that returns S3 client context managers
    """
    # Get configuration from parameters or environment
    endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
    region = region or os.getenv("AWS_REGION", "us-east-1")
    access_key = access_key or os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
    config = _make_config(signature_version)

    if not (access_key and secret_key):
        raise RuntimeError(
            "AWS credentials missing. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
            "environment variables or pass them as parameters."
        )

    @asynccontextmanager
    async def _ctx():
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=config,
        ) as client:
            yield client  # ← the channel to real S3 / MinIO

    return _ctx


# Backward compatibility - direct client function
def client(
    *,
    endpoint_url: Optional[str] = None,
    region: Optional[str] = None,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    signature_version: Optional[str] = None,
):
    """
    Return an aioboto3 S3 client context manager.

    This is a convenience function for direct usage.
    The factory() function is preferred for use with ArtifactStore.
    """
    session = aioboto3.Session()
    return session.client(
        "s3",
        endpoint_url=endpoint_url or os.getenv("S3_ENDPOINT_URL"),
        region_name=region or os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=access_key or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=secret_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=_make_config(signature_version),
    )
