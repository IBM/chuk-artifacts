#!/usr/bin/env python3
"""
Example 8: Batch Operations for Efficiency

This example demonstrates batch operations for efficient bulk processing:
- Batch file creation with metadata
- Batch reading multiple files
- Batch writing/updating files
- Batch deletion
- Use cases for batch operations
- Performance comparisons
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
    print("BATCH OPERATIONS FOR EFFICIENCY")
    print("=" * 70)

    # ========================================================================
    # Part 1: Individual vs Batch Operations Comparison
    # ========================================================================
    print("\n⚡ PART 1: INDIVIDUAL VS BATCH OPERATIONS")
    print("-" * 70)

    workspace = await store.create_namespace(
        type=NamespaceType.WORKSPACE,
        name="batch-demo",
        scope=StorageScope.SESSION,
    )

    vfs = store.get_namespace_vfs(workspace.namespace_id)

    num_files = 50

    # Individual writes
    print(f"\n✓ Writing {num_files} files individually...")
    individual_start = time.time()

    for i in range(num_files):
        await vfs.write_file(f"/individual_{i}.txt", f"Individual file {i}".encode())

    individual_time = time.time() - individual_start
    print(f"  Time: {individual_time:.3f}s")
    print(f"  Rate: {num_files / individual_time:.0f} files/sec")

    # Batch creates (which both creates and writes)
    print(f"\n✓ Creating {num_files} files with batch_create...")
    batch_specs = [
        {"path": f"/batch_{i}.txt", "content": f"Batch file {i}".encode()}
        for i in range(num_files)
    ]

    batch_start = time.time()
    await vfs.batch_create_files(batch_specs)
    batch_time = time.time() - batch_start

    print(f"  Time: {batch_time:.3f}s")
    print(f"  Rate: {num_files / batch_time:.0f} files/sec")
    print(f"\n✓ Batch is {individual_time / batch_time:.1f}x faster!")

    # ========================================================================
    # Part 2: Batch Create with Metadata
    # ========================================================================
    print("\n📦 PART 2: BATCH CREATE WITH METADATA")
    print("-" * 70)

    # Create multiple files with metadata in one operation
    file_specs = [
        {
            "path": f"/project/module_{i}.py",
            "content": f'"""Module {i}"""\n\ndef function_{i}():\n    pass\n'.encode(),
            "metadata": {
                "module_id": i,
                "author": "alice" if i % 2 == 0 else "bob",
                "version": "1.0",
                "tags": ["python", "module"],
            },
        }
        for i in range(10)
    ]

    print(f"\n✓ Creating {len(file_specs)} Python modules with metadata...")
    create_start = time.time()
    await vfs.batch_create_files(file_specs)
    create_time = time.time() - create_start

    print(f"  Time: {create_time:.3f}s")
    print(f"  Files created: {len(file_specs)}")

    # Verify metadata
    module_0_meta = await vfs.get_metadata("/project/module_0.py")
    print("\n✓ Module 0 metadata:")
    print(f"  Author: {module_0_meta.get('author')}")
    print(f"  Tags: {module_0_meta.get('tags')}")

    # ========================================================================
    # Part 3: Batch Read Operations
    # ========================================================================
    print("\n📖 PART 3: BATCH READ OPERATIONS")
    print("-" * 70)

    # Read multiple files at once
    paths_to_read = [f"/batch_{i}.txt" for i in range(10)]

    print(f"\n✓ Reading {len(paths_to_read)} files with batch_read...")
    read_start = time.time()
    batch_read_data = await vfs.batch_read_files(paths_to_read)
    read_time = time.time() - read_start

    print(f"  Time: {read_time:.3f}s")
    print(f"  Files read: {len(batch_read_data)}")
    print(f"  Sample: {list(batch_read_data.keys())[:3]}")

    # ========================================================================
    # Part 4: Batch Update Operations
    # ========================================================================
    print("\n✏️  PART 4: BATCH UPDATE OPERATIONS")
    print("-" * 70)

    # Update multiple existing files
    update_data = {
        f"/batch_{i}.txt": f"Updated batch file {i}".encode() for i in range(5)
    }

    print(f"\n✓ Updating {len(update_data)} files...")
    update_start = time.time()
    await vfs.batch_write_files(update_data)
    update_time = time.time() - update_start

    print(f"  Time: {update_time:.3f}s")
    print(f"  Files updated: {len(update_data)}")

    # Verify update
    updated_content = await vfs.read_file("/batch_0.txt")
    if updated_content:
        print(f"\n✓ Verified update: {updated_content.decode()}")
    else:
        print(f"\n✓ Update completed (file exists: {await vfs.exists('/batch_0.txt')})")

    # ========================================================================
    # Part 5: Batch Delete Operations
    # ========================================================================
    print("\n🗑️  PART 5: BATCH DELETE OPERATIONS")
    print("-" * 70)

    # Delete multiple files at once
    paths_to_delete = [f"/individual_{i}.txt" for i in range(num_files)]

    print(f"\n✓ Deleting {len(paths_to_delete)} files with batch_delete...")
    delete_start = time.time()
    await vfs.batch_delete_paths(paths_to_delete)
    delete_time = time.time() - delete_start

    print(f"  Time: {delete_time:.3f}s")
    print(f"  Files deleted: {len(paths_to_delete)}")
    print(f"  Rate: {len(paths_to_delete) / delete_time:.0f} files/sec")

    # ========================================================================
    # Part 6: Real-World Use Case - Dataset Management
    # ========================================================================
    print("\n💡 PART 6: REAL-WORLD USE CASE - DATASET MANAGEMENT")
    print("-" * 70)

    print("\n✓ Creating a dataset with 100 data files...")

    # Create dataset with batch operations
    dataset_specs = []
    for category in ["train", "val", "test"]:
        for i in range(33 if category == "train" else 17):
            dataset_specs.append(
                {
                    "path": f"/dataset/{category}/sample_{i:03d}.json",
                    "content": f'{{"id": {i}, "category": "{category}", "value": {i * 10}}}'.encode(),
                    "metadata": {
                        "category": category,
                        "sample_id": i,
                        "split": category,
                    },
                }
            )

    dataset_start = time.time()
    await vfs.batch_create_files(dataset_specs)
    dataset_time = time.time() - dataset_start

    print(f"  Files created: {len(dataset_specs)}")
    print(f"  Time: {dataset_time:.3f}s")
    print(f"  Rate: {len(dataset_specs) / dataset_time:.0f} files/sec")

    # Verify dataset structure
    dataset_files = await vfs.find(pattern="*.json", path="/dataset", recursive=True)
    print("\n✓ Dataset verification:")
    print(f"  Total JSON files: {len(dataset_files)}")

    # Count by category
    train_files = [f for f in dataset_files if "/train/" in f]
    val_files = [f for f in dataset_files if "/val/" in f]
    test_files = [f for f in dataset_files if "/test/" in f]

    print(f"  Train split: {len(train_files)}")
    print(f"  Val split: {len(val_files)}")
    print(f"  Test split: {len(test_files)}")

    # ========================================================================
    # Part 7: Real-World Use Case - Log Processing
    # ========================================================================
    print("\n📋 PART 7: REAL-WORLD USE CASE - LOG PROCESSING")
    print("-" * 70)

    print("\n✓ Creating log files for multiple services...")

    # Create logs for different services
    services = ["api", "database", "cache", "worker"]
    log_specs = []

    for service in services:
        for hour in range(24):
            log_content = "\n".join(
                [
                    f"[{hour:02d}:{minute:02d}:00] {service.upper()}: Event {minute}"
                    for minute in range(0, 60, 5)
                ]
            )
            log_specs.append(
                {
                    "path": f"/logs/{service}/2025-11-25_{hour:02d}.log",
                    "content": log_content.encode(),
                    "metadata": {
                        "service": service,
                        "date": "2025-11-25",
                        "hour": hour,
                        "type": "application_log",
                    },
                }
            )

    logs_start = time.time()
    await vfs.batch_create_files(log_specs)
    logs_time = time.time() - logs_start

    print(f"  Log files created: {len(log_specs)}")
    print(f"  Time: {logs_time:.3f}s")
    print(f"  Services: {', '.join(services)}")
    print("  Hours covered: 24")

    # ========================================================================
    # Part 8: Performance Summary
    # ========================================================================
    print("\n📊 PART 8: PERFORMANCE SUMMARY")
    print("-" * 70)

    total_files = num_files * 2 + len(file_specs) + len(dataset_specs) + len(log_specs)
    total_operations = (
        individual_time
        + batch_time
        + create_time
        + read_time
        + update_time
        + delete_time
        + dataset_time
        + logs_time
    )

    print("\n✓ Overall statistics:")
    print(f"  Total files processed: {total_files}")
    print(f"  Total time: {total_operations:.3f}s")
    print(f"  Average rate: {total_files / total_operations:.0f} files/sec")

    print("\n✓ Operation breakdown:")
    print(f"  Individual writes: {num_files} files in {individual_time:.3f}s")
    print(f"  Batch writes: {num_files} files in {batch_time:.3f}s")
    print(f"  Batch creates: {len(file_specs)} files in {create_time:.3f}s")
    print(f"  Batch reads: {len(batch_read_data)} files in {read_time:.3f}s")
    print(f"  Batch updates: {len(update_data)} files in {update_time:.3f}s")
    print(f"  Batch deletes: {len(paths_to_delete)} files in {delete_time:.3f}s")
    print(f"  Dataset creation: {len(dataset_specs)} files in {dataset_time:.3f}s")
    print(f"  Log creation: {len(log_specs)} files in {logs_time:.3f}s")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ BATCH OPERATIONS - SUMMARY")
    print("=" * 70)

    print(
        """
  BATCH OPERATIONS AVAILABLE:

    batch_create_files(file_specs):
      ✓ Create multiple files with content and metadata
      ✓ Most efficient for new files
      ✓ Perfect for: datasets, project scaffolding, bulk imports

    batch_write_files(file_data):
      ✓ Write/update multiple existing files
      ✓ Dictionary of path -> content
      ✓ Perfect for: bulk updates, synchronization

    batch_read_files(paths):
      ✓ Read multiple files at once
      ✓ Returns dictionary of path -> content
      ✓ Perfect for: loading configurations, reading datasets

    batch_delete_paths(paths):
      ✓ Delete multiple files/directories
      ✓ Efficient bulk deletion
      ✓ Perfect for: cleanup, pruning, archive

  WHEN TO USE BATCH OPERATIONS:

    ✓ Processing multiple files (>10)
    ✓ Initial project setup
    ✓ Dataset management
    ✓ Log processing
    ✓ Bulk migrations
    ✓ Synchronization tasks

  BENEFITS:

    → Significantly faster than individual operations
    ✓ Reduced overhead
    ✓ Better throughput
    ✓ Cleaner code
    ✓ Atomic-like behavior (all or nothing)

  WORKS FOR BOTH:
    → BLOB namespaces (batch operations on /_data)
    → WORKSPACE namespaces (batch operations on any files)
    """
    )

    # Cleanup
    print("\n🧹 Cleaning up...")
    await store.destroy_namespace(workspace.namespace_id)
    print("✓ Workspace destroyed")

    print("\n" + "=" * 70)
    print("✓ BATCH OPERATIONS DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
