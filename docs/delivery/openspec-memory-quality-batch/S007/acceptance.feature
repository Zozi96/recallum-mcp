Feature: Scalable bounded graph edges with honest edge truncation
  A memory owner can request a graph projection or related neighbours whose edges
  are bounded per node, respect the minimum similarity and the embedding model,
  and report the pre-cap qualifying pair count. An operator can route the
  projection to the scalable path with an explicit flag or with a node-count
  threshold, while the pairwise path stays the effective default.

  Rule: The pairwise path remains the default and preserves the existing output

    Scenario: With neither mechanism active the projection matches the pairwise path
      Given a memory owner with a small corpus of active memories
      And the activation flag is off
      And the active node count is below the activation threshold
      When the owner requests a graph projection of their memories
      Then the response contains the same edges as the pairwise path produces for that corpus
      And the response reports the same edge_total and edges_truncated as the pairwise path
      And the response reports the same total and truncated as the pairwise path

  Rule: Both activation mechanisms independently route to the scalable path

    Scenario Outline: <activation> routes the projection to the scalable path
      Given a corpus in which one node has more qualifying neighbours than the per-node bound
      And <activation>
      When the owner requests a graph projection of their memories
      Then only the strongest edges within the per-node bound are returned
      And the response reports edges_truncated true
      And the response reports edge_total equal to the number of qualifying pairs before the per-node bound

      Examples:
        | activation                                                          |
        | the activation flag is set while the active node count is below the threshold |
        | the active node count exceeds the threshold while the activation flag is off   |

  Rule: The scalable path honors similarity and the embedding model and never invents edges

    Scenario: Every returned edge meets the minimum similarity and connects same-model embeddings
      Given a corpus with pairs above and below the minimum similarity and memories embedded by two different models
      And the scalable path is active
      When the owner requests a graph projection of their memories
      Then every returned edge connects two memories whose similarity is at least the minimum
      And every returned edge connects two memories embedded by the same model

    Scenario: A node with only below-threshold candidate relations gains no invented neighbours
      Given a corpus with a node whose qualifying candidate relations are all below the minimum similarity
      And the scalable path is active
      When the owner requests a graph projection of their memories
      Then the response contains no edge incident to that node

  Rule: Edge truncation is reported honestly

    Scenario: A corpus within the per-node bound reports no truncation
      Given a corpus where every node's qualifying neighbours fit within the per-node bound
      And the scalable path is active
      When the owner requests a graph projection of their memories
      Then the response reports edges_truncated false
      And the response reports edge_total equal to the number of edges returned

  Rule: Related-neighbour requests share the bounded semantics

    Scenario Outline: Related neighbours honor the bound, the minimum similarity, and the model with <activation>
      Given a memory owner with an active memory that has more qualifying candidate neighbours than the per-node bound
      And <activation>
      When the owner requests the related neighbours of that memory
      Then at most the per-node bound of neighbours is returned
      And every returned neighbour has at least the minimum similarity to the memory
      And every returned neighbour is embedded by the same model as the memory

      Examples:
        | activation                                                          |
        | the activation flag is set while the active node count is below the threshold |
        | the active node count exceeds the threshold while the activation flag is off   |

  Rule: The graph suites stay green and the runbook documents activation

    Scenario: The graph suites assert parity and truncation and pass
      When the graph test suites run
      Then the small-fixture parity tests compare the scalable and pairwise edge sets and both new signals exactly
      And the truncation tests cover the dense component
      And the graph unit and integration suites pass

    Scenario: The runbook documents the activation conditions and the pairwise default
      When an operator reads the graph operations runbook
      Then it states that the scalable path is activated by the explicit operator flag and/or by node volume above the threshold
      And it states that the default deployment keeps the pairwise path
