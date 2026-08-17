Feature: Hygiene self-service over HTTP: stale queue, bounded neighbours, and resolution mutations
  A session-authenticated memory owner can clean their corpus through the web
  self-service: a vector-free stale queue and thematic neighbours, and the
  reconfirm and merge mutations, while cross-user data and ownership stay isolated.

  Background:
    Given two session-authenticated memory owners, the first owner and the second owner, have distinct accounts

  Rule: The stale queue lists only the owner's stale memories and never exposes embedding vectors

    Scenario: The stale queue lists only the owner's own stale memories without embedding vectors
      Given the first owner has stale memories
      And the second owner has stale memories
      When the first owner lists their stale memories through the web self-service
      Then the response contains the first owner's stale memories
      And it contains none of the second owner's stale memories
      And the response contains no embedding vectors

  Rule: Thematic neighbours of an active memory are bounded and vector-free

    Scenario: The owner reads a bounded list of thematic neighbours without embedding vectors
      Given the first owner has an active memory with related active memories
      When the first owner requests the thematic neighbours of that memory through the web self-service
      Then the response returns the related active memories
      And the response contains no more than the defined neighbour bound
      And the response contains no embedding vectors

    Scenario Outline: Seeds that are not the owner's active memory yield no neighbours and no disclosure
      Given the first owner has an active memory
      And <seed>
      When the first owner requests the thematic neighbours of the seed memory through the web self-service
      Then the response returns no thematic neighbours
      And the response does not reveal whether the seed memory exists or whose it is

      Examples:
        | seed                                                    |
        | the seed memory does not exist                          |
        | the seed memory belongs to the second owner             |
        | the seed memory belongs to the first owner but is retired |

  Rule: Reconfirm mutates only the owner's own memories

    Scenario: The owner reconfirms their own memory and the change is visible on a subsequent read
      Given the first owner has an active memory
      When the first owner applies reconfirmation to that memory through the web self-service
      Then the operation succeeds
      And a subsequent read of the memory through the web self-service shows it was reconfirmed at the time of the request

    Scenario: The owner cannot reconfirm another owner's memory
      Given the first owner has an active memory
      And the second owner has an active memory
      When the first owner applies reconfirmation to the second owner's memory through the web self-service
      Then the operation is rejected
      And the second owner's memory remains unchanged

  Rule: Merge follows the domain semantics and stays owner-scoped

    Scenario: The owner merges two of their own active memories
      Given the first owner has two active memories
      When the first owner merges those two memories through the web self-service
      Then exactly one of the two memories remains active
      And the two merged memories are retired
      And the surviving memory is linked to the retired memories
      And the retired memories remain recoverable through the memory history

    Scenario: The owner cannot merge one of their memories with another owner's memory
      Given the first owner has an active memory
      And the second owner has an active memory
      When the first owner merges their own memory with the second owner's memory through the web self-service
      Then the operation is rejected
      And both memories remain unchanged

  Rule: The delivered surface is verified by the HTTP suites and the API contract snapshot

    Scenario: The self-service HTTP suites pass with the delivered surface
      When the delivered web self-service surface is verified against the HTTP test suites
      Then the stale listing, thematic neighbours, resolution mutation, and cross-user isolation tests all pass

    Scenario: The OpenAPI snapshot reflects the new self-service surface
      When an operator inspects the OpenAPI snapshot of the web API
      Then the snapshot documents the stale queue, thematic neighbours, reconfirm, and merge
      And the snapshot is consistent with the delivered web self-service behaviour
