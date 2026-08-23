Feature: Register Recallum with Antigravity CLI through the installer
  The installer detects `agy` on PATH, installs the plugin bundle, and
  separately writes the native global MCP config so tools stay available
  even if the bundle path proves not to be honoured at runtime. Because
  Antigravity performs no environment-variable expansion, the API key is
  written into that file literally, so the write must be safe: private
  file mode, a retained backup of whatever was there before, and no
  spillage into the workspace-scope config location.

  Background:
    Given a fake $HOME isolated from the operator's real home directory
    And the operator runs `./install.sh` from the plugin's `scripts` directory

  Rule: Antigravity is only targeted when `agy` is actually present

    Scenario: Installing with agy on PATH runs the plugin install and writes the native config
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity`
      Then the fake `agy` was invoked as `agy plugin install <bundle dir>` with the plugin bundle directory
      And `~/.gemini/config/mcp_config.json` exists under the fake $HOME
      And its `mcpServers.recallum.serverUrl` value ends exactly in `/mcp/`
      And its `mcpServers.recallum.headers.Authorization` value is present

    Scenario: Installing without agy on PATH fails closed and writes nothing
      Given no `agy` executable is on PATH
      When the operator runs `./install.sh --target antigravity`
      Then the command exits with a non-zero status
      And the error output names `agy` as the missing requirement
      And `~/.gemini/config/mcp_config.json` does not exist under the fake $HOME

    Scenario: Auto-detection includes Antigravity only when agy is present
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target auto`
      Then the fake `agy` was invoked as `agy plugin install <bundle dir>` with the plugin bundle directory

    Scenario: Auto-detection skips Antigravity when agy is absent
      Given no `agy` executable is on PATH
      When the operator runs `./install.sh --target auto` with at least one other supported CLI on PATH
      Then the command exits with a zero status
      And `~/.gemini/config/mcp_config.json` does not exist under the fake $HOME

  Rule: The native config write is safe for a literal, unrecoverable secret

    Scenario: The written native config file is private
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity`
      Then `~/.gemini/config/mcp_config.json` under the fake $HOME has file mode `0600`

    Scenario: A pre-existing native config is backed up before being rewritten
      Given a fake `agy` executable is on PATH that records its own invocations
      And `~/.gemini/config/mcp_config.json` under the fake $HOME already contains a `recallum` entry with a different `serverUrl`
      When the operator runs `./install.sh --target antigravity`
      Then a backup file distinct from `~/.gemini/config/mcp_config.json` exists under the fake $HOME after the run
      And the backup file's content equals the pre-run content of `~/.gemini/config/mcp_config.json`

    Scenario: A pre-existing native config with unrelated servers keeps those servers after the merge
      Given a fake `agy` executable is on PATH that records its own invocations
      And `~/.gemini/config/mcp_config.json` under the fake $HOME already contains an `mcpServers.other-tool` entry
      When the operator runs `./install.sh --target antigravity`
      Then `~/.gemini/config/mcp_config.json` under the fake $HOME still contains the `mcpServers.other-tool` entry unchanged
      And its `mcpServers.recallum.serverUrl` value ends exactly in `/mcp/`

    Scenario: Re-running with an already-matching entry makes no reported change
      Given a fake `agy` executable is on PATH that records its own invocations
      And `~/.gemini/config/mcp_config.json` under the fake $HOME already contains a `recallum` entry matching the target `--url`
      When the operator runs `./install.sh --target antigravity` a second time with the same `--url`
      Then the run reports the Antigravity native entry as already matching and unchanged
      And no new backup file is created by this second run

    Scenario Outline: A URL failing the shared endpoint rule is rejected before any file is written
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity --url <url>`
      Then the command exits with a non-zero status
      And `~/.gemini/config/mcp_config.json` does not exist under the fake $HOME

      Examples:
        | url                                    |
        | http://example.com/mcp/                |
        | https://example.com/other               |
        | https://example.com/mcp/extra           |

    Scenario: A loopback HTTP URL is accepted like it is for other clients
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity --url http://127.0.0.1:8080/mcp/`
      Then `~/.gemini/config/mcp_config.json` under the fake $HOME has `mcpServers.recallum.serverUrl` equal to `http://127.0.0.1:8080/mcp/`

  Rule: The run-end summary reports the Antigravity result

    Scenario: The summary names Antigravity when it was installed
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity`
      Then the run's summary output includes a line naming Antigravity

  Rule: The installer never touches the workspace-scope config location

    Scenario: No workspace-scope file is created by any Antigravity-inclusive run
      Given a fake `agy` executable is on PATH that records its own invocations
      And the current working directory has no `.agents` directory
      When the operator runs `./install.sh --target antigravity`
      Then no `.agents/mcp_config.json` file exists anywhere under the current working directory after the run

    Scenario: A pre-existing workspace-scope file is left byte-for-byte untouched and its contents are never read
      Given a fake `agy` executable is on PATH that records its own invocations
      And a file `.agents/mcp_config.json` already exists in the current working directory containing malformed, non-JSON, poisoned content
      When the operator runs `./install.sh --target antigravity`
      Then the run's exit status, stdout, and stderr are identical to the same run with `.agents/mcp_config.json` absent, aside from the added warning line below
      And the file `.agents/mcp_config.json` still contains exactly its original poisoned content byte-for-byte
      And the run emits a warning naming `.agents/mcp_config.json` as a workspace-scope config outside this installer's supported registration path

  Rule: The test fixture never touches the operator's real environment

    Scenario: The test run leaves the repository working tree clean
      Given a fake `agy` executable is on PATH that records its own invocations
      When the operator runs `./install.sh --target antigravity` inside the test fixture's fake $HOME
      Then `git status` in the repository afterward reports no tracked file as modified
