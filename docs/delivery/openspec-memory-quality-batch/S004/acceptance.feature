Feature: Benchmark operations runbook, client/policy matrix, and honest gap reporting
  An operator can run the observed agent-workflow benchmark guided by a runbook
  that states launch and configuration per supported client, consult a versioned
  matrix of clients, checkpoint policy, and synthetic scenarios, and trust that
  the report marks unconfigured or failed cells as gaps without substituting
  fixture traces for observed runs.

  Rule: The runbook documents launch, configuration, interpretation, and versioning

    Scenario: The runbook states launch commands and required configuration for each supported client
      When an operator reads the benchmark runbook
      Then it states an exact launch command for the observed benchmark
      And it states the required environment and configuration for Cursor
      And it states the required environment and configuration for Codex
      And it states the required environment and configuration for Claude Code
      And it states the required environment and configuration for Grok Build

    Scenario: The runbook defines omitted and incomplete and how to interpret them
      When an operator reads the benchmark runbook
      Then it defines the omitted outcome
      And it defines the incomplete outcome
      And it explains how an operator should interpret each of those outcomes

    Scenario: The runbook versioning list forbids persisting restricted content
      When an operator reads the benchmark runbook
      Then its versioning list requires persisting only bounded evaluation events
      And it forbids persisting prompts
      And it forbids persisting queries and reasoning
      And it forbids persisting credentials
      And it forbids persisting production memory content

  Rule: The versioned matrix covers the clients, the checkpoint policy, and the scenarios

    Scenario: The matrix covers every supported client, the checkpoint policy, and the scenarios with a stated repetition count
      When an operator reads the versioned benchmark matrix
      Then it lists the four supported clients Cursor, Codex, Claude Code, and Grok Build
      And it covers the current checkpoint policy
      And it covers every scenario in the synthetic scenario set
      And it states an explicit repetition count for each client, policy, and scenario combination

  Rule: The report marks unconfigured or failed cells as gaps and never uses fixture traces

    Scenario Outline: An unavailable or failed client cell is reported as a gap without success values
      Given the operator requests a benchmark report for <client condition>
      When the report is generated
      Then the client's cell is marked as a gap or omitted
      And the report contains no success value for that cell
      And the report contains no success value derived from fixture traces

      Examples:
        | client condition                          |
        | a client that is unconfigured on the host |
        | a client whose runs are all incomplete    |
        | a client that is absent from the host     |

    Scenario: A harness unit test locks the gap-reporting behaviour
      When the harness unit tests run
      Then a test asserts that an unconfigured client cell is reported as a gap or omitted
      And a test asserts that such a cell contains no success value derived from fixture traces

  Rule: Gap-fill scenarios are synthetic, justified, and leave the existing set runnable

    Scenario: A scenario added to fill a coverage gap is synthetic and carries a stated rationale
      When an operator reviews the synthetic scenario set
      Then every scenario added as a gap-fill is synthetic
      And the rationale for each added scenario is stated

    Scenario Outline: The pre-existing synthetic scenarios remain runnable unchanged
      When an operator runs the full synthetic scenario set
      Then the <scenario> scenario runs unchanged

      Examples:
        | scenario                      |
        | session-rotation-pivot        |
        | covered-by-initial-context    |
        | repeated-checkpoint-results   |
