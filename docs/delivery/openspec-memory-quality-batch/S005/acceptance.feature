Feature: Benchmark parity with SessionStart guidance, clean dry-run, and observed-run completion
  The benchmark assumptions and the SessionStart and skill guidance name the same
  context, recall, and capture tools and the same fail-open behavior per client; a
  dry run with no agent omits cleanly; and the observed-run task completes under
  exactly one of two stated outcomes, never conditionally and never as a skip.

  Background:
    Given the benchmark runbook and versioned matrix from the benchmark-operations story are available

  Rule: The parity note lists per-client tool names and fail-open behavior

    Scenario Outline: The parity note names the expected discovery tools and confirms guidance parity for <client>
      When an operator reads the parity note for <client>
      Then it lists the tool names the benchmark expects to discover for that client
      And it states that the SessionStart and skill text for that client name the same context, recall, and capture tools
      And it states that the SessionStart and skill text for that client describe the same fail-open behavior, a session that continues without blocking when the memory server is unavailable

      Examples:
        | client       |
        | Cursor       |
        | Codex        |
        | Claude Code  |
        | Grok Build   |

  Rule: A review finding is reflected either in the note or in a guidance diff

    Scenario: A parity review that finds no mismatch records it and produces no diff
      Given the parity review found no mismatch between the benchmark assumptions and the SessionStart and skill text
      When the parity note is written
      Then the note states that no mismatch was found
      And no diff to the skill, hook, or docs is produced

    Scenario Outline: A parity review that finds a mismatch aligns the guidance through a diff
      Given the parity review found <mismatch> between the benchmark assumptions and the SessionStart or skill text for a client
      When an operator reviews the guidance diff produced by the review
      Then the diff changes only the skill, hook, or docs
      And the corrected SessionStart and skill text name the same context, recall, and capture tools the benchmark expects
      And the corrected text describes the same fail-open behavior when the memory server is unavailable

      Examples:
        | mismatch                      |
        | a tool-name mismatch          |
        | a fail-open behavior mismatch |

  Rule: A dry run without an agent omits cleanly

    Scenario: The dry run with no agent configured reports omitted runs and no fabricated success
      Given no agent is configured on the host
      When an operator runs the harness dry run
      Then the report marks every run as omitted
      And the report contains no agent traces
      And the report contains no success values derived from fixture traces

  Rule: The observed-run task completes under exactly one of two stated outcomes

    Scenario: Installed clients yield a versioned per-client and per-policy report from observed runs
      Given at least one client is installed and configured on the operating host
      And another supported client is unconfigured on the host
      When an operator completes the observed-run task
      Then a versioned per-client and per-policy report exists
      And the report derives its results from real observed runs
      And the unconfigured client is marked as an explicit gap
      And the report states the installed-client outcome as the basis for its completion

    Scenario: No installed client yields a documented gap plus the retained dry run, recorded as a pass
      Given no client is installed on the operating host
      When an operator completes the observed-run task
      Then a gap record documents that no client was available on the host
      And the clean dry run is retained as the observed-run evidence
      And the task is recorded as complete and passing, not skipped

  Rule: The observed-run record reports the host inventory unconditionally

    Scenario: The observed-run record reports the host's client inventory under both outcomes
      When an operator completes the observed-run task
      Then the observed-run record reports the host's client inventory
      And the report is produced under both outcomes rather than being made conditional on a client being installed
