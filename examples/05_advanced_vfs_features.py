#!/usr/bin/env python3
"""
Example 5: Advanced VFS Features

This example demonstrates advanced VFS functionality available in all namespaces:
- Batch operations (create, read, write, delete)
- Metadata management
- Directory operations (cd, rmdir, is_dir, is_file)
- File search and find
- Text/binary operations
- Touch and stat operations
- Storage stats

Everything shown here works for BOTH blob and workspace namespaces!
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    store = ArtifactStore()

    print("=" * 70)
    print("ADVANCED VFS FEATURES")
    print("=" * 70)

    # Create a workspace for demonstrations
    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="advanced-demo",
        scope=StorageScope.SESSION,
    )

    vfs = store.get_namespace_vfs(workspace.namespace_id)

    # ========================================================================
    # Part 1: Batch Operations
    # ========================================================================
    print("\n📦 PART 1: BATCH OPERATIONS")
    print("-" * 70)

    # Batch create files (creates nodes + writes content)
    file_specs = [
        {"path": "/batch1.txt", "content": b"First batch file"},
        {"path": "/batch2.txt", "content": b"Second batch file"},
        {"path": "/batch3.txt", "content": b"Third batch file"},
    ]
    await vfs.batch_create_files(file_specs)
    print(f"✓ Batch created {len(file_specs)} files")

    # Batch read files
    paths = ["/batch1.txt", "/batch2.txt", "/batch3.txt"]
    batch_data = await vfs.batch_read_files(paths)
    print(f"✓ Batch read {len(batch_data)} files:")
    for path, data in batch_data.items():
        print(f"  - {path}: {data.decode()}")

    # Batch write files (updates existing files)
    update_data = {
        "/batch1.txt": b"Updated first file",
        "/batch2.txt": b"Updated second file",
    }
    await vfs.batch_write_files(update_data)
    print(f"✓ Batch updated {len(update_data)} files")

    # Batch delete
    await vfs.batch_delete_paths(["/batch1.txt", "/batch2.txt"])
    print("✓ Batch deleted 2 files")

    remaining = await vfs.ls("/")
    print(f"✓ Remaining files: {remaining}")

    # ========================================================================
    # Part 2: Metadata Management
    # ========================================================================
    print("\n🏷️  PART 2: METADATA MANAGEMENT")
    print("-" * 70)

    # Write file with metadata
    await vfs.write_file("/meta_test.txt", b"File with metadata")

    # Set metadata
    metadata = {
        "author": "Alice",
        "version": "1.0",
        "tags": ["important", "demo"],
        "custom": {"key": "value"},
    }
    await vfs.set_metadata("/meta_test.txt", metadata)
    print("✓ Set metadata on /meta_test.txt")

    # Get metadata
    retrieved_meta = await vfs.get_metadata("/meta_test.txt")
    print("✓ Retrieved metadata:")
    print(f"  Author: {retrieved_meta.get('author')}")
    print(f"  Version: {retrieved_meta.get('version')}")
    print(f"  Tags: {retrieved_meta.get('tags')}")

    # Get full node info (includes metadata + stats)
    node_info = await vfs.get_node_info("/meta_test.txt")
    print("\n✓ Node info:")
    print(f"  Size: {node_info.size} bytes")
    print(f"  Is directory: {node_info.is_dir}")
    print(f"  Created: {node_info.created_at}")
    print(f"  MIME type: {node_info.mime_type}")

    # ========================================================================
    # Part 3: Directory Operations
    # ========================================================================
    print("\n📁 PART 3: DIRECTORY OPERATIONS")
    print("-" * 70)

    # Create nested directories
    await vfs.mkdir("/level1")
    await vfs.mkdir("/level1/level2")
    await vfs.mkdir("/level1/level2/level3")
    print("✓ Created nested directory structure")

    # Change directory
    await vfs.cd("/level1/level2")
    print("✓ Changed directory to /level1/level2")

    # Create file in current directory
    await vfs.write_file("file_in_level2.txt", b"Content")
    print("✓ Created file in current directory")

    # Check if directory/file
    is_dir = await vfs.is_dir("/level1")
    is_file = await vfs.is_file("/level1/level2/file_in_level2.txt")
    print(f"\n✓ /level1 is directory: {is_dir}")
    print(f"✓ file_in_level2.txt is file: {is_file}")

    # Remove directory
    await vfs.rmdir("/level1/level2/level3")
    print("✓ Removed /level1/level2/level3 directory")

    # ========================================================================
    # Part 4: Text vs Binary Operations
    # ========================================================================
    print("\n📝 PART 4: TEXT VS BINARY OPERATIONS")
    print("-" * 70)

    # Write text file
    await vfs.write_text(
        "/text_file.txt", "Hello, World!\nThis is text.", encoding="utf-8"
    )
    print("✓ Wrote text file with write_text()")

    # Read as text
    text_content = await vfs.read_text("/text_file.txt", encoding="utf-8")
    print(f"✓ Read as text: {repr(text_content)}")

    # Write binary file
    binary_data = bytes([0x89, 0x50, 0x4E, 0x47])  # PNG header
    await vfs.write_binary("/binary_file.bin", binary_data)
    print(f"\n✓ Wrote binary file ({len(binary_data)} bytes)")

    # Read as binary
    binary_content = await vfs.read_binary("/binary_file.bin")
    print(f"✓ Read as binary: {binary_content.hex()}")

    # Generic read_file (auto-detects)
    generic_text = await vfs.read_file("/text_file.txt", as_text=True)
    generic_binary = await vfs.read_file("/binary_file.bin", as_text=False)
    print(f"\n✓ Generic read (text): {type(generic_text).__name__}")
    print(f"✓ Generic read (binary): {type(generic_binary).__name__}")

    # ========================================================================
    # Part 5: Touch and File Checks
    # ========================================================================
    print("\n👆 PART 5: TOUCH AND FILE CHECKS")
    print("-" * 70)

    # Touch creates empty file or updates timestamp
    await vfs.touch("/touched.txt")
    print("✓ Touched /touched.txt (created empty file)")

    # Check existence
    exists = await vfs.exists("/touched.txt")
    print(f"✓ /touched.txt exists: {exists}")

    # Touch with custom metadata (use custom_meta dict)
    await vfs.touch(
        "/meta_touch.txt", custom_meta={"project": "demo", "status": "active"}
    )
    node_info2 = await vfs.get_node_info("/meta_touch.txt")
    print(f"✓ Touched with custom metadata: {node_info2.custom_meta}")

    # ========================================================================
    # Part 6: Search and Find
    # ========================================================================
    print("\n🔍 PART 6: SEARCH AND FIND")
    print("-" * 70)

    # Create test files for searching
    await vfs.mkdir("/search_test")
    await vfs.write_file("/search_test/file1.txt", b"content one")
    await vfs.write_file("/search_test/file2.log", b"content two")
    await vfs.write_file("/search_test/file3.txt", b"content three")
    await vfs.mkdir("/search_test/subdir")
    await vfs.write_file("/search_test/subdir/file4.txt", b"content four")

    # Find files by pattern
    txt_files = await vfs.find(pattern="*.txt", path="/search_test")
    print(f"\n✓ Found .txt files: {txt_files}")

    # Find by name
    file1_results = await vfs.find(pattern="file1.txt", path="/search_test")
    print(f"✓ Found file1.txt: {file1_results}")

    # Find all files recursively
    all_files = await vfs.find(pattern="*", path="/search_test", recursive=True)
    print(f"✓ Found all files: {all_files}")

    # ========================================================================
    # Part 7: Storage Stats
    # ========================================================================
    print("\n📊 PART 7: STORAGE STATS")
    print("-" * 70)

    # Get storage statistics
    stats = await vfs.get_storage_stats()
    print("\n✓ Storage statistics:")
    print(f"  Total files: {stats.get('total_files', 'N/A')}")
    print(f"  Total size: {stats.get('total_size', 'N/A')} bytes")
    print(f"  Provider: {await vfs.get_provider_name()}")

    # ========================================================================
    # Part 8: Advanced File Operations
    # ========================================================================
    print("\n⚙️  PART 8: ADVANCED FILE OPERATIONS")
    print("-" * 70)

    # Create test structure
    await vfs.write_file("/source.txt", b"Source content")

    # Copy preserves original
    await vfs.cp("/source.txt", "/copy.txt")
    print("✓ Copied /source.txt to /copy.txt")

    # Move removes original
    await vfs.mv("/copy.txt", "/moved.txt")
    print("✓ Moved /copy.txt to /moved.txt")

    # Verify
    source_exists = await vfs.exists("/source.txt")
    copy_exists = await vfs.exists("/copy.txt")
    moved_exists = await vfs.exists("/moved.txt")

    print(f"\n✓ /source.txt exists: {source_exists}")
    print(f"✓ /copy.txt exists: {copy_exists}")
    print(f"✓ /moved.txt exists: {moved_exists}")

    # ========================================================================
    # Part 9: Batch Create with Specs
    # ========================================================================
    print("\n🚀 PART 9: BATCH CREATE WITH SPECS")
    print("-" * 70)

    # Batch create files with full specifications
    file_specs = [
        {
            "path": "/batch_spec1.txt",
            "content": b"Spec file 1",
            "metadata": {"type": "spec", "index": 1},
        },
        {
            "path": "/batch_spec2.txt",
            "content": b"Spec file 2",
            "metadata": {"type": "spec", "index": 2},
        },
        {
            "path": "/batch_spec3.txt",
            "content": b"Spec file 3",
            "metadata": {"type": "spec", "index": 3},
        },
    ]

    await vfs.batch_create_files(file_specs)
    print(f"✓ Batch created {len(file_specs)} files with metadata")

    # Verify metadata was set
    spec1_meta = await vfs.get_metadata("/batch_spec1.txt")
    print(f"✓ Batch spec1 metadata: {spec1_meta}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ ADVANCED VFS FEATURES - SUMMARY")
    print("=" * 70)

    print("""
  BATCH OPERATIONS:
    ✓ batch_write_files() - Write multiple files at once
    ✓ batch_read_files() - Read multiple files at once
    ✓ batch_create_files() - Create with metadata specs
    ✓ batch_delete_paths() - Delete multiple paths

  METADATA:
    ✓ set_metadata() - Attach custom metadata
    ✓ get_metadata() - Retrieve metadata
    ✓ get_node_info() - Full file/directory info

  DIRECTORY OPERATIONS:
    ✓ mkdir() / rmdir() - Create/remove directories
    ✓ cd() - Change current directory
    ✓ is_dir() / is_file() - Type checking

  TEXT & BINARY:
    ✓ write_text() / read_text() - Text operations
    ✓ write_binary() / read_binary() - Binary operations
    ✓ read_file(as_text=True/False) - Generic read

  FILE OPERATIONS:
    ✓ touch() - Create/update file
    ✓ exists() - Check existence
    ✓ cp() / mv() / rm() - Copy/move/delete

  SEARCH:
    ✓ find(pattern=, path=, recursive=) - Find files by pattern

  STATS:
    ✓ get_storage_stats() - Storage metrics
    ✓ get_provider_name() - Provider info

  ALL WORK FOR BOTH BLOB AND WORKSPACE NAMESPACES!
    """)

    # Cleanup
    print("\n🧹 Cleaning up...")
    await store.destroy_namespace(workspace.namespace_id)
    print("✓ Cleaned up workspace")

    print("\n" + "=" * 70)
    print("✓ ADVANCED VFS FEATURES DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
