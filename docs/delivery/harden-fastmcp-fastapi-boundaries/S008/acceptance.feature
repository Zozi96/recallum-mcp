Feature: Harden FastMCP and FastAPI boundaries
  The delivery checks prove the supported runtime and test boundaries.

  Scenario: Fast CI passes all required checks for the supported repository
    Given the repository is checked out at a candidate revision
    When the fast CI workflow completes
    Then the exact dependency lock is verified
    And Ruff completes successfully
    And the unit and plugin tests complete successfully
    And the OpenAPI snapshot is verified
    And the supported compose topology is validated
    And the Dokploy compose topology is not required for this check

  Scenario: Integration checks use PostgreSQL with pgvector and deterministic embeddings
    Given the integration environment uses PostgreSQL with pgvector
    And embedding generation is replaced by a deterministic stub
    When the integration checks exercise the supported behavior
    Then the checks complete successfully
    And the observed results are reproducible across runs

  Scenario: Transport checks exercise an external Granian process
    Given the supported application is started as an external real Granian process
    When the vertical transport checks exercise the application
    Then the checks observe the supported transport behavior through that process

  Scenario: The supported proxy image and version remain pinned
    Given the supported compose topology is used
    When its proxy configuration is inspected
    Then the proxy image and version are explicitly pinned

  Scenario: FastMCP latest-compatible support is reported separately from required checks
    Given a latest-compatible FastMCP candidate is selected
    When the compatibility policy check runs
    Then the candidate result is reported as a separate policy check
    And it does not alter the locked required-check result

  Scenario: Selected compatibility deprecations fail the test suite
    Given the web interaction tests use the supported current client compatibility
    When the test suite encounters a selected deprecation warning
    Then the test suite fails

