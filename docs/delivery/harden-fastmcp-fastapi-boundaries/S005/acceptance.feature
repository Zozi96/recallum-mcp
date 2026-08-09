Feature: Harden FastMCP and FastAPI lifecycle and dependency boundaries

  Scenario Outline: Acquired resources are cleaned up exactly once in reverse order
    Given the process acquired resources in the order "first", "second", "third"
    And each acquired resource registered its cleanup immediately after acquisition
    When the lifecycle ends because of <ending>
    Then the cleanup callbacks are called once each in the order "third", "second", "first"

    Examples:
      | ending                               |
      | normal shutdown                      |
      | startup failure after partial acquisition |
      | cancellation                         |
      | partial initialization                |

  Scenario: Readiness probes are concurrent and bounded by configurable defaults
    Given readiness probes use a configurable per-probe timeout defaulting to 2 seconds
    And the whole readiness request uses a configurable timeout defaulting to 3 seconds
    When readiness is requested with at least two slow or hung dependencies
    Then the probes run concurrently
    And each probe is stopped within 2 seconds by default
    And the request completes within 3 seconds by default
    And the response is a stable HTTP 503 with no sensitive dependency details
    And no resources or probe tasks leak

  Scenario Outline: Database dependency phases are bounded
    Given a database operation is waiting during the <phase> phase
    When the dependency does not complete before its configured timeout
    Then that phase stops within its configured timeout
    And the failure does not leak resources

    Examples:
      | phase                         |
      | pool checkout                 |
      | connection establishment      |
      | command execution             |
      | hung dependency               |

  Scenario: Health remains available while dependencies fail
    Given the ASGI process is alive
    And one or more dependencies are unavailable or failing
    When the health endpoint is requested
    Then the response is HTTP 200
