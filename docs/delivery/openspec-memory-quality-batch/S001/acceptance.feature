Feature: Align the documented MCP tool surface with the eleven canonical tools
  The public documentation names exactly the eleven canonical MCP tools, and a
  deterministic no-network gate enforced by the fast CI lane prevents silent
  divergence from that surface.

  Background:
    Given the canonical MCP tool surface is the eleven tools:
      | name             |
      | remember         |
      | remember_batch   |
      | recall           |
      | context          |
      | get_memory       |
      | list_memories    |
      | update           |
      | merge_memories   |
      | related_memories |
      | reconfirm        |
      | forget           |

  Rule: The README presents the complete canonical tool surface

    Scenario: The README names all eleven canonical tools accurately
      When an operator reads the MCP tool feature list in the README
      Then all eleven canonical tool names appear in it
      And it states no incorrect tool count
      And it does not omit related_memories or reconfirm

  Rule: A client guide that enumerates the tools names exactly the canonical set

    Scenario: The client guide enumeration is exactly the canonical set
      Given the client guide enumerates the MCP tools
      When an operator reads that enumeration
      Then all eleven canonical tool names appear in it
      And no tool names outside the canonical set appear in it

  Rule: A deterministic no-network check gates the documented surface

    Scenario: The check passes when both documents match the canonical set
      Given the README and the client guide enumerate exactly the canonical tool set
      When the fast gate runs the tool-surface check locally without network access
      Then the check passes

    Scenario: Reverting the README to nine tools fails the check with a named mismatch
      Given the README is reverted to claim nine MCP tools and omit related_memories and reconfirm
      When the fast gate runs the tool-surface check locally without network access
      Then the check fails
      And the failure names the affected document and the mismatched tool names

    Scenario Outline: A mismatched client guide enumeration fails the check
      Given the client guide enumerates the MCP tools but <mismatch>
      When the fast gate runs the tool-surface check locally without network access
      Then the check fails
      And the failure names the client guide

      Examples:
        | mismatch                                       |
        | omits the canonical tool related_memories      |
        | omits the canonical tool reconfirm             |
        | includes a tool name outside the canonical set |

    Scenario: A client guide without a tool enumeration passes the check
      Given the client guide does not enumerate the MCP tools
      When the fast gate runs the tool-surface check locally without network access
      Then the check passes

  Rule: The fast CI lane enforces the documented surface

    Scenario: A pull request that reintroduces a mismatch fails the fast lane
      Given the fast CI lane gates documentation with the tool-surface check
      When a pull request reintroduces a mismatch between a document and the canonical tool set
      Then the fast lane job fails

    Scenario: An aligned branch passes the fast lane
      Given the fast CI lane gates documentation with the tool-surface check
      When a pull request carries documents aligned with the canonical tool set
      Then the fast lane job passes

  Rule: Delivery records the induced failure and the aligned pass

    Scenario: The delivered evidence records the induced failure followed by the aligned pass
      Given the documentation alignment is delivered
      When its recorded fast-gate evidence is reviewed
      Then the record shows the local fast gate failing on the reverted nine-tool README
      And the record shows the same gate passing on the aligned tree
