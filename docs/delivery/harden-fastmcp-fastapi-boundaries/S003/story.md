# S003 — Make MCP deployment routing explicit and safe

## Actor
An MCP client and the reverse proxy forwarding requests to the application.

## Objective and motivation
Ensure `/mcp` routing, forwarded origins, and host checks work predictably behind the supported proxy.

## In scope
- A validated typed settings seam for all task 4.1 values: allowed hosts/origins, trusted proxy CIDRs, body limits, login/password limits, and rate budgets; production wildcards and invalid CIDRs are rejected.
- Stable handling of `/mcp` versus `/mcp/` without unsafe method/body/auth redirects.
- Explicit trusted host/origin and proxy-header behavior, including the right-to-left `X-Forwarded-For` trust algorithm.
- Tests for the deployed URL shape and forwarded request metadata.

S004 consumes the body, rate, and password settings for enforcement; this story owns only their validated configuration seam plus routing/proxy enforcement.

## Out of scope
- Replacing Traefik or changing production infrastructure ownership.
- Horizontal scaling or shared MCP session state (S007).
- `deploy/dokploy-compose.yml`, which is not an operational path.

## Mapped OpenSpec tasks
4.1, 4.2, 4.6

## Dependencies
S001 transport authentication; production proxy hostname/CIDR values remain an open deployment input.

## Acceptance criteria
- A request to `/mcp` receives exactly an explicit method-preserving HTTP 308 with relative `Location: /mcp/`; no externally derived absolute origin is emitted.
- A request to `/mcp/` is handled directly and receives no redirect.
- Configuration startup rejects production wildcards and invalid CIDRs, and accepts the documented typed host/origin, proxy CIDR, body-limit, login/password-limit, and rate-budget values.
- The right-to-left `X-Forwarded-For` algorithm trusts only configured proxy CIDRs and cannot be extended by hostile client-supplied addresses.
- Host and Origin values outside the allowlists, including hostile forwarded values, are rejected or ignored according to the documented policy.
- Proxy integration tests exercise the public URL shape.

## Affected surface
FastAPI app mounting, proxy/header configuration, deployment documentation, integration tests.

## Risks
Incorrect trust ranges can enable host spoofing; redirect changes can break existing clients.

## Validation expectations
Proxy-backed integration tests and manual deployment smoke test.

## Boundary crossings
Public network and auth boundaries; no data boundary.
