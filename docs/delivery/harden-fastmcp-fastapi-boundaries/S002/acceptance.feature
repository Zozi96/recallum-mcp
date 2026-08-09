Feature: Prevent internal error disclosure from MCP calls

  Background:
    Given an authenticated MCP client is connected through the supported transport

  Scenario: Unexpected tool failures expose only a generic client message
    Given a tool encounters an unexpected internal failure containing "INTERNAL-LEAK-MARKER"
    When the authenticated client invokes the tool
    Then the client observes a generic failure without "INTERNAL-LEAK-MARKER"

  Scenario Outline: Unexpected failure details are absent from all client-visible channels
    Given a tool fails with the internal value "<secret>"
    When the authenticated client invokes the tool
    Then the MCP response, client logs, and telemetry contain none of "<secret>"

    Examples:
      | secret                         |
      | https://ollama.internal:11434  |
      | connection refused             |
      | Traceback (most recent call)   |
      | INTERNAL-LEAK-MARKER           |

  Scenario: Embedding failures expose the approved public message
    Given the embedding service is unavailable while processing a memory request
    When the authenticated client invokes the memory tool
    Then the client observes the message "embedding service unavailable"

  Scenario: Embedding failure internals are redacted
    Given the embedding service fails with an internal URL, connection data, and stack details
    When the authenticated client invokes the memory tool
    Then the MCP response, client logs, and telemetry contain none of those internal details

  Scenario: Domain validation remains actionable
    Given the authenticated client submits a request that violates a documented domain rule
    When the corresponding tool processes the request
    Then the client observes an actionable validation message identifying the invalid input

  Scenario: Server diagnostics retain correlated safe failure context
    Given a tool encounters an unexpected internal failure
    When the failure is recorded by the service
    Then server diagnostics include the failure class, stack trace, and correlated request identifier
    And server diagnostics contain none of the authorization credential, API key, tool arguments, or user content

