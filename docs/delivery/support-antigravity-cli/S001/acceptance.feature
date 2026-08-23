Feature: Add a validated MCP config to the Recallum plugin bundle
  Antigravity CLI (`agy`) validates and installs the `recallum-memory` plugin
  bundle. The bundle gains a bundle-root `mcp_config.json` in the shape `agy`
  accepts, so `agy plugin validate` reports the MCP server alongside the
  existing skills, and the runtime effect of carrying that config is probed
  and recorded.

  Background:
    Given the plugin bundle exists at "plugins/recallum-memory"

  Rule: The bundle-root mcp_config.json uses the serverUrl shape, not the legacy type/url shape

    Scenario: New mcp_config.json declares the recallum server with serverUrl
      Given "plugins/recallum-memory/mcp_config.json" exists
      When the file's "recallum" server entry is inspected
      Then the entry contains a "serverUrl" field
      And the entry does not contain "type" or "url" fields

    Scenario: Validation accepts the serverUrl shape without the missing-field error
      Given "plugins/recallum-memory/mcp_config.json" declares "recallum" using "serverUrl"
      When I run `agy plugin validate plugins/recallum-memory`
      Then the command does not report `Error: MCP server "recallum" must have either command or serverUrl`
      And the command exits successfully

    Scenario: The legacy type/url shape is rejected by validation
      Given a bundle's "mcp_config.json" declares "recallum" using "type" and "url" instead of "serverUrl"
      When I run `agy plugin validate` against that bundle
      Then the command reports `Error: MCP server "recallum" must have either command or serverUrl`
      And validation fails

  Rule: agy plugin validate reports both skills and mcpServers for the bundle

    Scenario: Validate reports mcpServers processed alongside the unchanged skills count
      Given "plugins/recallum-memory/mcp_config.json" is present with the "recallum" serverUrl entry
      When I run `agy plugin validate plugins/recallum-memory`
      Then the output reports "skills: 2 processed"
      And the output reports mcpServers as processed, not "not found"

  Rule: plugin.json continues to validate cleanly after the addition

    Scenario: plugin.json validates with no new errors after adding mcp_config.json
      Given "plugins/recallum-memory/plugin.json" is unchanged
      And "plugins/recallum-memory/mcp_config.json" has been added to the bundle
      When I run `agy plugin validate plugins/recallum-memory`
      Then plugin.json validation reports no errors
      And no error is attributed to plugin.json

  Rule: The configured endpoint is HTTPS with the exact /mcp/ path, except plain HTTP for loopback hosts

    Scenario Outline: The recallum server's serverUrl follows the endpoint rule
      Given the "recallum" server entry's serverUrl is "<url>"
      When the serverUrl is checked against the endpoint rule
      Then the endpoint rule <result>

      Examples:
        | url                           | result  |
        | https://api.example.com/mcp/  | is satisfied |
        | http://localhost:8000/mcp/    | is satisfied |
        | http://127.0.0.1:8000/mcp/    | is satisfied |
        | http://api.example.com/mcp/   | is violated  |
        | https://api.example.com/mcp   | is violated  |

  Rule: The OQ4 runtime probe records exactly one of three outcomes, each with evidence

    Scenario: Probe outcome "honoured" when the server appears without native config
      Given an isolated HOME with no native "~/.gemini/config/mcp_config.json" entry for "recallum"
      And the bundle "plugins/recallum-memory", containing "mcp_config.json", is installed via `agy plugin install`
      When the running CLI's active MCP servers are inspected
      Then the "recallum" server appears among the active MCP servers
      And the probe outcome is recorded as "honoured" with the supporting command output

    Scenario: Probe outcome "not honoured" when the server does not appear
      Given an isolated HOME with no native "~/.gemini/config/mcp_config.json" entry for "recallum"
      And the bundle "plugins/recallum-memory", containing "mcp_config.json", is installed via `agy plugin install`
      When the running CLI's active MCP servers are inspected
      Then the "recallum" server does not appear among the active MCP servers
      And the probe outcome is recorded as "not honoured" with the supporting command output

    Scenario: Probe outcome "inconclusive" requires a genuine interactive-mode attempt with a transcript and a named blocker
      Given an isolated HOME with no native "~/.gemini/config/mcp_config.json" entry for "recallum"
      And the bundle "plugins/recallum-memory", containing "mcp_config.json", is installed via `agy plugin install`
      When at least one interactive-mode attempt is made to inspect the running CLI's active MCP servers
      And that attempt is recorded as a transcript of what was tried and what was observed
      And a specific technical blocker prevents determining whether the server appears
      Then the probe outcome is recorded as "inconclusive" with the transcript and the named blocker

    Scenario: A headless-only attempt does not qualify the probe as inconclusive
      Given an isolated HOME with no native "~/.gemini/config/mcp_config.json" entry for "recallum"
      And the bundle "plugins/recallum-memory", containing "mcp_config.json", is installed via `agy plugin install`
      When only headless or non-interactive invocations are attempted to inspect the running CLI's active MCP servers
      And no interactive-mode attempt is made
      Then the probe outcome must not be recorded as "inconclusive"

  Rule: No secret value is committed to the repository

    Scenario: The bundled config uses a placeholder or accepted interpolation scheme, never a literal secret
      Given "plugins/recallum-memory/mcp_config.json" is committed to the repository
      When the file's Authorization header value is inspected
      Then the value is a non-secret placeholder or an interpolation scheme already accepted by `agy plugin validate`
      And no literal secret value appears in the committed file
