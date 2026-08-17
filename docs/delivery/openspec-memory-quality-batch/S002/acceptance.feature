Feature: Hygiene guidance for stale items, capture reconciliation, and the no-auto-resolve contract
  The actionable guidance demands an explicit resolution for every verified stale item and
  reconciles similar capture outcomes as merge-vs-update, while the server never resolves
  similar memories on its own.

  Rule: The stale-review prompt demands an explicit per-item resolution

    Scenario: The stale-review prompt demands exactly one of the four resolutions per verified item
      When an operator retrieves the stale-review prompt
      Then the returned text requires each verified stale item to conclude with exactly one of the four resolutions
      And the text names reconfirm, update, forget, and merge_memories as the only allowed resolutions for a verified stale item

    Scenario: The stale-review prompt offers no no-action terminal outcome
      When an operator retrieves the stale-review prompt
      Then the returned text does not describe merely having reviewed a stale item as a valid conclusion
      And every terminal outcome it offers for a verified stale item is one of the four resolutions

  Rule: The capture-scan prompt reconciles similar outcomes without auto-resolving

    Scenario: The capture-scan prompt requires reading the similar field
      When an operator retrieves the capture-scan prompt
      Then the returned text instructs reading the similar field on every remember and remember_batch outcome

    Scenario: The capture-scan prompt separates merge from update or forget
      When an operator retrieves the capture-scan prompt
      Then the returned text directs merging memories that restate or refine the same claim
      And it directs updating or forgetting a similar memory that contradicts the new claim or is incorrect

    Scenario: The capture-scan prompt leaves resolution to the agent, never to the server
      When an operator retrieves the capture-scan prompt
      Then the returned text instructs the agent to decide each similar outcome explicitly
      And the text does not instruct or expect the server to resolve similar memories automatically

  Rule: The prompt set stays exactly the three allowlisted prompts

    Scenario: Prompt discovery returns exactly the three allowlisted prompts
      When an operator discovers the available MCP prompts
      Then exactly session-start, capture-scan, and stale-review are returned

    Scenario: Registering a fourth prompt name fails startup validation
      Given the server allowlists exactly the three prompt names session-start, capture-scan, and stale-review
      When a fourth prompt name is registered
      Then startup validation fails

  Rule: The skill and SessionStart hook text carry the same hygiene criteria

    Scenario: The skill text requires explicit stale resolution and merge-vs-update reconciliation
      When an operator reads the recallum-memory skill
      Then the text requires every stale item to conclude with one of reconfirm, update, forget, or merge_memories
      And the text distinguishes merging restatements of the same claim from updating or forgetting contradictions and incorrect facts

    Scenario: The skill text keeps neighbourhood lookup optional and prefers reconfirm
      When an operator reads the recallum-memory skill
      Then the text presents related_memories as an optional neighbourhood step used only when needed
      And the text prefers reconfirm over re-storing identical content
      And the text names session-start, capture-scan, and stale-review as workflow shortcuts where MCP prompts are supported

    Scenario: The SessionStart hook text carries the stale-resolution and merge-vs-update criteria
      When a session starts with the recallum session hook
      Then the injected guidance requires every stale item to conclude with one of reconfirm, update, forget, or merge_memories
      And the injected guidance distinguishes merging restatements of the same claim from updating or forgetting contradictions

    Scenario: The SessionStart hook text keeps neighbourhood lookup optional and names the prompts
      When a session starts with the recallum session hook
      Then the injected guidance presents related_memories as an optional thematic-neighbourhood step
      And the injected guidance prefers reconfirm over re-storing identical content
      And the injected guidance names session-start, capture-scan, and stale-review as workflow shortcuts where MCP prompts are supported

  Rule: Contract tests assert the key guidance text

    Scenario: The contract tests pass while the hygiene text is present
      When the contract tests run against the delivered prompt, skill, and hook guidance
      Then they pass

    Scenario Outline: Removing required hygiene text fails the contract tests
      Given the contract tests assert the key hygiene guidance strings
      When the required text is removed from the <surface>
      Then the contract test for that surface fails

      Examples:
        | surface                 |
        | stale-review prompt     |
        | capture-scan prompt     |
        | recallum-memory skill   |
        | SessionStart hook text  |

  Rule: The server never auto-resolves reported similar memories

    Scenario Outline: Storing a memory with reported similar existing memories leaves them untouched
      When an agent stores a memory <via> and the server reports similar existing memories
      Then the new memory is persisted per the current rules
      And none of the similar memories is merged or forgotten by the server

      Examples:
        | via              |
        | remember         |
        | remember_batch   |

  Rule: The relevant suites stay green

    Scenario: The unit and plugin suites pass with the hygiene guidance delivered
      When the delivered guidance is verified against the relevant suites
      Then the unit suite passes
      And the plugin suite passes
