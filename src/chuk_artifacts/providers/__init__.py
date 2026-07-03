# -*- coding: utf-8 -*-
# chuk_artifacts/providers/__init__.py
"""
Convenience re-exports so caller code can do:

    from chuk_artifacts.providers import s3, ibm_cos, memory, filesystem, vfs_adapter, azure_blob
"""

from . import s3, ibm_cos, memory, filesystem, vfs_adapter

# Azure Blob Storage is optional - only import if azure-storage-blob is installed
try:
    from . import azure_blob
    __all__ = ["s3", "ibm_cos", "memory", "filesystem", "vfs_adapter", "azure_blob"]
except ImportError:
    __all__ = ["s3", "ibm_cos", "memory", "filesystem", "vfs_adapter"]
