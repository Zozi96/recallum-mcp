Feature: Harden FastMCP and FastAPI boundaries

  Scenario: Required validation checks are recorded before completion
    Given the S009 validation record is being completed
    When the required checks are reviewed
    Then it records the exact fast CI, PostgreSQL integration, and vertical transport commands and results
    And completion is blocked when any required check is skipped or lacks real evidence

  Scenario: Conditional FastMCP policy is disclosed
    Given the FastMCP policy decision is not yet authoritative
    When the validation record is reviewed
    Then the candidate policy is identified as conditional
    And no FastMCP policy outcome is presented as implemented without explicit authority

  Scenario Outline: Supported clients are validated over the production transport boundary
    Given an authorized staging environment supplies the production host, origin, and trusted CIDR values
    And the <client> client is available for validation
    When the client connects over HTTPS to /mcp/
    Then the client completes the expected MCP interaction through the transport boundary
    And the validation records the exact command and result

    Examples:
      | client  |
      | Codex   |
      | Claude  |
      | Cursor  |

  Scenario: Missing production boundary values block client validation
    Given production host, origin, or trusted-CIDR values are not supplied by an authorized authority
    When HTTPS /mcp/ client validation is attempted
    Then validation is blocked
    And no guessed value is used as evidence

  Scenario: Hostile-input staging evidence is required
    Given an authorized staging environment is configured with the supplied boundary values
    When hostile inputs are exercised at the HTTPS /mcp/ boundary
    Then the staging smoke evidence records the exact inputs, commands, and observed results
    And completion is blocked if that evidence is absent

  Scenario: Pagination ownership and search deprecation are explicit
    Given pagination ownership or the GET-search deprecation date is not authoritative
    When the delivery record is reviewed
    Then completion is blocked until an owner and date are recorded by the responsible authority
    And no owner or date is invented

  Scenario: Deployment and monitoring authority is explicit
    Given deployment or monitoring requires an external authority
    When the delivery record is reviewed
    Then completion is blocked until real external evidence confirms the supported one-worker and one-replica topology
    And private endpoint monitoring evidence contains no secrets

