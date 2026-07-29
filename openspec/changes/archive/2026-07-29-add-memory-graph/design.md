## Context

See `proposal.md` for motivation and `specs/memory-graph/spec.md` for observable behavior.

Recallum stores one 768-dimensional pgvector embedding and its producing model on each memory. `MemoryRepository` already performs cosine-neighbour queries, but its `similar_active` operation deliberately restricts results to the same scope, project and category because it detects possible duplicate or contradictory claims. The graph has different semantics: it must discover themes across those administrative boundaries.

The web API is mounted under `/api/v1`, derives the user from a browser session and runs memory statements inside forced-RLS user sessions. Its OpenAPI contract is versioned in `openapi/web-v1.json`. The separate `recallum-ui` repository consumes a generated TypeScript schema and uses React, TanStack Router, TanStack Query and the “Papel Cálido” design tokens. It has no graph-layout dependency today and must continue to build with Node.js 24.

## Goals / Non-Goals

**Goals:**

- Produce a bounded, truthful graph snapshot from active memories and their existing embeddings.
- Find semantic neighbours across projects, scopes and categories without weakening tenant isolation.
- Keep graph computation independent of the live embedding service.
- Render an interactive but accessible graph whose visual language belongs to Recallum.
- Let a newly stored memory join or bridge existing components while preserving orientation in the current UI session.

**Non-Goals:**

- Persisting graph edges, layout coordinates, conversations or session transcripts.
- Inferring typed relations such as “causes”, “supports” or “contradicts”.
- Connecting nodes merely because they share a project or category.
- Rendering retired and superseded history in the overview graph.
- Real-time push updates, collaborative graph editing or manual edge creation.
- An unbounded visualization of every memory ever stored.

## Decisions

### 1. Add a dedicated graph snapshot endpoint

Add `GET /me/memory-graph` to the authenticated self-service router. It accepts the existing optional `scope`, `project` and `category` filters plus a bounded `limit`; it does not accept a user identifier or a client-controlled similarity threshold.

The response has an additive OpenAPI contract:

```text
MemoryGraphResponse
├── nodes: MemoryGraphNode[]
│   ├── id, content, category, scope, project
│   └── importance, created_at
├── edges: MemoryGraphEdge[]
│   └── source_id, target_id, similarity
├── total: integer
├── truncated: boolean
└── model_mismatch: boolean
```

`source_id` and `target_id` use canonical identifier ordering so an undirected edge is returned once. Metadata and embeddings are omitted; the existing detail endpoint remains the source for a complete record.

This route is separate from `/me/memories/{memory_id}` to avoid a static `graph` segment competing with UUID path matching. Reusing the paginated list endpoint was rejected because it cannot expose similarity without leaking embeddings or making the browser reproduce domain logic.

### 2. Compute a bounded projection instead of storing edges

Add graph-specific repository/service operations rather than changing `similar_active`. The repository selects a deterministic set of active nodes after applying user/RLS and optional filters, ordered by importance, recency and identifier. It reports the full matching count before applying the node cap.

Within the same user transaction, PostgreSQL computes cosine similarity for unique pairs in the selected set. Only pairs at or above a validated graph threshold are returned to the service. The service sorts them strongest-first and greedily retains an edge only while both endpoints remain below the configured neighbour cap.

The initial release targets at most roughly 200 visible nodes and four neighbours per node. `graph_max_nodes`, `graph_max_neighbours` and `graph_min_similarity` belong in `MemoryLimits` because embedding distributions need calibration without a schema or client change. Their values remain server-owned and validated.

A persisted edge table was rejected: derived edges would become stale after model changes, add write amplification to every memory operation and duplicate information already present in embeddings. Calling `similar_active` once per node was rejected because it opens repeated database work and preserves restrictions that are wrong for thematic exploration.

### 3. Compare only embeddings with compatible provenance

Two nodes can form an edge only when both embeddings have the same known `embedding_model`. All active memories still appear as nodes, but unknown or mismatched provenance can leave nodes or model groups disconnected. `model_mismatch` tells the UI that the absence of cross-group edges may be technical rather than thematic.

Using vectors from different models was rejected because cosine distance across incompatible spaces is not evidence. Hiding the affected memories was also rejected because it would make the graph incomplete without showing the user what is missing.

The live Ollama service is not called: graph construction uses vectors already stored in PostgreSQL, so an Ollama outage does not remove the graph.

### 4. Use semantic forces only; project remains context

The UI uses edge similarity as the force-link strength. Charge, collision and centring forces make components legible, while node radius is derived from bounded importance. Project, category and scope do not add layout forces, so proximity never claims a relationship unsupported by an edge.

