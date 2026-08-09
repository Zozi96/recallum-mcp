Feature: Harden FastAPI and FastMCP boundaries

  Scenario: Protected operations are represented as cookie-authenticated in the API contract
    Given the API contract is published
    When a consumer inspects the authentication requirements for protected operations
    Then those operations require the API key cookie security scheme
    And the login operation remains publicly accessible

  Scenario: Search accepts authenticated JSON requests
    Given an authenticated consumer has searchable content
    When the consumer submits a search request with query text in a JSON body
    Then the search results are returned for that query

  Scenario: Deprecated search remains equivalent for one release
    Given an authenticated consumer has searchable content
    When the consumer uses the legacy search request during the one-release compatibility period
    Then the response authentication and search results are equivalent to the JSON search request
    And the response includes a Deprecation header
    And the response includes a Sunset header

  Scenario: Search query text is excluded from logs
    Given a consumer submits a search request containing query text
    When the request is processed
    Then the recorded logs do not contain the query text

  Scenario: Sensitive responses are not cached
    Given a consumer receives a sensitive response
    When the response is delivered
    Then it includes "Cache-Control: no-store"
    And it includes the legacy no-cache Pragma directive

  Scenario: OpenAPI publishes the required error responses
    Given the API contract is published
    When a consumer inspects the documented responses
    Then it includes responses for status codes 401, 403, 413, 422, 429, and 503

  Scenario: Startup reports an incompatible FastMCP version diagnostically
    Given the service is configured with an incompatible FastMCP version
    When the service starts
    Then startup fails with a diagnostic explaining the FastMCP compatibility problem

  Scenario: FastMCP installation resolves reproducibly within the supported range
    Given the project declares FastMCP support from version 3.4 inclusive to before version 4
    When dependencies are installed from the project lock
    Then an exact FastMCP version within that supported range is resolved
    And repeating the installation from the same lock resolves the same version

  Scenario: Compatibility contract passes for locked and latest-compatible FastMCP
    Given the project lock resolves a supported FastMCP version
    And a separate dependency resolution provides the latest version below 4
    When the application compatibility contract is exercised against both versions
    Then the application starts successfully and the compatibility contract passes for each version

  Scenario: Private FastMCP compatibility calls are isolated behind one seam
    Given the repository contains the three private FastMCP methods enumerated in the approved story
    When a deterministic architecture check examines their call sites
    Then all calls to those three methods are found behind the single compatibility seam
    And no calls to those methods are found elsewhere
