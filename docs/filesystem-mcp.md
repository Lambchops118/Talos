# Filesystem MCP Support

TALOS can now attach the official `@modelcontextprotocol/server-filesystem` server for general-purpose file inspection and editing.

## Configuration

Add one or more allowed roots to `.env`:

```env
TALOS_FILESYSTEM_ROOTS=["/Users/you/projects","/Volumes/shared/reference"]
TALOS_FILESYSTEM_ALLOW_WRITES=0
```

Notes:

- `TALOS_FILESYSTEM_ROOTS` accepts either:
  - a JSON array of paths
  - a single JSON string path
  - a plain platform-separated string, though JSON is preferred
- Relative paths are resolved relative to the TALOS repo root.
- TALOS prefixes official filesystem tools with `fs_` by default.

## Safety Defaults

- The official filesystem server is limited to the configured roots only.
- TALOS hides write-capable tools by default.
- To expose writes, set:

```env
TALOS_FILESYSTEM_ALLOW_WRITES=1
```

Even with writes exposed, TALOS's prompt guidance still prefers explaining evidence and showing diffs before modifying files.

## What This Enables

Once configured, TALOS can use the official filesystem MCP toolset for:

- listing directories
- building directory trees
- reading text files
- reading media files
- getting file metadata
- searching for files by name/pattern
- editing/writing/moving files when writes are enabled

## Verification

Run:

```bash
.venv-main/bin/python tools/verify_filesystem_mcp_setup.py
```

The smoke check verifies:

1. Filesystem MCP tools are visible.
2. The configured root can be listed.
3. Access outside the configured roots is rejected.

## Interaction Style

When using the general filesystem server, TALOS should still:

- prefer shallow inspection before deep reads
- use absolute paths when helpful
- avoid dumping large files blindly
- explain risky edits before making them
