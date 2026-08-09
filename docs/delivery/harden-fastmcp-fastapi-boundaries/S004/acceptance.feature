Feature: Enforce FastMCP and FastAPI request boundaries

  Scenario: Reject an oversized declared request body before parsing or session work
    Given an authenticated request is sent with a declared body size above the configured request-body limit
    When the request is received
    Then the request is rejected with status 413
    And its body is not parsed and no session is created or changed

  Scenario: Reject an oversized chunked or streaming request body before parsing or session work
    Given an authenticated request streams chunks whose combined size exceeds the configured request-body limit
    When the request is received
    Then the request is rejected with status 413
    And its body is not parsed and no session is created or changed

  Scenario: Reject a password exceeding the byte and length cap before credential processing
    Given an account operation contains a password exceeding the configured byte or length cap
    When the operation is received
    Then it is rejected as an invalid password
    And credential processing and account persistence do not occur

  Scenario: Evict rate-limit buckets deterministically while bounding stored keys
    Given requests resolve to expiring buckets by client IP and account identity
    When more than 10000 distinct bucket keys are created
    Then no more than 10000 bucket keys are retained
    And eviction is deterministic and expired buckets are removed

  Scenario: Throttle a client and identify when it may retry
    Given a client has exhausted its request allowance within the active rate-limit window
    When it makes another request
    Then the request is rejected with status 429
    And the response includes a Retry-After value for the remaining window

  Scenario: Avoid repeated account lookup while a client is throttled
    Given a client is currently rate limited
    When it makes repeated requests during the active window
    Then each request is rejected with status 429
    And no additional account lookup is performed for those requests

  Scenario: Allow a client again after its rate-limit window expires
    Given a client was rate limited and its rate-limit window has expired
    When it makes a request
    Then the request is processed under a fresh allowance

  Scenario Outline: Preserve strict integer rules for JSON body and FastMCP inputs
    Given a JSON body or FastMCP field requires an integer value
    When the request is received with <value>
    Then FastAPI JSON and FastMCP both <result>

    Examples:
      | value           | result                          |
      | a real integer  | accept it unchanged             |
      | true            | reject it as an invalid integer |
      | a floating value| reject it as an invalid integer |
      | a numeric string| reject it as an invalid integer |

  Scenario Outline: Preserve strict integer rules for FastAPI query parameters
    Given a FastAPI query parameter requires an integer value
    When the request is received with <value>
    Then the query boundary <result>

    Examples:
      | value                    | result                          |
      | a canonical digit string | accept it as that integer       |
      | true                     | reject it as an invalid integer |
      | a floating value         | reject it as an invalid integer |
      | a non-canonical string   | reject it as an invalid integer |
