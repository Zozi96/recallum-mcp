# ADR 0002: Centralize password length validation in `password_model`

## Status
Accepted

## Context
S004 added password caps across login, self-service key issue, and admin key issue. Each request model repeated an identical `@model_validator` checking `len(password) > 256`, while `password_model` already rebuilt the field for the configured cap. That duplicated the same security rule three times with a hardcoded ceiling.

## Decision
Encode the configured cap only in `password_model` via `AfterValidator`, preserving the public message `password is too long` and omitting OpenAPI `maxLength`. Remove the three copy-paste model validators. Keep the login handler's final HTTP 422 guard and the ASGI body-limit pre-check.

## Alternatives considered
- Keep Field `max_length` plus schema stripping: rejected; Field errors diverge from the public message.
- Also remove the login HTTPException: deferred; it remains a last-line guard without changing the happy path.

## Consequences
Configured and default caps share one validator factory. Future password-bearing models must use `password_model` rather than re-adding local validators.
