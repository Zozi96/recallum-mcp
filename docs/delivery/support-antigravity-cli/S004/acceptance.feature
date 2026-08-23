Feature: Antigravity hook parity or documented gap
  Recallum's hook runtime injects memory context into every other supported
  client's session. Whether Antigravity CLI can receive the same treatment is
  gated on unresolved facts about its interactive hook dispatch and output
  contract. Exactly one outcome — parity or a documented gap — is recorded
  with reproducible evidence, and neither outcome is permitted to leave the
  user worse off than before this story: skill-based guidance keeps working
  either way.

  Background:
    Given the Recallum plugin bundle is installed for Antigravity CLI
    And a genuine interactive `agy` session is used for every dispatch attempt in this feature, not headless or print mode

  Rule: A shipped hooks.json must use Antigravity's single-object event schema

    Scenario: A hooks.json using Claude's array-of-groups schema is rejected
      Given a `hooks.json` where the `SessionStart` event maps to an array of hook groups
      When the plugin bundle is validated
      Then validation fails with an error naming `SessionStart` and an array/object schema mismatch
      And no hook is registered for `SessionStart`

    Scenario: A hooks.json using the single-object event schema validates
      Given a `hooks.json` where the `SessionStart` event maps to a single object containing a `hooks` list
      When the plugin bundle is validated
      Then validation reports the `hooks` component as found
      And no schema error is reported for `SessionStart`

  Rule: Interactive dispatch is determined by direct observation, not assumed

    Scenario: A dispatched SessionStart hook is observed in an interactive session
      Given a `hooks.json` in the single-object schema is installed for Antigravity CLI
      When an interactive `agy` session starts
      Then the hook process is invoked
      And the hook receives at least one of `conversationId`, `workspacePaths`, or `transcriptPath` on its input
      And the invocation is evidenced by a captured transcript or log excerpt

    Scenario: No hook dispatch is observed after a genuine interactive attempt
      Given a `hooks.json` in the single-object schema is installed for Antigravity CLI
      When an interactive `agy` session starts and no hook process is invoked
      Then the absence of dispatch is recorded together with what was attempted and what was observed
      And the recorded attempt is an interactive-mode attempt, not a headless or print-mode attempt

  Rule: Parity outcome — dispatch is observed and injected content reaches the model

    Scenario: The hook process identifies Antigravity as the running client
      Given a dispatched hook process is running under an interactive `agy` session
      When the hook inspects its environment for a client-identifying signal
      Then it identifies the client as Antigravity CLI
      And it selects the Antigravity tool-name prefix for that client

    Scenario: Injected context is confirmed to reach the model's visible context
      Given a dispatched `SessionStart` hook emits output on a field the Antigravity binary is confirmed to read
      When the interactive session continues past session start
      Then the injected content is observed in the model's visible context
      And the outcome is recorded as the parity outcome with the observed field name as evidence

  Rule: Gap outcome — no usable interactive dispatch or output field is found

    Scenario: The gap is recorded after a genuine interactive attempt finds no usable dispatch
      Given no `SessionStart` hook dispatch is observed under a genuine interactive `agy` attempt
      When the story's evidence is recorded
      Then the outcome is recorded as the gap outcome
      And the record states what was tried and what was observed
      And a headless-only or print-mode-only attempt is not accepted as satisfying this outcome

    Scenario Outline: Skills still load regardless of hooks.json presence when the gap outcome applies
      Given the gap outcome has been recorded for this story
      And <hooks_state>
      When the plugin bundle is validated
      Then the skills component is reported as processed
      And the reported skill count is unchanged from the count reported with no hooks.json present

      Examples:
        | hooks_state                                   |
        | no `hooks.json` is present in the plugin bundle |
        | a `hooks.json` is present but produces no dispatch |

  Rule: The outcomes are mutually exclusive and existing clients are unaffected

    Scenario: Only one of the two outcomes is recorded for this story
      Given the interactive dispatch investigation has concluded
      When the story's evidence is recorded
      Then exactly one of the parity outcome or the gap outcome is recorded
      And the unrecorded outcome's scenarios do not apply

    Scenario Outline: Existing clients keep their current hook behavior unchanged
      Given a dispatched hook process is running under <client>'s existing environment signal
      When the hook selects a client identity, a tool-name prefix, and an output field
      Then the selected identity, prefix, and output field match the behavior recorded before this story
      And no Antigravity-specific branch is exercised

      Examples:
        | client      |
        | Codex       |
        | Claude Code |
        | Grok Build  |
        | Cursor      |
