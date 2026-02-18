# chuk-artifacts Examples

This directory contains comprehensive examples demonstrating the unified "everything is VFS" architecture in chuk-artifacts v1.0.

## Overview

chuk-artifacts v1.0 introduces a unified namespace architecture where **everything is VFS**:
- **Blobs** (artifacts) are single-file VFS-backed namespaces
- **Workspaces** are multi-file VFS-backed namespaces
- Both use the same API, grid architecture, and session management

## Running Examples

All examples are standalone Python scripts. Run them with:

```bash
# Install chuk-artifacts first
pip install chuk-artifacts

# Run any example (in order recommended)
python examples/00_quick_start.py
python examples/01_blob_namespace_basics.py
python examples/02_workspace_namespace_basics.py
python examples/03_unified_everything_is_vfs.py
python examples/04_legacy_api_compatibility.py
python examples/05_advanced_vfs_features.py
```

## Example Scripts

### 00_quick_start.py

**What it demonstrates:**
- Quick introduction to the unified namespace API
- Both BLOB and WORKSPACE creation in one simple example
- Checkpoints for both types
- The "everything is VFS" philosophy

**Key concepts:**
- Fastest way to understand the unified API
- Shows the simplicity of the architecture
- Perfect starting point for new users

**Run:**
```bash
python examples/00_quick_start.py
```

### 01_blob_namespace_basics.py

**What it demonstrates:**
- Creating blob namespaces (single-file storage)
- Writing and reading data
- Direct VFS access to blobs
- Session-scoped vs user-scoped blobs
- Creating and restoring checkpoints
- Listing and destroying namespaces

**Key concepts:**
- Blobs store data at `/_data` within VFS
- Metadata at `/_meta.json`
- Perfect for artifacts, caching, temporary storage

**Run:**
```bash
python examples/01_blob_namespace_basics.py
```

### 02_workspace_namespace_basics.py

**What it demonstrates:**
- Creating workspace namespaces (multi-file storage)
- Writing and reading multiple files
- Directory operations (create, list, navigate)
- Direct VFS access for advanced operations
- Checkpoints for entire workspace state
- User-scoped persistent workspaces

**Key concepts:**
- Workspaces are full directory trees
- Support all VFS operations (copy, move, delete, stat)
- Perfect for projects, file collections, code repos

**Run:**
```bash
python examples/02_workspace_namespace_basics.py
```

### 03_unified_everything_is_vfs.py

**What it demonstrates:**
- How blobs and workspaces share the same API
- Unified grid architecture for both types
- Same VFS access methods
- Same checkpoint system
- Same scoping (SESSION, USER, SANDBOX)
- Unified listing and management

**Key concepts:**
- ONE API to rule them all
- `create_namespace(type=BLOB|WORKSPACE)`
- Everything else is identical
- Only difference: BLOB=single file, WORKSPACE=file tree

**Run:**
```bash
python examples/03_unified_everything_is_vfs.py
```

### 04_legacy_api_compatibility.py

**What it demonstrates:**
- Legacy `store()` and `retrieve()` still work
- How legacy API maps to unified architecture
- Interoperability between legacy and unified APIs
- Migration path from old to new API
- Backward compatibility guarantees

**Key concepts:**
- `artifact_id == namespace_id`
- Legacy code keeps working
- Can mix legacy and unified APIs
- Gradual migration supported

**Run:**
```bash
python examples/04_legacy_api_compatibility.py
```

### 05_advanced_vfs_features.py

**What it demonstrates:**
- Comprehensive VFS functionality (works for both blobs and workspaces!)
- Batch operations (create, read, write, delete)
- Metadata management (set, get, node info)
- Directory operations (cd, mkdir, rmdir, is_dir, is_file)
- Text vs binary operations (write_text, read_text, write_binary, read_binary)
- Touch and file checks (touch, exists, custom metadata)
- Search and find (pattern matching, recursive search)
- Storage stats (get_storage_stats, get_provider_name)
- Advanced file operations (cp, mv, rm)

**Key concepts:**
- ALL VFS features work for both BLOB and WORKSPACE namespaces
- Batch operations for efficiency
- Rich metadata support (custom_meta, tags, checksums, TTL)
- Powerful search capabilities
- Text and binary handling

**Run:**
```bash
python examples/05_advanced_vfs_features.py
```

