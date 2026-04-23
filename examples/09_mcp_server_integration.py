#!/usr/bin/env python3
"""
Example 9: MCP Server Integration

This example demonstrates how to integrate chuk-artifacts with an MCP server:
- Setting up context-aware artifact management
- Creating MCP tools that use artifacts
- Automatic user/session scoping
- Building a complete MCP server with artifact support
"""

import asyncio
import os

os.environ.setdefault("ARTIFACT_PROVIDER", "memory")
os.environ.setdefault("SESSION_PROVIDER", "memory")

from chuk_artifacts import ArtifactStore, NamespaceType, StorageScope


async def main():
    print("=" * 70)
    print("MCP SERVER INTEGRATION")
    print("=" * 70)

    # ========================================================================
    # Part 1: Setting Up Artifact Store for MCP Server
    # ========================================================================
    print("\n📦 PART 1: SETTING UP ARTIFACT STORE")
    print("-" * 70)

    # In a real MCP server, you'd set this up once in your server initialization
    store = ArtifactStore()
    print("\n✓ ArtifactStore initialized")
    print("  This would typically be done in create_server()")

    # ========================================================================
    # Part 2: Context-Aware Tool Pattern
    # ========================================================================
    print("\n🔧 PART 2: CONTEXT-AWARE TOOL PATTERN")
    print("-" * 70)

    # Simulate context variables (in real MCP server, these come from context)
    current_user_id = "alice"
    current_session_id = "sess-001"

    print("\n✓ Context simulation:")
    print(f"  user_id: {current_user_id}")
    print(f"  session_id: {current_session_id}")

    # This is how an MCP tool would work
    async def create_artifact_tool(
        content: str,
        name: str | None = None,
        scope: StorageScope = StorageScope.SESSION,
    ):
        """
        MCP tool to create an artifact.

        In a real MCP server:
        - user_id and session_id come from get_user_id() and get_session_id()
        - The @tool decorator makes this available to AI agents
        """
        # Get context (in real server, use get_user_id() and get_session_id())
        user_id = current_user_id
        session_id = current_session_id

        # Create blob namespace
        namespace = await store.create_namespace(
            type=NamespaceType.BLOB,
            name=name,
            scope=scope,
            user_id=(
                user_id if scope in (StorageScope.USER, StorageScope.SESSION) else None
            ),
            session_id=session_id if scope == StorageScope.SESSION else None,
        )

        # Write content
        await store.write_namespace(namespace.namespace_id, data=content.encode())

        return {
            "namespace_id": namespace.namespace_id,
            "grid_path": namespace.grid_path,
            "scope": scope.value,
            "size": len(content.encode()),
        }

    # Use the tool
    result = await create_artifact_tool(
        content="This is my artifact content",
        name="my-document",
        scope=StorageScope.USER,
    )

    print("\n✓ Created artifact via tool:")
    print(f"  namespace_id: {result['namespace_id']}")
    print(f"  grid_path: {result['grid_path']}")
    print(f"  scope: {result['scope']}")
    print(f"  size: {result['size']} bytes")

    # ========================================================================
    # Part 3: Workspace Tool Pattern
    # ========================================================================
    print("\n📁 PART 3: WORKSPACE TOOL PATTERN")
    print("-" * 70)

    async def create_workspace_tool(
        name: str,
        scope: StorageScope = StorageScope.SESSION,
        provider_type: str = "vfs-memory",
    ):
        """
        MCP tool to create a workspace.

        This is similar to how chuk-mcp-vfs works internally.
        """
        # Get context
        user_id = current_user_id
        session_id = current_session_id

        # Create workspace namespace
        namespace = await store.create_namespace(
            type=NamespaceType.WORKSPACE,
            name=name,
            scope=scope,
            user_id=(
                user_id if scope in (StorageScope.USER, StorageScope.SESSION) else None
            ),
            session_id=session_id if scope == StorageScope.SESSION else None,
            provider_type=provider_type,
        )

        # Get VFS for file operations
        vfs = store.get_namespace_vfs(namespace.namespace_id)

        # Create some initial structure
        await vfs.write_text("/README.md", f"# {name}\n\nWorkspace created!\n")
        await vfs.mkdir("/src")
        await vfs.mkdir("/tests")

        return {
            "namespace_id": namespace.namespace_id,
            "grid_path": namespace.grid_path,
            "scope": scope.value,
            "name": name,
        }

    # Use the tool
    workspace_result = await create_workspace_tool(
        name="my-project",
        scope=StorageScope.USER,
    )

    print("\n✓ Created workspace via tool:")
    print(f"  namespace_id: {workspace_result['namespace_id']}")
    print(f"  name: {workspace_result['name']}")
    print(f"  scope: {workspace_result['scope']}")

    # Verify structure
    vfs = store.get_namespace_vfs(workspace_result["namespace_id"])
    files = await vfs.ls("/")
    print(f"\n✓ Workspace contents: {files}")

    # ========================================================================
    # Part 4: List Artifacts Tool Pattern
    # ========================================================================
    print("\n📋 PART 4: LIST ARTIFACTS TOOL PATTERN")
    print("-" * 70)

    async def list_artifacts_tool(scope: StorageScope | None = None):
        """
        MCP tool to list artifacts.

        Lists all artifacts accessible to the current user/session.
        """
        # Get context
        user_id = current_user_id
        session_id = current_session_id

        # List namespaces
        if scope == StorageScope.SESSION:
            namespaces = store.list_namespaces(session_id=session_id)
        elif scope == StorageScope.USER:
            namespaces = store.list_namespaces(user_id=user_id)
        elif scope == StorageScope.SANDBOX:
            namespaces = store.list_namespaces()  # All sandbox namespaces
        else:
            # All namespaces for current user
            namespaces = store.list_namespaces(user_id=user_id)

        return [
            {
                "namespace_id": ns.namespace_id,
                "type": ns.type.value,
                "name": ns.name,
                "scope": ns.scope.value,
                "grid_path": ns.grid_path,
                "created_at": str(ns.created_at),
            }
            for ns in namespaces
        ]

    # Use the tool
    artifacts = await list_artifacts_tool(scope=StorageScope.USER)

    print(f"\n✓ Found {len(artifacts)} user-scoped artifact(s):")
    for artifact in artifacts:
        print(
            f"  • {artifact['type']:9} | {artifact['name']:15} | {artifact['namespace_id']}"
        )

    # ========================================================================
    # Part 5: Read Artifact Tool Pattern
    # ========================================================================
    print("\n📖 PART 5: READ ARTIFACT TOOL PATTERN")
    print("-" * 70)

    async def read_artifact_tool(namespace_id: str):
        """
        MCP tool to read an artifact.

        Works for both BLOB and WORKSPACE types.
        """
        # Get namespace info by getting it directly
        try:
            # Try to read to verify it exists and get type
            vfs = store.get_namespace_vfs(namespace_id)
            # If we got here, it's a valid namespace
            # Determine type by checking if it's a BLOB or WORKSPACE
            # For now, try reading as blob first
            try:
                content = await store.read_namespace(namespace_id)
                namespace_type = NamespaceType.BLOB
            except Exception:
                namespace_type = NamespaceType.WORKSPACE
        except Exception:
            raise ValueError(f"Namespace '{namespace_id}' not found")

        if namespace_type == NamespaceType.BLOB:
            # Read blob content (already read above)
            return {
                "namespace_id": namespace_id,
                "type": "blob",
                "content": content.decode(),
                "size": len(content),
            }
        else:
            # Read workspace file tree
            files = await vfs.find(pattern="*", recursive=True)
            return {
                "namespace_id": namespace_id,
                "type": "workspace",
                "files": files,
                "file_count": len(files),
            }

    # Read the artifact we created
    artifact_content = await read_artifact_tool(result["namespace_id"])

    print("\n✓ Read artifact:")
    print(f"  Type: {artifact_content['type']}")
    print(f"  Content: {artifact_content['content'][:50]}...")

    # Read the workspace we created
    workspace_content = await read_artifact_tool(workspace_result["namespace_id"])

    print("\n✓ Read workspace:")
    print(f"  Type: {workspace_content['type']}")
    print(f"  Files: {workspace_content['files']}")

    # ========================================================================
    # Part 6: Complete MCP Server Example
    # ========================================================================
    print("\n🖥️  PART 6: COMPLETE MCP SERVER EXAMPLE")
    print("-" * 70)

    print("\n✓ To create a complete MCP server, you would:")
    print(
        """
    from chuk_mcp_server import ChukMCPServer
    from chuk_artifacts import ArtifactStore

    def create_server():
        # Initialize artifact store
        store = ArtifactStore()
        server = ChukMCPServer()

        # Register tools
        @server.tool
        async def create_artifact(content: str, name: str = None, scope: str = "session"):
            # Tool implementation using store
            ...

        @server.tool
        async def create_workspace(name: str, scope: str = "session"):
            # Tool implementation using store
            ...

        @server.tool
        async def list_artifacts(scope: str = None):
            # Tool implementation using store
            ...

        return server

    # Run server
    server = create_server()
    server.run_stdio()
    """
    )

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("✨ MCP SERVER INTEGRATION - SUMMARY")
    print("=" * 70)

    print(
        """
  KEY PATTERNS:

    1. Context-Aware Tools:
       ✓ Use get_user_id() and get_session_id() from context
       ✓ Automatic scoping based on context
       ✓ No need to pass user/session explicitly

    2. Artifact Management:
       ✓ create_artifact_tool() - Create BLOB namespaces
       ✓ create_workspace_tool() - Create WORKSPACE namespaces
       ✓ list_artifacts_tool() - List namespaces by scope
       ✓ read_artifact_tool() - Read artifact content

    3. Workspace Management:
       ✓ Each workspace is a WORKSPACE namespace
       ✓ Use get_namespace_vfs() for file operations
       ✓ Full VFS API available (read, write, ls, etc.)

    4. Scope Management:
       ✓ SESSION - Ephemeral, per-conversation
       ✓ USER - Persistent, per-user
       ✓ SANDBOX - Shared across all users

    5. MCP Integration:
       ✓ Use @server.tool decorator
       ✓ Pydantic models for requests/responses
       ✓ Context variables for user/session
       ✓ Automatic JSON schema generation

  EXAMPLE SERVERS USING THIS PATTERN:

    → chuk-mcp-vfs: Virtual filesystem workspaces
    → Your custom server: Any artifact-based application

  BENEFITS:

    → Unified architecture (everything is VFS)
    → Automatic scope isolation
    → Context-aware tools
    → Clean grid-based storage
    → Consistent API across blob/workspace types
    """
    )

    # Cleanup
    print("\n🧹 Cleaning up...")
    all_namespaces = store.list_namespaces()
    for ns in all_namespaces:
        await store.destroy_namespace(ns.namespace_id)
    print("✓ All namespaces cleaned up")

    print("\n" + "=" * 70)
    print("✓ MCP SERVER INTEGRATION DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
