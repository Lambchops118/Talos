# Coding-Agent MCP Setup

TALOS can be extended into a much more capable coding agent by appending four MCP providers:

- local Git awareness for repo status, diff, branches, and commit history
- GitHub platform access for PRs, issues, Actions, repository metadata, and remote code reads
- semantic code intelligence through `mcp-language-server`
- up-to-date dependency and library docs through Context7

## Recommended Shape

Use the local filesystem helpers for broad repo access, then add:

- `git` for repository-aware workflows inside one local checkout
- `github` for remote repository APIs and collaboration workflows
- `language-server` for symbol definitions, references, diagnostics, hover, and rename
- `context7` for current library and framework documentation

This gives TALOS a strong split of responsibilities:

- filesystem MCP for files and search
- git MCP for local VCS state
- GitHub MCP for remote hosting/workflow state
- language-server MCP for semantic navigation
- Context7 for third-party docs

## `.env` Example

```env
TALOS_FILESYSTEM_ROOTS=["/Users/you/dev"]

TALOS_GIT_MCP_ENABLED=1
TALOS_GIT_REPOSITORY=/Users/you/dev/your-repo

TALOS_GITHUB_MCP_ENABLED=1
TALOS_GITHUB_MCP_MODE=remote
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_your_token_here

TALOS_LANGUAGE_SERVER_MCP_ENABLED=1
TALOS_LANGUAGE_SERVER_WORKSPACE=/Users/you/dev/your-repo
TALOS_LANGUAGE_SERVER_LSP=pyright-langserver
TALOS_LANGUAGE_SERVER_LSP_ARGS_JSON=["--stdio"]

TALOS_CONTEXT7_MCP_ENABLED=1
CONTEXT7_API_KEY=ctx7_your_key_here
```

Restart TALOS after changing `.env`.

## Provider Details

### Local Git MCP

TALOS uses the official Git reference server.

- Default command: `uvx`
- Default package: `mcp-server-git`
- Default repo: the TALOS checkout root unless `TALOS_GIT_REPOSITORY` is set

Useful for:

- status and diff inspection
- commit and branch context
- local history-aware code review

### GitHub MCP

TALOS defaults to the official remote GitHub MCP server hosted by GitHub:

- URL: `https://api.githubcopilot.com/mcp/`
- PAT env: `GITHUB_PERSONAL_ACCESS_TOKEN`

Useful for:

- reading remote repositories
- issues and pull requests
- GitHub Actions and workflow runs
- repository metadata and code search

If you need a local GitHub MCP server instead, TALOS also supports `TALOS_GITHUB_MCP_MODE=local` with a Docker-based configuration.

### `mcp-language-server`

TALOS wires `mcp-language-server` as a generic semantic provider.

Defaults:

- command: `mcp-language-server`
- workspace: TALOS checkout root unless overridden
- LSP backend: `pyright-langserver`
- LSP args: `["--stdio"]`

For other languages, change `TALOS_LANGUAGE_SERVER_LSP` and `TALOS_LANGUAGE_SERVER_LSP_ARGS_JSON`.

Examples:

- TypeScript: `typescript-language-server` with `["--stdio"]`
- Go: `gopls` with no extra args
- Rust: `rust-analyzer` with no extra args
- C/C++: `clangd` with compile-command flags as needed

### Context7

TALOS uses the hosted Context7 MCP endpoint:

- URL: `https://mcp.context7.com/mcp`
- optional API key env: `CONTEXT7_API_KEY`

Useful for:

- version-aware library docs
- current framework usage patterns
- avoiding stale dependency knowledge

## Notes

- These helpers are opt-in and are not appended unless their `*_ENABLED=1` flags are set.
- `git` and `language-server` are local tools; `github` and `context7` are remote by default.
- The GitHub and Context7 providers may fail if network access, authentication, or host policy is missing.
