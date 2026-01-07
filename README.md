# CHUK Artifacts

> **Unified VFS-backed artifact and workspace storage with scope-based isolation—built for AI apps and MCP servers**

[![PyPI version](https://img.shields.io/pypi/v/chuk-artifacts)](https://pypi.org/project/chuk-artifacts/)
[![Python](https://img.shields.io/pypi/pyversions/chuk-artifacts.svg)](https://pypi.org/project/chuk-artifacts/)
[![Tests](https://img.shields.io/badge/tests-778%20passing-success.svg)](#testing)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen.svg)](#testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Async](https://img.shields.io/badge/async-await-green.svg)](https://docs.python.org/3/library/asyncio.html)

CHUK Artifacts provides a **unified namespace architecture** where everything—blobs (artifacts) and workspaces (file collections)—is VFS-backed. Store ephemeral session files, persistent user projects, and shared resources with automatic access control, checkpoints, and a clean API that works the same for single files and entire directory trees.

## 🎯 Everything is VFS

The v0.9 architecture unifies blobs and workspaces under a single API:

- **Blobs** = Single-file VFS-backed namespaces (artifacts, documents, data)
- **Workspaces** = Multi-file VFS-backed namespaces (projects, collections, repos)
- **Same API** for both types (only the `type` parameter differs)
- **Same features** for both (checkpoints, scoping, VFS access, metadata)

### 60-Second Tour

```python
from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope

async with ArtifactStore() as store:
    # Create a blob (single file)
    blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION
    )
    await store.write_namespace(blob.namespace_id, data=b"Hello, World!")

    # Create a workspace (file tree)
    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="my-project",
        scope=StorageScope.USER,
        user_id="alice"
    )

    # Write files to workspace
    await store.write_namespace(workspace.namespace_id, path="/main.py", data=b"print('hello')")
    await store.write_namespace(workspace.namespace_id, path="/config.json", data=b'{"version": "1.0"}')

    # Get VFS for advanced operations (works for BOTH!)
    vfs = store.get_namespace_vfs(workspace.namespace_id)
    files = await vfs.ls("/")  # ['.workspace', 'main.py', 'config.json']

    # Create checkpoint (works for BOTH!)
    checkpoint = await store.checkpoint_namespace(workspace.namespace_id, name="v1.0")
```

**One API. Two types. Zero complexity.**

---

## 📦 CHUK Stack Integration

CHUK Artifacts is the **unified storage substrate for the entire CHUK AI stack**:

```
chuk-ai-planner  →  uses artifacts as workspaces for multi-step plans
chuk-mcp-server  →  exposes artifacts as remote filesystems via MCP
chuk-virtual-fs  →  underlying filesystem engine for all namespaces
chuk-sessions    →  session-based scope isolation for namespaces
```

**Why this matters:**
- **Consistent storage** across all CHUK components
- **Unified access patterns** for AI tools, planners, and MCP servers
- **Automatic isolation** prevents cross-session data leakage
- **Production-ready** from development to deployment

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Architecture](#architecture)
- [Install](#install)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
  - [Namespaces](#namespaces)
  - [Storage Scopes](#storage-scopes)
  - [Grid Architecture](#grid-architecture)
- [API Reference](#api-reference)
- [VFS Operations](#vfs-operations)
- [Examples](#examples)
- [Advanced Features](#advanced-features)
- [Legacy Compatibility](#legacy-compatibility)
- [Configuration](#configuration)
- [Testing](#testing)

---

## Why This Exists

Most platforms offer object storage (S3, filesystem)—but not a **unified namespace architecture** with **automatic access control**.

**CHUK Artifacts provides:**

- ✅ **Unified API** - Same code for single files (blobs) and file trees (workspaces)
- ✅ **Three storage scopes** - SESSION (ephemeral), USER (persistent), SANDBOX (shared)
- ✅ **VFS-backed** - Full filesystem operations on all namespaces
- ✅ **Checkpoints** - Snapshot and restore for both blobs and workspaces
- ✅ **Grid architecture** - Predictable, auditable storage organization
- ✅ **Access control** - Automatic scope-based isolation
- ✅ **Provider-agnostic** - Memory, Filesystem, SQLite, S3—same API
- ✅ **Async-first** - Built for FastAPI, MCP servers, modern Python

**Use cases:**
- 📝 AI chat applications (session artifacts + user documents)
- 🔧 MCP servers (tool workspaces + shared templates)
- 🚀 CI/CD systems (build artifacts + project workspaces)
- 📊 Data platforms (user datasets + shared libraries)

### Why not S3 / Filesystem / SQLite directly?

**What you get with raw storage:**
- S3 → objects (not namespaces)
- Filesystem → files (not isolated storage units)
- SQLite → durability (not structured filesystem trees)

**What CHUK Artifacts adds:**

| Feature | S3 Alone | Filesystem Alone | CHUK Artifacts |
|---------|----------|------------------|----------------|
| Namespace abstraction | ❌ | ❌ | ✅ |
| Scope-based isolation | ❌ | ❌ | ✅ |
| Unified API across backends | ❌ | ❌ | ✅ |
| Checkpoints/snapshots | ❌ | ❌ | ✅ |
| Grid path organization | Manual | Manual | Automatic |
| VFS operations | ❌ | Partial | ✅ Full |
| Session lifecycle | Manual | Manual | Automatic |

**CHUK Artifacts provides:**
- **VFS** + **scopes** + **namespaces** + **checkpoints** + **unified API** + **grid paths**

This is fundamentally more powerful than raw storage.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Application                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ create_namespace(type=BLOB|WORKSPACE)
                             │ write_namespace(), read_namespace()
                             │ checkpoint_namespace(), restore_namespace()
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ArtifactStore                             │
│                  (Unified Namespace Management)                  │
│                                                                   │
│  • Manages both BLOB and WORKSPACE namespaces                    │
│  • Enforces scope-based access control                           │
│  • Provides VFS access to all namespaces                         │
│  • Handles checkpoints and restoration                           │
└──────────┬────────────────────────────────────┬─────────────────┘
           │                                    │
           │ session management                 │ VFS operations
           ▼                                    ▼
   ┌────────────┐                   ┌─────────────────────────┐
   │  Sessions  │                   │    chuk-virtual-fs       │
   │  (Memory/  │                   │  (Unified VFS Layer)     │
   │   Redis)   │                   │                          │
   └────────────┘                   │  • ls(), mkdir(), rm()   │
                                    │  • cp(), mv(), find()    │
                                    │  • Metadata management   │
                                    │  • Batch operations      │
                                    └────────┬────────────────┘
                                             │
                                             │ provider calls
                                             ▼
                                ┌────────────────────────────┐
                                │   Storage Providers         │
                                │                             │
                                │ Memory │ Filesystem │ S3 │  │
                                │              SQLite         │
                                └─────────────┬───────────────┘
                                              │
                                              ▼
                              grid/{sandbox}/{scope}/{namespace_id}/
```

### Key Architectural Principles

1. **Everything is VFS** - Both blobs and workspaces are VFS-backed
2. **Unified API** - One set of methods for all namespace types
3. **Scope-based isolation** - SESSION, USER, and SANDBOX scopes
4. **Grid organization** - Predictable, auditable storage paths
5. **Provider-agnostic** - Swap storage backends via configuration

---

## Install

```bash
pip install chuk-artifacts
```

**Dependencies:**
- `chuk-virtual-fs` - VFS layer (automatically installed)
- `chuk-sessions` - Session management (automatically installed)

**Optional:**
- `redis` - For Redis session provider
- `boto3` - For S3 storage backend
- `ibm-cos-sdk` - For IBM Cloud Object Storage

---

## Quick Start

### 1. Create and Use a Blob Namespace

```python
from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope

store = ArtifactStore()

# Create a blob namespace (single file)
blob = await store.create_namespace(
    type=NamespaceType.BLOB,
    scope=StorageScope.SESSION
)

# Write data to the blob
await store.write_namespace(blob.namespace_id, data=b"My important data")

# Read data back
data = await store.read_namespace(blob.namespace_id)
print(data)  # b"My important data"
```

### 2. Create and Use a Workspace Namespace

```python
# Create a workspace namespace (file tree)
workspace = await store.create_namespace(
    type=NamespaceType.WORKSPACE,
    name="my-project",
    scope=StorageScope.USER,
    user_id="alice"
)

# Write multiple files
await store.write_namespace(workspace.namespace_id, path="/README.md", data=b"# My Project")
await store.write_namespace(workspace.namespace_id, path="/src/main.py", data=b"print('hello')")

# Get VFS for advanced operations
vfs = store.get_namespace_vfs(workspace.namespace_id)

# List files
files = await vfs.ls("/")  # ['.workspace', 'README.md', 'src']
src_files = await vfs.ls("/src")  # ['main.py']

# Copy files
await vfs.cp("/src/main.py", "/src/backup.py")

# Search for files
python_files = await vfs.find(pattern="*.py", path="/", recursive=True)
```

### 3. Use Checkpoints (Works for Both!)

```python
# Create a checkpoint
checkpoint = await store.checkpoint_namespace(
    workspace.namespace_id,
    name="initial-version",
    description="First working version"
)

# Make changes
await store.write_namespace(workspace.namespace_id, path="/README.md", data=b"# Updated")

# Restore from checkpoint
await store.restore_namespace(workspace.namespace_id, checkpoint.checkpoint_id)
```

---

## Core Concepts

### Namespaces

A **namespace** is a VFS-backed storage unit. There are two types:

| Type | Description | Use Cases |
|------|-------------|-----------|
| **BLOB** | Single file at `/_data` | Artifacts, documents, data files, caches |
| **WORKSPACE** | Full file tree | Projects, collections, code repos, datasets |

**Both types:**
- Use the same unified API
- Support checkpoints
- Have VFS access
- Support all three scopes

### Storage Scopes

Every namespace has a **scope** that determines its lifecycle and access:

| Scope | Lifecycle | Access | Grid Path | Use Cases |
|-------|-----------|--------|-----------|-----------|
| **SESSION** | Ephemeral (session lifetime) | Same session only | `grid/{sandbox}/sess-{session_id}/{ns_id}` | Temporary files, caches, current work |
| **USER** | Persistent | Same user only | `grid/{sandbox}/user-{user_id}/{ns_id}` | User projects, personal docs, settings |
| **SANDBOX** | Persistent | All users | `grid/{sandbox}/shared/{ns_id}` | Templates, shared libraries, documentation |

**Example:**

```python
# Session-scoped (ephemeral)
temp_blob = await store.create_namespace(
    type=NamespaceType.BLOB,
    scope=StorageScope.SESSION
)

# User-scoped (persistent)
user_project = await store.create_namespace(
    type=NamespaceType.WORKSPACE,
    name="my-docs",
    scope=StorageScope.USER,
    user_id="alice"
)

# Sandbox-scoped (shared)
shared_templates = await store.create_namespace(
    type=NamespaceType.WORKSPACE,
    name="templates",
    scope=StorageScope.SANDBOX
)
```

### Grid Architecture

All namespaces are organized in a **grid** structure:

```
grid/
├── {sandbox_id}/
│   ├── sess-{session_id}/          # SESSION scope
│   │   ├── {namespace_id}/         # Blob or workspace
│   │   │   ├── _data               # For blobs
│   │   │   ├── _meta.json          # For blobs
│   │   │   ├── file1.txt           # For workspaces
│   │   │   └── ...
│   ├── user-{user_id}/             # USER scope
│   │   └── {namespace_id}/
│   └── shared/                     # SANDBOX scope
│       └── {namespace_id}/
```

**Benefits:**
- Predictable paths
- Easy auditing
- Clear isolation
- Efficient listing

### Features Matrix

Everything works for both namespace types across all scopes:

| Feature | BLOB | WORKSPACE | SESSION | USER | SANDBOX |
|---------|------|-----------|---------|------|---------|
| VFS access | ✅ | ✅ | ✅ | ✅ | ✅ |
| Checkpoints/restore | ✅ | ✅ | ✅ | ✅ | ✅ |
| Metadata (custom) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Batch operations | ✅ | ✅ | ✅ | ✅ | ✅ |
| Search/find | ✅ | ✅ | ✅ | ✅ | ✅ |
| Grid placement | Auto | Auto | Auto | Auto | Auto |
| Access control | Auto | Auto | Auto | Auto | Auto |
| TTL expiration | ✅ | ✅ | ✅ | ❌ | ❌ |

**Key insight:** The unified architecture means you get **full feature parity** regardless of namespace type or scope.

---

## API Reference

### Core Namespace Operations

```python
# Create namespace
namespace = await store.create_namespace(
    type: NamespaceType,              # BLOB or WORKSPACE
    scope: StorageScope,               # SESSION, USER, or SANDBOX
    name: str | None = None,           # Optional name (workspaces only)
    user_id: str | None = None,        # Required for USER scope
    ttl_hours: int | None = None,      # Session TTL (SESSION scope only)
    provider_type: str = "vfs-memory", # VFS provider
    provider_config: dict | None = None # Provider configuration
) -> NamespaceInfo

# Write data
await store.write_namespace(
    namespace_id: str,
    data: bytes,
    path: str | None = None  # Required for workspaces, optional for blobs
)

# Read data
data: bytes = await store.read_namespace(
    namespace_id: str,
    path: str | None = None  # Required for workspaces, optional for blobs
)

# Get VFS access
vfs: AsyncVirtualFileSystem = store.get_namespace_vfs(namespace_id: str)

# List namespaces
namespaces: list[NamespaceInfo] = store.list_namespaces(
    session_id: str | None = None,
    user_id: str | None = None,
    type: NamespaceType | None = None
)

# Destroy namespace
await store.destroy_namespace(namespace_id: str)
```

### Checkpoint Operations

```python
# Create checkpoint
checkpoint: CheckpointInfo = await store.checkpoint_namespace(
    namespace_id: str,
    name: str,
    description: str | None = None
)

# List checkpoints
checkpoints: list[CheckpointInfo] = await store.list_checkpoints(
    namespace_id: str
)

# Restore from checkpoint
await store.restore_namespace(
    namespace_id: str,
    checkpoint_id: str
)

# Delete checkpoint
await store.delete_checkpoint(
    namespace_id: str,
    checkpoint_id: str
)
```

---

## VFS Operations

All namespaces provide full VFS access:

```python
vfs = store.get_namespace_vfs(namespace_id)

# File operations
await vfs.write_file(path, data)
data = await vfs.read_file(path)
await vfs.rm(path)
await vfs.cp(src, dst)
await vfs.mv(src, dst)
exists = await vfs.exists(path)

# Directory operations
await vfs.mkdir(path)
await vfs.rmdir(path)
await vfs.cd(path)
files = await vfs.ls(path)
is_dir = await vfs.is_dir(path)
is_file = await vfs.is_file(path)

# Metadata
await vfs.set_metadata(path, metadata)
metadata = await vfs.get_metadata(path)
node_info = await vfs.get_node_info(path)

# Search
results = await vfs.find(pattern="*.py", path="/", recursive=True)

# Batch operations
await vfs.batch_create_files(file_specs)
data_dict = await vfs.batch_read_files(paths)
await vfs.batch_write_files(file_data)
await vfs.batch_delete_paths(paths)

# Text/Binary
await vfs.write_text(path, text, encoding="utf-8")
text = await vfs.read_text(path, encoding="utf-8")
await vfs.write_binary(path, data)
data = await vfs.read_binary(path)

# Stats
stats = await vfs.get_storage_stats()
provider = await vfs.get_provider_name()
```

See [examples/05_advanced_vfs_features.py](examples/05_advanced_vfs_features.py) for comprehensive VFS examples.

---

## Examples

We provide **9 comprehensive examples** covering all features:

1. **[00_quick_start.py](examples/00_quick_start.py)** - Quick introduction to unified API
2. **[01_blob_namespace_basics.py](examples/01_blob_namespace_basics.py)** - Blob operations
3. **[02_workspace_namespace_basics.py](examples/02_workspace_namespace_basics.py)** - Workspace operations
4. **[03_unified_everything_is_vfs.py](examples/03_unified_everything_is_vfs.py)** - Unified architecture
5. **[04_legacy_api_compatibility.py](examples/04_legacy_api_compatibility.py)** - Legacy compatibility
6. **[05_advanced_vfs_features.py](examples/05_advanced_vfs_features.py)** - Advanced VFS features
7. **[06_session_isolation.py](examples/06_session_isolation.py)** - Session isolation and scoping
8. **[07_large_files_streaming.py](examples/07_large_files_streaming.py)** - Large file handling
9. **[08_batch_operations.py](examples/08_batch_operations.py)** - Batch operations

Run any example:

```bash
python examples/00_quick_start.py
python examples/02_workspace_namespace_basics.py
python examples/05_advanced_vfs_features.py
```

See [examples/README.md](examples/README.md) for complete documentation.

---

## Advanced Features

### Checkpoints

Create snapshots of any namespace (blob or workspace):

```python
# Create checkpoint
cp1 = await store.checkpoint_namespace(workspace.namespace_id, name="v1.0")

# Make changes...
await store.write_namespace(workspace.namespace_id, path="/new_file.txt", data=b"new")

# Restore to checkpoint
await store.restore_namespace(workspace.namespace_id, cp1.checkpoint_id)
```

### Batch Operations

Process multiple files efficiently:

```python
vfs = store.get_namespace_vfs(workspace.namespace_id)

# Batch create with metadata
file_specs = [
    {"path": "/file1.txt", "content": b"data1", "metadata": {"tag": "important"}},
    {"path": "/file2.txt", "content": b"data2", "metadata": {"tag": "draft"}},
]
await vfs.batch_create_files(file_specs)

# Batch read
data = await vfs.batch_read_files(["/file1.txt", "/file2.txt"])

# Batch delete
await vfs.batch_delete_paths(["/file1.txt", "/file2.txt"])
```

### Metadata Management

Attach rich metadata to files:

```python
await vfs.set_metadata("/document.pdf", {
    "author": "Alice",
    "tags": ["important", "reviewed"],
    "custom": {"project_id": 123}
})

metadata = await vfs.get_metadata("/document.pdf")
```

### Search and Find

Find files by pattern:

```python
# Find all Python files
py_files = await vfs.find(pattern="*.py", path="/", recursive=True)

# Find specific file
results = await vfs.find(pattern="config.json", path="/")
```

---

## Legacy Compatibility

The legacy `store()` and `retrieve()` APIs still work:

```python
# Legacy API (still supported)
artifact_id = await store.store(
    b"data",
    mime="text/plain",
    summary="My artifact"
)
data = await store.retrieve(artifact_id)

# But unified API is recommended for new code
blob = await store.create_namespace(type=NamespaceType.BLOB)
await store.write_namespace(blob.namespace_id, data=b"data")
data = await store.read_namespace(blob.namespace_id)
```

See [examples/04_legacy_api_compatibility.py](examples/04_legacy_api_compatibility.py) for details.

---

## Configuration

### 🏭 Production Deployment Patterns

Choose the right storage backend for your use case:

**Development / Testing:**
```python
# Memory provider - instant, ephemeral
store = ArtifactStore()  # Uses vfs-memory by default
```

**Small Deployments / Edge:**
```python
# Filesystem provider with container volumes
export ARTIFACT_PROVIDER=vfs-filesystem
export VFS_ROOT_PATH=/data/artifacts

# Good for: Docker containers, edge devices, local-first apps
```

**Portable / Embedded:**
```python
# SQLite provider - single file, queryable
export ARTIFACT_PROVIDER=vfs-sqlite
export SQLITE_DB_PATH=/data/artifacts.db

# Good for: Desktop apps, portable storage, offline-first
```

**Production / Cloud:**
```python
# S3 provider with Redis standalone
export ARTIFACT_PROVIDER=vfs-s3
export SESSION_PROVIDER=redis
export AWS_S3_BUCKET=my-artifacts
export SESSION_REDIS_URL=redis://prod-redis:6379/0

# Good for: Multi-tenant SaaS, distributed systems, high scale
```

**High-Availability Production:**
```python
# S3 provider with Redis Cluster
export ARTIFACT_PROVIDER=vfs-s3
export SESSION_PROVIDER=redis
export AWS_S3_BUCKET=my-artifacts
export SESSION_REDIS_URL=redis://node1:7000,node2:7001,node3:7002

# Good for: Mission-critical systems, zero-downtime requirements, large scale
```

**Hybrid Deployments:**
```python
# Different scopes, different backends
# - SESSION: vfs-memory (ephemeral, fast)
# - USER: vfs-filesystem (persistent, local)
# - SANDBOX: vfs-s3 (persistent, shared, cloud)

# Configure per namespace:
await store.create_namespace(
    type=NamespaceType.BLOB,
    scope=StorageScope.SESSION,
    provider_type="vfs-memory"  # Fast ephemeral
)

await store.create_namespace(
    type=NamespaceType.WORKSPACE,
    scope=StorageScope.USER,
    provider_type="vfs-s3"  # Persistent cloud
)
```

### Storage Providers

Configure via environment variables:

```bash
# Memory (default, for development)
export ARTIFACT_PROVIDER=vfs-memory

# Filesystem (for local persistence)
export ARTIFACT_PROVIDER=vfs-filesystem

# SQLite (for portable database)
export ARTIFACT_PROVIDER=vfs-sqlite

# S3 (for production)
export ARTIFACT_PROVIDER=vfs-s3
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Session Providers

```bash
# Memory (default)
export SESSION_PROVIDER=memory

# Redis Standalone (for production)
export SESSION_PROVIDER=redis
export SESSION_REDIS_URL=redis://localhost:6379/0

# Redis Cluster (for high-availability production - auto-detected)
export SESSION_PROVIDER=redis
export SESSION_REDIS_URL=redis://node1:7000,node2:7001,node3:7002

# Redis with TLS
export SESSION_REDIS_URL=rediss://localhost:6380/0
export REDIS_TLS_INSECURE=1  # Set to 1 to skip cert verification (dev only)
```

**Redis Cluster Support** (chuk-sessions ≥0.5.0):
- Automatically detected from comma-separated URL format
- High availability with automatic failover
- Horizontal scaling across multiple nodes
- Production-ready with proper error handling

### Programmatic Configuration

```python
from chuk_artifacts.config import configure_memory, configure_s3, configure_redis_session

# Development
config = configure_memory()
store = ArtifactStore(**config)

# Production with S3 and Redis standalone
config = configure_s3(
    bucket="my-artifacts",
    region="us-east-1",
    session_provider="redis"
)
configure_redis_session("redis://localhost:6379/0")
store = ArtifactStore(**config)

# Production with S3 and Redis Cluster
config = configure_s3(
    bucket="my-artifacts",
    region="us-east-1",
    session_provider="redis"
)
configure_redis_session("redis://node1:7000,node2:7001,node3:7002")
store = ArtifactStore(**config)
```

---

## ⚡ Performance

CHUK Artifacts is designed for production performance:

**Memory Provider:**
- Nanosecond to microsecond operations
- Zero I/O overhead
- Perfect for testing and development

**Filesystem Provider:**
- Depends on OS filesystem (typically microseconds to milliseconds)
- Uses async I/O for non-blocking operations
- Good for local deployments

**S3 Provider:**
- Uses streaming + zero-copy writes
- Parallel uploads for large files
- Production-proven at scale

**SQLite Provider:**
- Fast for small to medium workspaces
- Queryable storage with indexes
- Good for embedded/desktop apps

**Checkpoints:**
- Use copy-on-write semantics where supported
- Snapshot-based for minimal overhead
- Incremental when possible

**VFS Layer:**
- Batch operations reduce round trips
- Streaming for large files (no memory buffering)
- Provider-specific optimizations

**Benchmarks** (from examples):
- Batch operations: **1.7x faster** than individual operations
- Large file writes: **577 MB/s** (memory provider)
- Large file reads: **1103 MB/s** (memory provider)
- Batch dataset creation: **250+ files/sec**

See [examples/08_batch_operations.py](examples/08_batch_operations.py) and [examples/07_large_files_streaming.py](examples/07_large_files_streaming.py) for detailed benchmarks.

---

## Testing

CHUK Artifacts includes 778 passing tests with 92% coverage:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=chuk_artifacts --cov-report=html

# Run specific test file
pytest tests/test_namespace.py -v
```

**Memory provider** makes testing instant:

```python
import pytest
from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope

@pytest.mark.asyncio
async def test_my_feature():
    store = ArtifactStore()  # Uses memory provider by default

    blob = await store.create_namespace(
        type=NamespaceType.BLOB,
        scope=StorageScope.SESSION
    )

    await store.write_namespace(blob.namespace_id, data=b"test")
    data = await store.read_namespace(blob.namespace_id)

    assert data == b"test"
```

---

## Documentation

- **[Examples](examples/README.md)** - 9 comprehensive examples
- **[VFS API Reference](examples/VFS_API_REFERENCE.md)** - Quick VFS API guide

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Run linters (`make check`)
6. Submit a pull request

---

## Support

- **Issues**: [GitHub Issues](https://github.com/chrishayuk/chuk-artifacts/issues)
- **Documentation**: [examples/](examples/)
- **Discussions**: [GitHub Discussions](https://github.com/chrishayuk/chuk-artifacts/discussions)

---

**Built with ❤️ for AI applications and MCP servers**
