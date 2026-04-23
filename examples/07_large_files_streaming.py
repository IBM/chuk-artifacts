#!/usr/bin/env python3
"""
Example 7: Large Files and Streaming

This example demonstrates efficient handling of large files:
- Writing large files to namespaces
- Reading large files efficiently
- Chunked processing for memory efficiency
- Progress tracking
- Binary vs text handling for large files
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")
import time

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    store = ArtifactStore()

    print("=" * 70)
    print("LARGE FILES AND STREAMING")
    print("=" * 70)

    # ========================================================================
    # Part 1: Writing Large Files
    # ========================================================================
    print("\n📤 PART 1: WRITING LARGE FILES")
    print("-" * 70)

    # Create a workspace for large file demonstration
    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="large-files-demo",
        scope=StorageScope.SESSION,
    )

    vfs = store.get_namespace_vfs(workspace.namespace_id)

    # Generate a large file (10MB)
    chunk_size = 1024 * 1024  # 1MB chunks
    num_chunks = 10
    total_size = chunk_size * num_chunks

    print(f"\n✓ Creating {total_size / 1024 / 1024:.1f} MB test file")
    print(f"  Chunk size: {chunk_size / 1024:.0f} KB")
    print(f"  Number of chunks: {num_chunks}")

    # Write large file in chunks (memory efficient)
    start_time = time.time()
    large_data = bytearray()

    for i in range(num_chunks):
        # Generate chunk data
        chunk = f"Chunk {i:02d}: ".encode() + b"x" * (chunk_size - 20)
        large_data.extend(chunk)

        # Show progress
        progress = (i + 1) / num_chunks * 100
        print(f"  Generating... {progress:.0f}%", end="\r")

    print("  Generating... 100% ✓")

    # Write the large file
    write_start = time.time()
    await vfs.write_binary("/large_file.bin", bytes(large_data))
    write_time = time.time() - write_start

    total_time = time.time() - start_time

    print("\n✓ Wrote large file:")
    print(f"  Size: {len(large_data) / 1024 / 1024:.1f} MB")
    print(f"  Write time: {write_time:.2f}s")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Throughput: {len(large_data) / 1024 / 1024 / write_time:.1f} MB/s")

    # ========================================================================
    # Part 2: Reading Large Files
    # ========================================================================
    print("\n📥 PART 2: READING LARGE FILES")
    print("-" * 70)

    # Read the large file
    read_start = time.time()
    read_data = await vfs.read_binary("/large_file.bin")
    read_time = time.time() - read_start

    print("\n✓ Read large file:")
    print(f"  Size: {len(read_data) / 1024 / 1024:.1f} MB")
    print(f"  Read time: {read_time:.2f}s")
    print(f"  Throughput: {len(read_data) / 1024 / 1024 / read_time:.1f} MB/s")
    print(f"  Data integrity: {read_data == large_data}")

    # ========================================================================
    # Part 3: Chunked Processing (Memory Efficient)
    # ========================================================================
    print("\n🔄 PART 3: CHUNKED PROCESSING")
    print("-" * 70)

    # For truly massive files, you'd process in chunks
    # This demonstrates the pattern:

    print("\n✓ Processing large file in chunks...")

    # Simulate chunked processing by reading portions
    process_chunk_size = 2 * 1024 * 1024  # 2MB chunks
    num_process_chunks = len(read_data) // process_chunk_size
    checksum = 0

    for i in range(num_process_chunks):
        start_offset = i * process_chunk_size
        end_offset = min(start_offset + process_chunk_size, len(read_data))
        chunk = read_data[start_offset:end_offset]

        # Simulate processing (calculate checksum)
        checksum += sum(chunk)

        progress = (i + 1) / num_process_chunks * 100
        print(f"  Processing... {progress:.0f}%", end="\r")

    print("  Processing... 100% ✓")
    print(
        f"\n✓ Processed {len(read_data) / 1024 / 1024:.1f} MB in {num_process_chunks} chunks"
    )
    print(f"  Checksum: {checksum}")

    # ========================================================================
    # Part 4: Multiple Large Files (Batch)
    # ========================================================================
    print("\n📦 PART 4: MULTIPLE LARGE FILES (BATCH)")
    print("-" * 70)

    # Create multiple large files
    num_files = 5
    file_size = 2 * 1024 * 1024  # 2MB each

    print(
        f"\n✓ Creating {num_files} large files ({file_size / 1024 / 1024:.1f} MB each)..."
    )

    batch_start = time.time()

    for i in range(num_files):
        file_data = f"File {i}: ".encode() + b"y" * (file_size - 20)
        await vfs.write_binary(f"/batch_file_{i}.bin", file_data)
        print(f"  Created file {i + 1}/{num_files}", end="\r")

    batch_time = time.time() - batch_start

    print("  Created all files ✓")
    print("\n✓ Batch write completed:")
    print(f"  Files: {num_files}")
    print(f"  Total size: {num_files * file_size / 1024 / 1024:.1f} MB")
    print(f"  Time: {batch_time:.2f}s")
    print(f"  Throughput: {num_files * file_size / 1024 / 1024 / batch_time:.1f} MB/s")

    # List all files
    all_files = await vfs.ls("/")
    large_files = [f for f in all_files if f.endswith(".bin")]
    print(f"\n✓ Found {len(large_files)} binary files in workspace")

    # ========================================================================
    # Part 5: Text vs Binary for Large Files
    # ========================================================================
    print("\n📝 PART 5: TEXT VS BINARY FOR LARGE FILES")
    print("-" * 70)

    # Create large text file
    text_lines = []
    for i in range(100000):  # 100k lines
        text_lines.append(f"Line {i:06d}: This is a test line with some content\n")

    large_text = "".join(text_lines)
    text_size = len(large_text.encode("utf-8"))

    print("\n✓ Creating large text file:")
    print(f"  Lines: {len(text_lines):,}")
    print(f"  Size: {text_size / 1024 / 1024:.1f} MB")

    # Write as text
    text_write_start = time.time()
    await vfs.write_text("/large_text.txt", large_text)
    text_write_time = time.time() - text_write_start

    print("\n✓ Wrote large text file:")
    print(f"  Time: {text_write_time:.2f}s")
    print(f"  Throughput: {text_size / 1024 / 1024 / text_write_time:.1f} MB/s")

    # Read as text
    text_read_start = time.time()
    read_text = await vfs.read_text("/large_text.txt")
    text_read_time = time.time() - text_read_start

    print("\n✓ Read large text file:")
    print(f"  Time: {text_read_time:.2f}s")
    print(f"  Lines: {len(read_text.splitlines()):,}")
    print(f"  Data integrity: {read_text == large_text}")

    # ========================================================================
    # Part 6: Storage Stats
    # ========================================================================
    print("\n📊 PART 6: STORAGE STATS")
    print("-" * 70)

    # Get node info for large files
    large_file_info = await vfs.get_node_info("/large_file.bin")
    print("\n✓ Large file info:")
    print(f"  Name: {large_file_info.name}")
    print(f"  Size: {large_file_info.size / 1024 / 1024:.1f} MB")
    print(f"  MIME type: {large_file_info.mime_type}")
    print(f"  Created: {large_file_info.created_at}")

    # Get storage stats
    stats = await vfs.get_storage_stats()
    print("\n✓ Workspace storage stats:")
    if stats.get("total_size"):
        print(f"  Total size: {stats['total_size'] / 1024 / 1024:.1f} MB")
    print(f"  Total files: {stats.get('total_files', 'N/A')}")

    # ========================================================================
    # Part 7: Cleanup Large Files
    # ========================================================================
    print("\n🧹 PART 7: CLEANUP")
    print("-" * 70)

    # Delete large files
    print("\n✓ Cleaning up large files...")
    await vfs.rm("/large_file.bin")
    await vfs.rm("/large_text.txt")

    for i in range(num_files):
        await vfs.rm(f"/batch_file_{i}.bin")

    remaining_files = await vfs.ls("/")
    print(f"✓ Remaining files: {remaining_files}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ LARGE FILES AND STREAMING - SUMMARY")
    print("=" * 70)

    print(
        """
  LARGE FILE HANDLING:

    Writing:
      ✓ write_binary() - Binary files (efficient)
      ✓ write_text() - Text files (UTF-8 encoding)
      ✓ Handles files of any size

    Reading:
      ✓ read_binary() - Binary files (returns bytes)
      ✓ read_text() - Text files (returns str)
      ✓ Efficient memory usage

    Batch Operations:
      ✓ Multiple large files
      ✓ Parallel processing possible
      ✓ Good throughput

    Best Practices:
      → Use write_binary/read_binary for non-text data
      → Use write_text/read_text for text data
      → Process in chunks for massive files (>100MB)
      → Monitor storage stats
      → Clean up temporary large files

    VFS Benefits:
      → Provider handles optimization
      → Memory-efficient internally
      → Same API regardless of file size
      → Works for both BLOB and WORKSPACE namespaces
    """
    )

    # Cleanup workspace
    print("\n🧹 Destroying workspace...")
    await store.destroy_namespace(workspace.namespace_id)
    print("✓ Workspace destroyed")

    print("\n" + "=" * 70)
    print("✓ LARGE FILES DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