## Quick Reference

### Unified API (New Code)

```python
from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope

store = ArtifactStore()

# Create blob namespace
blob_ns = await store.create_namespace(
    type=NamespaceType.BLOB,
    scope=StorageScope.SESSION
)

# Write to blob
await store.write_namespace(blob_ns.namespace_id, data=b"content")

# Read from blob
data = await store.read_namespace(blob_ns.namespace_id)

# Create workspace namespace
workspace_ns = await store.create_namespace(
    type=NamespaceType.WORKSPACE,
    name="my-project",
    scope=StorageScope.USER,
    user_id="alice"
)

# Write files to workspace
await store.write_namespace(workspace_ns.namespace_id, path="/main.py", data=b"code")

# Get VFS for advanced operations
vfs = store.get_namespace_vfs(workspace_ns.namespace_id)
await vfs.list_directory("/")

# Checkpoint (works for both!)
checkpoint = await store.checkpoint_namespace(
    workspace_ns.namespace_id,
    name="v1.0",
    description="Initial release"
)

# Restore
await store.restore_namespace(workspace_ns.namespace_id, checkpoint.checkpoint_id)
```

### Legacy API (Backward Compatible)

```python
from chuk_artifacts import ArtifactStore, StorageScope

store = ArtifactStore()

# OLD API (still works!)
artifact_id = await store.store(
    data=b"content",
    mime="text/plain",
    summary="My artifact"
)

data = await store.retrieve(artifact_id)

# Interoperable with unified API
vfs = store.get_namespace_vfs(artifact_id)  # Works!
await store.checkpoint_namespace(artifact_id, name="v1")  # Works!
```

## Storage Scopes

All examples demonstrate different storage scopes:

| Scope | Lifecycle | Use Case | Example |
|-------|-----------|----------|---------|
| **SESSION** | Ephemeral (expires with session) | Temporary data, caches | Session-scoped blob for temp storage |
| **USER** | Persistent (tied to user) | User's personal data | Alice's project workspace |
| **SANDBOX** | Shared (sandbox-wide) | Shared libraries, templates | Shared documentation blob |

## VFS Providers

Examples use `vfs-memory` for simplicity, but all providers work:

```python
# Memory (fast, ephemeral)
provider_type="vfs-memory"

# Filesystem (persistent)
provider_type="vfs-filesystem"

# SQLite (portable, single-file)
provider_type="vfs-sqlite"

# S3 (cloud, scalable)
provider_type="vfs-s3"
```

## Grid Architecture

All examples use the same grid structure:

```
grid/
├── {sandbox_id}/
│   ├── {session_id}/           # SESSION scope
│   │   ├── {namespace_id}/     # Blob or workspace
│   │   │   ├── _data           # For blobs
│   │   │   ├── _meta.json      # For blobs
│   │   │   ├── main.py         # For workspaces
│   │   │   └── ...
│   ├── user-{user_id}/         # USER scope
│   │   └── {namespace_id}/
│   └── shared/                 # SANDBOX scope
│       └── {namespace_id}/
```

## Next Steps

After running these examples:

1. **Integrate with chuk-mcp-server** - Use artifacts in your MCP tools
2. **Explore VFS providers** - Try filesystem, SQLite, or S3 backends
3. **Build real applications** - Use namespaces for your projects
4. **Contribute examples** - Share your use cases!

## Archive

Older demonstration scripts from development are available in the `archive/` directory. These are not maintained and may not work with the current version. Always prefer the numbered examples (00-05) above.

## Resources

- [VFS_API_REFERENCE.md](VFS_API_REFERENCE.md) - Quick VFS API reference
- [UNIFIED_VFS_DESIGN.md](../UNIFIED_VFS_DESIGN.md) - Architecture design document
- [IMPLEMENTATION_SUMMARY.md](../IMPLEMENTATION_SUMMARY.md) - Implementation details
- [chuk-artifacts README](../README.md) - Main package documentation
- [chuk-virtual-fs](https://github.com/your-org/chuk-virtual-fs) - VFS engine documentation

## Support

Questions or issues?
- File an issue: https://github.com/your-org/chuk-artifacts/issues
- Discussions: https://github.com/your-org/chuk-artifacts/discussions

## License

Apache 2.0 - See [LICENSE](../LICENSE) for details
