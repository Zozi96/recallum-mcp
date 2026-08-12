# Claude Desktop MCP Specification

## Purpose
TBD

## Requirements
### Requirement: Native Claude user MCP registration
When the Recallum installer configures the Claude target, it MUST register (or update under force) a user-scoped HTTP MCP server named `recallum` whose URL is the normalized Recallum `/mcp/` endpoint. This registration MUST be independent of the plugin-bundled `.mcp.json` so Claude Desktop sessions that load plugin hooks but omit plugin MCP tools still receive a connectable server. The installer MUST still install and configure the `recallum-memory` plugin (marketplace, `mcp_url` userConfig, and optional pluginSecrets) for hooks and skills.

#### Scenario: Fresh Claude install writes native MCP
- **WHEN** an operator runs the installer for the Claude target with a valid endpoint and the native `recallum` server is absent
- **THEN** the Claude user MCP configuration contains an HTTP server named `recallum` whose URL matches the normalized install endpoint ending in `/mcp/`

#### Scenario: Plugin install remains part of Claude setup
- **WHEN** an operator runs the installer for the Claude target
- **THEN** the `recallum-memory` plugin is installed or reinstalled for Claude and non-sensitive `mcp_url` userConfig is present for the plugin path

#### Scenario: Mismatched native MCP requires force
- **WHEN** a user-scoped `recallum` MCP server already exists with a different URL than the install endpoint and the operator did not pass force replacement
- **THEN** the installer exits with an error that names force replacement and MUST NOT silently overwrite the existing server

#### Scenario: Force replaces mismatched native MCP
- **WHEN** a user-scoped `recallum` MCP server exists with a different URL and the operator requests force replacement
- **THEN** the installer rewrites that server to the install endpoint and a desktop-safe Authorization header per the auth requirements

### Requirement: Desktop-safe native MCP authentication
The native Claude `recallum` MCP entry MUST authenticate with `Authorization: Bearer …`. When the installer stores or otherwise has an API key for this run, it MUST write a literal Bearer token into that entry and MUST NOT print the key. When the operator opts out of key persistence and only an environment variable is intended, the entry MUST use the unexpanded `Bearer ${ENV_VAR}` form for the configured token env var name. The installer MUST continue to populate Claude pluginSecrets for the plugin path when a key is stored, so GUI-oriented plugin configuration remains available.

#### Scenario: Stored key produces literal Bearer on native entry
- **WHEN** the installer configures Claude and an API key is stored for this run
- **THEN** the native `recallum` MCP entry’s Authorization header is a literal Bearer value and the key value is not written to installer stdout or stderr

#### Scenario: No-store uses env placeholder
- **WHEN** the installer configures Claude with key persistence disabled and a token environment variable name is configured
- **THEN** the native `recallum` MCP entry’s Authorization header is exactly `Bearer ${<that variable name>}` with no expanded secret

### Requirement: Dual Claude tool prefix discovery
Agent-facing Claude instructions shipped with the plugin (session hook text and the Claude rows of the memory/setup skills and client docs) MUST state that Recallum tools may appear under either `mcp__plugin_recallum-memory_recallum__*` or `mcp__recallum__*`, and MUST direct the agent to use the host tool search (ToolSearch) with a recallum-oriented query before concluding memory is unavailable. They MUST NOT present the long plugin-only name as the sole callable form.

#### Scenario: Session hook names both prefixes on Claude
- **WHEN** the session hook emits Claude-oriented context and no digest was inlined
- **THEN** the additional context mentions both the plugin-namespaced tool form and the native `mcp__recallum__` form (or an equivalent explicit dual-prefix statement) and mentions ToolSearch

#### Scenario: Zero tools after search remains fail-open
- **WHEN** neither Claude tool prefix is present after tool search
- **THEN** the agent-facing text still permits continuing the task without memory (fail-open) after telling the user once

### Requirement: Desktop vs CLI diagnostics
Setup and troubleshooting documentation for Claude MUST distinguish a healthy nested-shell `claude mcp list` from tool presence inside a Desktop session, and MUST state that Desktop sessions need the native user MCP entry (or equivalent registered tools) for ToolSearch to return Recallum tools.

#### Scenario: Troubleshooting documents false-green CLI check
- **WHEN** an operator follows the Claude setup diagnostics after a Desktop ToolSearch miss
- **THEN** the documentation warns that running `claude mcp list` from a shell or from Bash inside Desktop does not prove Desktop session tool registration, and points at ToolSearch or native MCP registration as the session-level check
