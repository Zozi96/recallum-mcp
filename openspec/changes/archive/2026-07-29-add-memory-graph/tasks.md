## 1. Backend graph projection

- [x] 1.1 Add validated graph node, neighbour and similarity limits to `MemoryLimits`, plus graph response value types that never serialize embeddings.
- [x] 1.2 Add a forced-RLS repository query that selects a deterministic bounded set of active memories, reports the full filtered total and computes unique cosine-similarity pairs only between embeddings with identical known provenance.
- [x] 1.3 Add a memory-service graph operation that applies scope/project/category filters, prunes strongest edges to the per-node neighbour cap, preserves isolated nodes and reports truncation and model mismatch.
- [x] 1.4 Extend repository and service tests for cross-project and cross-category edges, unrelated same-project nodes, bridge memories, incompatible models, deterministic truncation, degree caps and absence of foreign-user data.
- [x] 1.5 Add a representative bounded graph-query performance check and calibrate the initial server-owned node, neighbour and similarity defaults without relaxing their validated ceilings.

## 2. Authenticated web contract

- [x] 2.1 Add `GET /me/memory-graph` with session-derived identity, existing memory filters and a bounded limit, mapping the domain result to the graph response contract.
- [x] 2.2 Extend self-service API tests for authentication, filter forwarding, empty and isolated graphs, partial/truncated flags, canonical undirected edges and responses that omit embeddings.
- [x] 2.3 Regenerate `openapi/web-v1.json` and run the repository check that detects contract drift.

## 3. UI contract and navigation

- [x] 3.1 Copy the updated web OpenAPI contract into `recallum-ui`, regenerate TypeScript types and add only the focused `d3-force` layout dependency and its required type support.
- [x] 3.2 Add the typed graph API request, TanStack Query key and graph invalidation alongside the existing memory API helpers.
- [x] 3.3 Add the authenticated `/memory-graph` route, document title and “Mapa de memoria” navigation entry, with router tests for authentication and active navigation.

## 4. Memory graph experience

- [x] 4.1 Implement and unit-test deterministic graph layout using similarity-weighted links, collision by node size, retained positions on refresh, neighbour-based placement for new nodes and a non-animated reduced-motion path.
- [x] 4.2 Build the native SVG graph canvas with category geometry, importance sizing, similarity-weighted edges, pan, zoom, recentering and synchronized node selection.
- [x] 4.3 Build the page controls and raised-paper detail panel: server-side scope/project/category filters, visible-snapshot text search, refresh action, relationship highlighting and link to the existing memory detail route.
- [x] 4.4 Add the synchronized semantic list for keyboard and screen-reader traversal, including textual category, importance, project and relationship counts.
- [x] 4.5 Style the canvas, nodes, edges, controls and responsive detail layout exclusively with the existing “Papel Cálido” tokens in light and dark modes.
- [x] 4.6 Integrate loading, empty, isolated, partial, truncated and recoverable error states without blocking the rest of the authenticated shell.

## 5. End-to-end validation

- [x] 5.1 Add UI tests for isolated components, a newly refreshed bridge node, filters, truncated-search messaging, model-mismatch messaging, shared canvas/list selection and reduced motion.
- [x] 5.2 Add Playwright coverage for keyboard-only selection and detail navigation, pointer pan/zoom/recenter, responsive layout and both colour schemes.
- [x] 5.3 Run targeted backend tests, OpenAPI verification and the relevant broader Python checks; record any environment-dependent integration checks that cannot run.
- [x] 5.4 Using Node.js 24, run `recallum-ui` formatting, lint, typecheck, unit tests, production build and targeted end-to-end tests, and inspect the production bundle impact of `d3-force`.
