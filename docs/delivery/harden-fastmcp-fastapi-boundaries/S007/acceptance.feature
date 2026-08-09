Feature: Harden FastAPI and FastMCP boundaries
  As an operator
  I want request observability and administration boundaries to be safe and predictable
  So that telemetry and administration remain trustworthy under supported deployment conditions

  Scenario Outline: Emit exactly one redacted span for every FastAPI request outcome
    Given a request is received through the FastAPI <route kind> route
    When the request completes with <outcome>
    Then exactly one request span is emitted with the method, normalized route template, status, and latency
    And the span contains no UUIDs, query or body content, cookies, authorization or token values, email addresses, user identifiers, or other request content

    Examples:
      | route kind | outcome |
      | ordinary   | success |
      | ordinary   | an error |

  Scenario Outline: Emit exactly one redacted span for every mounted FastMCP request outcome
    Given a request is received through the mounted FastMCP <route kind> route
    When the request completes with <outcome>
    Then exactly one request span is emitted with the method, normalized route template, status, and latency
    And the span contains no UUIDs, query or body content, cookies, authorization or token values, email addresses, user identifiers, or other request content

    Examples:
      | route kind | outcome |
      | tool       | success |
      | tool       | an error |

  Scenario: Propagate only a valid inbound request identifier
    Given a request includes a valid inbound X-Request-ID
    When the request completes
    Then the emitted request span uses that request identifier
    And the request identifier is not replaced by a new identifier

  Scenario: Replace an invalid inbound request identifier
    Given a request includes an invalid X-Request-ID
    When the request completes
    Then the emitted request span uses a newly generated valid request identifier
    And the invalid identifier is not included in telemetry

  Scenario Outline: Redact sensitive request data from request spans
    Given a request contains <sensitive data>
    When the request completes
    Then the emitted request span contains no UUIDs, query or body content, cookies, authorization or token values, email addresses, user identifiers, or other request content

    Examples:
      | sensitive data |
      | a UUID         |
      | query and body content |
      | cookies and authorization credentials |
      | an email address and user identifier |

  Scenario: Reject an unsupported multi-worker deployment before serving traffic
    Given the service is configured with more than one worker
    When the service starts
    Then startup fails before any traffic is served

  Scenario: Start successfully with the supported single-worker topology
    Given the service is configured with one worker and one replica
    When the service starts
    Then startup succeeds
    And documented configuration evidence identifies one worker and one replica as the supported topology

  Scenario: Paginate the administrative user list at the default page size
    Given more than 100 users are available to an administrator
    When the administrator requests the first page without specifying a page size
    Then the page contains at most 100 users
    And the response includes the total number of matching users

  Scenario: Enforce the administrative page-size maximum
    Given more than 200 users are available to an administrator
    When the administrator requests a page size greater than 200
    Then the page contains at most 200 users
    And the response includes the total number of matching users

  Scenario: Aggregate administrative counts with constant queries and bounded memory
    Given an administrator requests a page of user counts
    When the page is produced for datasets of different sizes
    Then the number of data queries is constant for the page request
    And memory used for aggregation remains bounded independently of the total dataset size

  Scenario: Include zero-count users and detect count mismatches
    Given the administrative count sources include users with no events and inconsistent totals
    When the administrator requests the count page
    Then users with no events are included with a count of zero
    And a count mismatch is reported

  Scenario: Preserve tenant and user isolation in counts-only administration
    Given an administrator requests counts-only data for a tenant and user scope
    When the count page is produced
    Then every returned count belongs to that tenant and user scope
    And no count from another tenant or user is exposed

  Scenario: Present the paginated counts in the administrative UI
    Given an administrator opens the user-count administration view
    When the view loads a page of results
    Then the UI displays the page of counts and its total
    And the administrator can move between pages without losing the selected scope
