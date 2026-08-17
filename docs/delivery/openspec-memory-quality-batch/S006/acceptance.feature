Feature: Usage vote in recall ranking with reproducible evaluation
  Ranking evaluation is a documented, reproducible command over a versioned
  synthetic dataset, the recall usage vote reorders only within its cap and
  never across owners, and the production default stays at zero regardless of
  the experiment outcome.

  Rule: The ranking evaluation command is documented and distinct from the workflow evaluator

    Scenario: The documentation states the ranking evaluation command
      When an operator reads the ranking evaluation documentation
      Then it states the exact command that runs the ranking evaluation
      And it states that the command is separate from the workflow evaluator

  Rule: The eval report covers MRR, recall@k, and tagged misses only

    Scenario: The eval report contains MRR, recall@k, and a tagged misses list and no workflow metrics
      Given the versioned ranking dataset with query tags
      When an operator runs the documented ranking evaluation command against the dataset
      Then the report contains an MRR value
      And the report contains a recall@k value
      And the report contains a misses list annotated by query tag
      And the report contains no workflow-evaluator metrics

    Scenario: The eval command accepts a usage-weight override
      When an operator runs the documented ranking evaluation command with a usage-weight override
      Then the run uses the identical dataset and configuration as a run without the override
      And the report records the usage-weight value that was applied

  Rule: The ranking dataset is versioned, tagged, and synthetic-only

    Scenario: The ranking dataset is versioned, tagged, and synthetic-only
      When an operator inspects the versioned ranking dataset
      Then each query in it carries a tag and the expected keys
      And the dataset contains only synthetic fixture content and no production data

  Rule: The eval runs dry and reproducibly

    Scenario: Repeated runs with the same dataset and configuration produce identical reports
      When an operator runs the documented ranking evaluation command twice with the same dataset and configuration
      Then both runs produce the same report

    Scenario: The eval run leaves stored memories untouched
      When an operator runs the documented ranking evaluation command
      Then no stored memory is created, modified, or retired as a result

  Rule: At usage weight zero the recall ranking preserves the existing ordering

    Scenario: Weight zero leaves the recall ordering unchanged
      Given the usage vote in recall is configured with weight zero
      When a memory owner recalls memories for a query
      Then the returned ranking matches the ordering produced by relevance alone

  Rule: A positive usage weight reorders near-ties within the cap

    Scenario: Higher usage reorders candidates the relevance score placed close together
      Given the usage vote in recall is configured with a weight above zero
      And two of the owner's active memories that relevance scored close together for a query have different usage
      When the owner recalls memories for that query
      Then the higher-usage memory ranks above the lower-usage memory

    Scenario: The cap keeps a clearly better match on top
      Given the usage vote in recall is configured with a weight above zero
      When a memory owner recalls memories for a query where one active memory is a clearly better semantic or exact-text match
      Then the clearly better match ranks first regardless of the usage of the other candidates

    Scenario Outline: Only the owner's active memories participate in recall ranking
      Given the usage vote in recall is configured with a weight above zero
      And the owner has active memories that match a query, with varying usage
      And <non-participant> also matches the query
      When the owner recalls memories for that query
      Then the returned ranking contains only the owner's active memories
      And <non-participant> never appears in the returned ranking

      Examples:
        | non-participant                                     |
        | a retired memory of the owner with high usage       |
        | an active memory of a second owner with high usage  |

  Rule: The experiment record keeps the production default at zero

    Scenario: The experiment record compares baseline and candidate runs side by side
      When an operator reads the ranking experiment record
      Then it shows a baseline run at usage weight zero
      And it shows at least one candidate run at a usage weight above zero
      And it presents MRR, recall@k, and misses for the baseline and candidate runs side by side

    Scenario: The experiment record keeps the production default at zero with no config change
      When an operator reads the ranking experiment record
      Then the record states the decision to keep the production default usage weight at zero
      And the record states that no configuration change ships a non-zero default

    Scenario: The shipped configuration keeps the usage vote off by default
      When an operator inspects the shipped configuration
      Then the default usage weight is zero
      And no experiment candidate value is shipped as the default
