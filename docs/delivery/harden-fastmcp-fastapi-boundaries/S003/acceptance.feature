Feature: Safe and explicit MCP deployment routing

  Scenario: Production rejects wildcard host or origin configuration
    Given the service is configured for production
    When its allowed hosts or allowed origins contain a wildcard or an invalid value
    Then startup fails with a configuration validation error

  Scenario: Production rejects an invalid trusted proxy network
    Given the service is configured for production
    When its trusted proxy CIDR list contains an invalid CIDR
    Then startup fails with a configuration validation error

  Scenario: Production requires explicit routing and proxy limit settings
    Given the service is configured for production
    When a required host, origin, proxy, body, login, password, or rate budget is missing or invalid
    Then startup fails with a configuration validation error

  Scenario: Development permits explicit localhost routing
    Given the service is configured for development with explicit localhost hosts and origins
    When the service starts
    Then startup succeeds with those development routing values

  Scenario: The canonical MCP path is served directly
    Given a client requests the MCP service at "/mcp/"
    When the request is processed
    Then the client receives the MCP service response without a redirect

  Scenario: The non-canonical MCP path redirects without changing the request method
    Given a client requests the MCP service at "/mcp"
    When the request is processed
    Then the client receives an HTTP 308 response with relative Location "/mcp/"
    And the redirect does not reflect the request origin
    And the original HTTP method and request body remain eligible for forwarding

  Scenario: Invalid host or origin is rejected before MCP authentication or session creation
    Given a client sends an MCP request with a disallowed Host or Origin
    When the request is processed
    Then the request is rejected before authentication or session creation

  Scenario: Forwarded client address is derived from a trusted peer
    Given a request arrives from a trusted proxy with a valid X-Forwarded-For chain
    When the service determines the client address by walking the chain right-to-left
    Then it uses the first address that is not in a trusted proxy CIDR

  Scenario Outline: Untrusted or malformed forwarding data cannot spoof the client address
    Given a request arrives from <peer> with X-Forwarded-For value <forwarded>
    When the service determines the client address
    Then it ignores the untrusted or malformed forwarding data and falls back to the peer address

    Examples:
      | peer            | forwarded                 |
      | an untrusted IP | 203.0.113.10, 10.0.0.2    |
      | a trusted proxy | attacker, 10.0.0.2        |
      | a trusted proxy | 203.0.113.10, malformed   |

