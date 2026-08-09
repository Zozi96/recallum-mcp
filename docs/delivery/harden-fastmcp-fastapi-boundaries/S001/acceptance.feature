Feature: Authenticate the MCP transport boundary
  The MCP service protects transport access before establishing a session or
  exposing capabilities, while preserving authenticated user isolation.

  Background:
    Given the MCP service is publicly reachable through its supported application path
    And two active users have distinct valid bearer credentials

  Rule: Requests without valid transport authentication are rejected before MCP work

    Scenario: Missing bearer credentials are rejected without a session
      Given a client sends an MCP request without bearer credentials
      When the service receives the request
      Then it responds with HTTP 401
      And the response body is empty
      And the response includes `WWW-Authenticate: Bearer`
      And no MCP session or capabilities are created

    Scenario Outline: Invalid or revoked bearer credentials are rejected before dispatch
      Given a client sends an MCP request with a <credential> bearer credential
      When the service receives the request
      Then it responds with HTTP 401
      And the response identifies OAuth error `invalid_token`
      And no MCP session is created
      And the request is not dispatched to an MCP operation

      Examples:
        | credential |
        | invalid    |
        | revoked    |

  Rule: Valid credentials authenticate the MCP interaction as their owner

    Scenario: A valid bearer initializes and discovers MCP capabilities
      Given a client uses the first user's valid bearer credential
      When the client initializes an MCP session and discovers tools and resources
      Then the session is established successfully
      And the advertised capabilities are returned
      And the capabilities are associated with the first user

    Scenario: A valid bearer can invoke an authorized tool
      Given a client uses the first user's valid bearer credential
      When the client invokes an available MCP tool
      Then the tool operation succeeds for the first user
      And telemetry records the operation for the first user

    Scenario: A valid bearer can read an authorized resource
      Given a client uses the first user's valid bearer credential
      When the client reads an available MCP resource belonging to that user
      Then the resource is returned
      And telemetry records the operation for the first user

    Scenario: A valid bearer can list available resources
      Given a client uses the first user's valid bearer credential
      When the client lists the available MCP resources
      Then the resource list is returned
      And the list does not disclose the second user's resources

    Scenario: A valid bearer can query the MCP service
      Given a client uses the first user's valid bearer credential
      When the client sends an MCP ping request
      Then the service responds successfully
      And no user data is changed

  Rule: Token revocation takes effect according to the configured verification cache

    Scenario: Revocation is immediate when verification caching is disabled
      Given a client has successfully authenticated with the first user's bearer credential
      And transport verification caching is disabled
      When that credential is revoked and the client sends the next MCP request
      Then the request responds with HTTP 401
      And the response identifies OAuth error `invalid_token`

    Scenario: Revocation is delayed only within the configured cache window
      Given a client has successfully authenticated with the first user's bearer credential
      And transport verification caching has an exact positive time-to-live
      When that credential is revoked and the client sends a request within that time-to-live
      Then the cached authentication remains valid
      When the client sends the first request after that time-to-live expires
      Then the request responds with HTTP 401
      And the response identifies OAuth error `invalid_token`

  Rule: Authenticated users cannot access one another's data

    Scenario: A user cannot read another user's resource
      Given the first and second users own distinct MCP resources
      And a client uses the first user's valid bearer credential
      When the client attempts to read the second user's resource
      Then the resource is not returned
      And the second user's data is not disclosed

    Scenario: A user cannot mutate another user's data
      Given the first and second users own distinct MCP data
      And a client uses the first user's valid bearer credential
      When the client attempts to mutate the second user's data
      Then the mutation is rejected
      And the second user's data remains unchanged
