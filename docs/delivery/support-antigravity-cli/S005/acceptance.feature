Feature: Document Antigravity CLI support and update client-list strings
  Recallum's documentation and client-list metadata describe Antigravity CLI
  as a supported client with the same structure, security warnings, and
  tool-name accuracy already given to Codex, Claude Code, Grok Build, and
  Cursor.

  Background:
    Given S001 through S003 have landed, establishing the Antigravity bundle,
      installer target, and doctor check
    And S004 has recorded its hook-parity-or-gap outcome for Antigravity CLI

  Rule: docs/clients.md documents Antigravity CLI on par with the other clients

    Scenario: docs/clients.md gains an Antigravity CLI section
      Given docs/clients.md as published
      When a reader looks for Antigravity CLI among the per-client sections
      Then docs/clients.md contains an H2 heading `## Antigravity CLI`
      And that section follows the same structure as the existing per-client
        sections: an install pointer and a native MCP config location

    Scenario: docs/clients.md states the exact install command and native config path
      Given the Antigravity CLI section of docs/clients.md
      When a reader looks for how to register Recallum with Antigravity CLI
      Then the section states the install command using `--target antigravity`
      And the section states the native config path
        `~/.gemini/config/mcp_config.json`

    Scenario: docs/clients.md warns that the API key is stored in cleartext
      Given the Antigravity CLI section of docs/clients.md
      When a reader looks for how the API key is stored on disk
      Then the section states plainly that the key is written in cleartext to
        `~/.gemini/config/mcp_config.json`, with no environment-variable
        expansion
      And the section states the file must be mode `0600`

  Rule: recallum-setup/SKILL.md documents standalone setup steps for Antigravity CLI

    Scenario: SKILL.md gains a Setup — Antigravity CLI section
      Given plugins/recallum-memory/skills/recallum-setup/SKILL.md as published
      When a reader looks for Antigravity CLI among the "Setup — <Client>"
        sections
      Then the file contains an H2 heading `## Setup — Antigravity CLI`

    Scenario: The Setup — Antigravity CLI section is followable without undocumented prerequisites
      Given the "Setup — Antigravity CLI" section of SKILL.md
      When a reader follows only the steps written in that section
      Then every step needed to reach a working, verified connection is
        present in the section
      And no step depends on an action not described anywhere in the section
        or the shared setup material above it

  Rule: The tool-name prefix table never silently omits Antigravity CLI

    Scenario: The tool-name prefix table names Antigravity CLI explicitly
      Given the tool-name prefix documentation in docs/clients.md
      When a reader looks for Antigravity CLI's entry
      Then the table or sentence explicitly names Antigravity CLI
      And it is not absent from the list of clients described there

  Rule: Hook-related documentation is consistent with S004's recorded outcome, not presumed

    Scenario: Every hook-related sentence about Antigravity CLI agrees with S004's recorded outcome
      Given S004's story file's acceptance-criteria outcome for Antigravity CLI
        hook support
      When a reviewer compares that recorded outcome against every
        hook-related sentence added by this story in docs/clients.md,
        SKILL.md, and the tool-name prefix table
      Then each such sentence states either the exact hook behavior S004
        recorded, or, if S004 recorded a gap, that hooks are not available
        for Antigravity CLI and skill-driven tool discovery is used instead
      And no sentence asserts hook parity that S004's recorded outcome does
        not support, and none asserts a gap that S004's recorded outcome
        contradicts

  Rule: README.md lists Antigravity CLI as a supported client

    Scenario: README.md's client table gains an Antigravity CLI row
      Given README.md as published
      When a reader looks at the client list/table naming Codex, Claude Code,
        Grok Build, and Cursor
      Then the table contains a row for Antigravity CLI
      And that row has values in the same columns as the other four rows

  Rule: Plugin metadata mentions Antigravity CLI wherever the other clients are enumerated

    Scenario: plugin.json's description and keywords mention Antigravity CLI
      Given plugins/recallum-memory/plugin.json as published
      When a reader looks at the description and keywords fields
      Then the description mentions Antigravity CLI alongside Codex, Claude
        Code, Grok Build, and Cursor
      And the keywords list includes an Antigravity CLI term

    Scenario: .grok-plugin/plugin-index.json mentions Antigravity CLI
      Given .grok-plugin/plugin-index.json as published
      When a reader looks at the top-level entry and the mcpServers
        description text
      Then both mention Antigravity CLI alongside the other supported clients

  Rule: Every surface that enumerates supported clients mentions Antigravity CLI

    Scenario Outline: A client-enumerating surface mentions Antigravity CLI
      Given <file> as published
      When a reader searches that file for a mention of Antigravity CLI
      Then the file contains at least one mention of Antigravity CLI

      Examples:
        | file                                                              |
        | docs/clients.md                                                   |
        | plugins/recallum-memory/skills/recallum-setup/SKILL.md            |
        | plugins/recallum-memory/README.md                                 |
        | README.md                                                         |
        | plugins/recallum-memory/plugin.json                               |
        | .grok-plugin/plugin-index.json                                    |
        | scripts/validate_external_mcp_clients.sh                         |

    Scenario: validate_external_mcp_clients.sh's required-clients line names Antigravity
      Given scripts/validate_external_mcp_clients.sh as published
      When a reader looks at the script's `Required clients:` echo line
      Then that line names Antigravity CLI alongside the clients it already
        named
      And this scenario makes no claim about the script's exit status or
        about it reading any documentation file
