Feature: Diagnose Antigravity CLI registration in the doctor report
  The doctor reads the operator's Antigravity CLI configuration read-only and
  reports whether Recallum is correctly registered: server present, endpoint
  correct, credential present, config file private, and plugin listed. It
  never writes or repairs anything, and it never prints the literal secret.

  Background:
    Given a fake $HOME isolated from the operator's real home directory
    And the operator runs `recallum_doctor.py --json`

  Rule: An absent Antigravity install is silently omitted, not reported as unhealthy

    Scenario: No Antigravity config directory produces no Antigravity entry
      Given no `.gemini` directory exists under the fake $HOME
      When the doctor report is generated
      Then the report's `clients` object has no `Antigravity CLI` key
      And the report's exit code is `0`

  Rule: A correctly registered server produces no problems

    Scenario: A healthy native config with a private file mode reports no problems
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      When the doctor report is generated
      Then the report's `problems` array contains no entry mentioning `Antigravity`
      And the report's exit code is `0`

  Rule: The server entry must be present in the native Antigravity config

    Scenario: A missing recallum server entry is flagged
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME exists but its `mcpServers` object has no `recallum` entry
      And that file has mode `0600`
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the missing server
      And the report's exit code is `1`

  Rule: The serverUrl must be HTTPS with the exact /mcp/ path, except for loopback hosts

    Scenario Outline: A serverUrl that violates the endpoint rule is flagged
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `<url>` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the invalid endpoint
      And the report's exit code is `1`

      Examples:
        | url                                       |
        | http://example.com/mcp/                   |
        | https://example.com/other                 |
        | https://example.com/mcp/extra              |

    Scenario: A loopback serverUrl using plain HTTP is accepted
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `http://127.0.0.1:8080/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      When the doctor report is generated
      Then the report's `problems` array contains no entry mentioning `Antigravity`
      And the report's exit code is `0`

  Rule: An Authorization header must be present

    Scenario: A recallum entry with no Authorization header is flagged
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and no `headers.Authorization` value
      And that file has mode `0600`
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the missing authorization
      And the report's exit code is `1`

  Rule: The config file must be private, because the API key is stored literally

    Scenario: A world-readable config file is flagged
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0644`
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the file path with its permission problem
      And the report's exit code is `1`

    Scenario: A group-readable config file is flagged
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0640`
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the file path with its permission problem
      And the report's exit code is `1`

  Rule: The literal token is never printed, healthy or not

    Scenario Outline: The report never contains the literal token value
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `<url>` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `<mode>`
      When the doctor report is generated
      Then the report's raw JSON text does not contain `sk-live-abc123`

      Examples:
        | url                              | mode  |
        | https://recallum.zozbit.com/mcp/ | 0600  |
        | https://recallum.zozbit.com/mcp/ | 0644  |
        | http://example.com/mcp/          | 0600  |

  Rule: The plugin must be listed by agy when agy is on PATH, and the check is skipped otherwise

    Scenario: agy on PATH reporting the plugin listed shows the plugin as present
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      And a fake `agy` executable is on PATH whose `agy plugin list --json` output lists the `recallum-memory` import with `mcpServers` present
      When the doctor report is generated
      Then the report's `clients.Antigravity CLI.plugin_present` value is `true`
      And the report's `problems` array contains no entry mentioning the plugin

    Scenario: agy on PATH reporting the plugin missing flags it
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      And a fake `agy` executable is on PATH whose `agy plugin list --json` output does not list the `recallum-memory` import
      When the doctor report is generated
      Then the report's `problems` array contains an entry mentioning `Antigravity` and naming the plugin as not listed
      And the report's exit code is `1`

    Scenario: No agy on PATH skips the plugin-listed check without failing or raising
      Given `~/.gemini/config/mcp_config.json` under the fake $HOME contains a `recallum` entry with `serverUrl` `https://recallum.zozbit.com/mcp/` and `headers.Authorization` `Bearer sk-live-abc123`
      And that file has mode `0600`
      And no `agy` executable is on PATH
      When the doctor report is generated
      Then the doctor process completes without raising an exception
      And the report's `problems` array contains no entry mentioning the plugin
      And the report's exit code is `0`