Project is exposed in filters, the selected-memory panel and concise hover/focus labels. Components can naturally be dominated by one project, but the UI does not draw a project-to-project edge or force every project into one region.

### 5. Render native SVG with `d3-force` as the only graph dependency

Use `d3-force` for deterministic, bounded layout and native SVG for nodes, edges and transforms. A full D3 bundle, WebGL graph package and diagram editor were rejected as unnecessary. A handwritten force simulation was rejected because collision, link strength and stable ticking are substantial numerical behavior rather than product-specific code.

On first load, node identifiers seed deterministic starting positions. During a refresh, existing positions are retained; a new connected node starts near the weighted centre of its strongest visible neighbours, while an isolated node starts from its deterministic seed. The simulation then settles only the affected layout.

With `prefers-reduced-motion`, the simulation advances a fixed number of synchronous ticks before presentation and no animated settling is shown. Coordinates remain client state only and are not persisted.

### 6. Reuse the “Papel Cálido” visual grammar

The page uses the existing `workspace-header`, filter controls, request states and raised-paper surfaces. The graph canvas uses `--color-paper-sunken`; edges use low-opacity ink or line tokens; selection, a newly arrived node and its adjacent path use `--color-accent`.

Node geometry reuses the category vocabulary:

- preference: circle;
- decision: filled square;
- constraint: diamond;
- fact: horizontal bar.

Importance controls a small, bounded radius range. Category is never encoded by colour alone. The design deliberately avoids the multicolour clusters in the visual reference because Recallum defines one accent; project context is textual rather than rainbow-coded.

### 7. Keep graph interaction and accessible traversal synchronized

The SVG supports pointer pan, wheel/button zoom and recentering through one transformed graph group. Selecting a node highlights it and its incident edges and opens a raised-paper summary panel linking to `/memories/$id`.

The canvas itself is summarized as an accessible graphic. A structured, searchable list of visible memories is the keyboard and screen-reader traversal surface; selecting an item there performs the same action as selecting its SVG node. This avoids forcing assistive technology through hundreds of low-level SVG elements while retaining all essential information and actions.

Search highlights loaded nodes client-side and explicitly scopes itself to the visible snapshot when `truncated` is true. Scope, project and category filters refetch the server-side subgraph so filtered nodes are not lost behind the default node cap.

### 8. Treat growth as refreshable snapshots, not live state

Use a TanStack Query key derived from `memoriesKey`, `graph` and the active filters. Memory create, supersede, correct and forget invalidation also invalidates graph snapshots. A visible refresh action and normal refetch-on-focus incorporate memories written by agents outside the browser.

No polling or push channel is added. The page labels the data as a snapshot and preserves existing node positions when refreshed, which makes a new bridge legible without promising real-time updates.

### 9. Keep the cross-repository contract explicit

Backend work lands first in `recallum-mcp`, including tests and regenerated `openapi/web-v1.json`. The contract is then copied to the versioned OpenAPI input in `recallum-ui`, and `npm run generate:api` regenerates its TypeScript types before the route and view are added.

This order allows the backend to deploy independently and prevents handwritten frontend response types from drifting.

## Risks / Trade-offs

- **Pairwise similarity is quadratic in the selected node count** → enforce a server cap before the pair query, keep a small neighbour cap and add a representative performance check.
- **A threshold can produce either noise or excessive isolation** → keep the threshold validated and server-configurable, calibrate against representative multilingual memories and expose honest isolated states.
- **Model drift can fragment the graph** → compare only identical known model provenance and surface `model_mismatch`; re-embedding remains a separate concern.
- **Force layouts can move too much after refresh** → retain existing coordinates and seed only new nodes near known neighbours.
- **Dense SVG can become expensive** → bound the initial graph; move to canvas or progressive expansion only if measured usage exceeds the SVG budget.
- **A visual graph can exclude keyboard or screen-reader users** → provide a synchronized semantic list and shared selection/detail behavior.
- **The feature spans two repositories** → version the backend contract, regenerate UI types and validate both repositories before release.
- **Adding `d3-force` increases frontend bundle size** → depend on the focused package only and verify the production bundle rather than importing the full D3 suite.

## Migration Plan

1. Add backend limits, graph query/service, authenticated endpoint and tests without changing the database schema.
2. Regenerate and verify the backend OpenAPI artifact.
3. Update the contract and generated types in `recallum-ui`.
4. Add the UI route, navigation, graph view and tests; build and test it with Node.js 24.
5. Deploy the backend before or together with the UI. The additive endpoint is harmless to older clients.
6. If rollback is required, remove or hide the UI route first; the unused additive backend endpoint can remain until the backend is rolled back.
