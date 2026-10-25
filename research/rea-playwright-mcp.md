# Architecture study: Playwright MCP server (`@playwright/mcp` 0.0.83)

Purpose: learn how a production MCP server is shaped, so projects 08, 09, 20 and 23 can be designed from first
principles. **No code was copied.** This note describes architecture only; every project in this repo is original code.

## Target

| Item | Value |
|---|---|
| Package | `@playwright/mcp` 0.0.83 (npx cache `_npx/9833c18b2d85bc59/node_modules/@playwright/mcp`) |
| Real implementation | `playwright-core` 1.64.0-alpha-1790635538000, `lib/coreBundle.js` (3.5 MB, 77,880 lines, esbuild bundle that keeps `// packages/playwright-core/src/...` module banners) |
| MCP SDK | `@modelcontextprotocol/sdk` (ESM build) bundled inside `playwright-core/lib/utilsBundle.js` |
| License | **Apache-2.0** (both `package.json` files and file headers), not MIT as the brief assumed. Architecture description is fine under either licence; we still copy nothing. |

## Method (REA, and what happened)

1. Loaded the `reverse-engineer-anything` skill. REA MCP tools were **not** registered in this session, so the documented
   CLI fallback was used: `npx -y rea-agents@latest analyze-javascript-application <path> --format json`
   (rea-agents 6.7.0).
2. Every run failed before analysis with `artifact_operation_failed / integrity_mismatch`,
   detail `Directory entry changed before open: cli.js`. Retrying with `--integrity-policy record-and-continue`,
   on a fresh copy in a scratch directory, and with `--source-path index.js` gave the same result.
3. `rea doctor --client claude_code --json` identified the blocker: **Node.js 22.14.0 is below REA's required
   22.19+** (`scope_checks[node].classification = missing_dependency`). The same file-identity failure also hit the
   doctor's own read of `~/.claude.json` ("Selected input changed while being read"), which points to the old Node
   runtime's file-identity behaviour on Windows rather than the target. REA setup never upgrades Node, and installing
   software was out of scope, so this blocker was **not repaired**.
4. Per the skill's recovery guidance ("continue useful supported work"), the investigation continued with **manual
   static reading of the shipped bundle** (grep for module banners, then reading the relevant modules). Because no REA
   Evidence records exist, findings below cite **local evidence IDs (L1…L14) = file + line in the shipped bundle**.
   To reproduce with REA later: upgrade Node to >= 22.19 and rerun step 1 against `playwright-core/lib`.

Paths below are relative to `node_modules/playwright-core/lib/`.

## Evidence ledger

| ID | Location | What it is |
|---|---|---|
| L1 | `@playwright/mcp/index.js`, `cli.js` | Thin wrapper: re-exports `tools.createConnection` and `tools.decorateMCPCommand` from `playwright-core/lib/coreBundle` |
| L2 | `coreBundle.js:73864-73952` (`src/tools/utils/mcp/server.ts`) | `createServer`, `connect`, `start` (stdio vs HTTP) |
| L3 | `coreBundle.js:73841-73855` (`src/tools/utils/mcp/tool.ts`) | `toMcpTool`: internal tool -> MCP tool descriptor |
| L4 | `coreBundle.js:74009-74053` | `initializeServer` (roots negotiation) + heartbeat ping |
| L5 | `coreBundle.js:67490-67599` (`src/tools/backend/browserBackend.ts`) | `BrowserBackend.callTool`: lookup, validation, response, error shaping |
| L6 | `coreBundle.js:65604-65622` (`src/tools/backend/tool.ts`) | `defineTool` / `defineTabTool`, modal-state gate |
| L7 | `coreBundle.js:65668-65760` (`src/tools/backend/snapshot.ts`) | `browser_snapshot`, `browser_click`, `browser_drag` definitions |
| L8 | `coreBundle.js:66601-66705` (`src/tools/backend/tab.ts`) | `captureSnapshot`, `_raceAgainstModalStates`, `targetLocators` |
| L9 | `coreBundle.js:65477-65512` (`src/tools/backend/utils.ts`) | `waitForCompletion`: settle + network-quiet heuristic |
| L10 | `coreBundle.js:67076-67442` (`src/tools/backend/response.ts`) | `Response` sections, serialisation, output budget |
| L11 | `coreBundle.js:69995-70000` (`src/tools/backend/tools.ts`) | `filteredTools(config)`: capability gating |
| L12 | `coreBundle.js:73710-73840` (`src/tools/utils/mcp/http.ts`) | HTTP transport: Streamable HTTP `/mcp`, legacy SSE `/sse`, host allow-list |
| L13 | `coreBundle.js` (embedded injected script `packages/injected/src/ariaSnapshot.ts`) | ref minting `"e" + ++lastRef`, cached on the element; renders `[ref=eN]`, `[cursor=pointer]` |
| L14 | `utilsBundle.js` (bundled SDK) | `LATEST_PROTOCOL_VERSION = "2025-11-25"`, supported list back to `2024-10-07`; `DEFAULT_REQUEST_TIMEOUT_MSEC = 6e4` |

## Findings

### 1. Server structure and transport

**Observed**
- The published package is a 2-file shim; the server lives in `playwright-core` (L1).
- The server is built on the official MCP SDK `Server` class. Only two request handlers are registered by Playwright
  itself: `tools/list` and `tools/call` (L2). `initialize`, `ping` and protocol-version negotiation are handled by the
  SDK (L14).
- Declared capabilities: `{ tools: { listChanged: true } }`. No `resources` or `prompts` capability (L2).
- Transport choice: no `--port` -> stdio (`StdioServerTransport`; closes when stdin ends). With `--port` -> HTTP server
  offering Streamable HTTP at `/mcp` and legacy SSE at `/sse`, guarded by a Host-header allow-list (L2, L12).
- Heartbeat: for Streamable HTTP sessions the server pings the client every ~3 s and closes the session if a ping
  takes longer than 5 s (configurable via env). Stdio and SSE pass `runHeartbeat = false` (L4, L12).

**Inferred**
- Splitting "protocol server" (SDK) from "backend" (`BrowserBackend`) lets the same tools be reused by other front
  ends (the bundle also contains a CLI client and a dashboard that call the same backend).

### 2. Lazy backend + capability negotiation

**Observed**
- The browser backend is **created lazily on the first `tools/call`**, not at `initialize` (L2). `tools/list` works
  without launching a browser.
- On that first call, if the client advertised the `roots` capability, the server calls `roots/list` (waiting up to
  5 s for the transport) and uses the first root as the working directory; otherwise `process.cwd()` (L4).
- If the browser disconnects, the cached backend promise is dropped so the next call creates a fresh one (L2).
- `tools/list` = static schemas + "dynamic" tools discovered from the page (WebMCP); when those change the server sends
  `notifications/tools/list_changed` (L2, L5).

### 3. Tool registry and schemas

**Observed**
- Each tool is a plain object: `{ capability, schema: { name, title, description, inputSchema (zod), type }, handle }`.
  `type` is one of `readOnly | input | action | assertion` (L6, L7).
- `toMcpTool` converts zod -> JSON Schema and derives MCP annotations: `readOnlyHint` for readOnly/assertion,
  `destructiveHint` for everything else, `openWorldHint: true` always (L3).
- Tools are grouped by capability (`core`, `core-input`, `core-navigation`, `core-tabs`, `network`, `storage`,
  `devtools`, `vision`, `pdf`, `testing`, `config`); `core*` are always on, the rest are opt-in via config (L11).
  Static count in this build: 24 `core`, 7 `core-input`, 4 `core-navigation`, 1 `core-tabs`, plus opt-in groups.
- `defineTabTool` wraps a handler so it first ensures a tab exists and **refuses to run while a modal (dialog / file
  chooser) is pending**, unless the tool is the one that clears that modal (L6).

### 4. Browser state exposed to the model: accessibility snapshot + refs

**Observed**
- `browser_snapshot` returns an **accessibility (ARIA) snapshot in YAML-like text** produced in "ai" mode; options:
  subtree `target`, `depth`, bounding `boxes`, or save to file (L7, L8).
- Every interactable node gets a short ref `e1, e2, ...` (`f<N>e<M>` inside frames). Refs are minted by a counter in
  the injected page script and **cached on the DOM element** together with its role and name (L13). *Inferred:* the
  cache lets an unchanged element keep its ref across snapshots; the exact reuse condition was not read. Rendered lines look like `- button "Submit" [ref=e12] [cursor=pointer]` (L13).
- Action tools take `target` (a ref, or a CSS/Playwright selector as fallback) plus an optional human-readable
  `element` description "used to obtain permission to interact with the element" (L7).
- Ref resolution: `target` matching `^(f\d+)?e\d+$` is resolved through an `aria-ref=` locator; failure raises
  "Ref eN not found in the current page snapshot. Try capturing new snapshot." (L8).
- After an action the response includes a fresh snapshot (actions call `setIncludeSnapshot`), together with "Page"
  (URL, title, HTTP status, console counts), "Open tabs", "Modal state" and "Events" sections (L10).
- In this build, implicit post-action snapshots are written to a `page-*.yml` file and returned as a link unless the
  snapshot was explicitly requested (L10, `snapshotToFile`). An output-size budget deletes the oldest output files (L10).

### 5. Tool call -> browser action mapping

**Observed** (`browser_click` as the worked example, L7, L9)
1. Resolve `target` -> locator (L8).
2. Record the equivalent Playwright code line (`response.addAction`) so the reply can show "Ran Playwright code".
3. Run the action inside `waitForCompletion`: listen for network requests, run the action, wait a "settle" delay
   (default 500 ms); if a navigation was requested wait for `load` (10 s cap), else wait for outstanding
   document/script/xhr/fetch requests (5 s cap) and settle again (L9).
4. Everything is raced against "a modal appeared" so a surprise `alert()` does not hang the call (L8).
5. Serialise a markdown reply with `### Error`, `### Result`, `### Ran Playwright code`, `### Page`, `### Snapshot`
   sections; consecutive text parts are merged into one content block (L2, L10).

### 6. Errors and timeouts

**Observed**
- Unknown tool -> tool result `isError: true` with `### Error\nTool "x" not found` (not a JSON-RPC error) (L5).
- Bad arguments -> zod validation -> `isError: true` with a prettified message (L5).
- Handler exceptions and unhandled page promise rejections are caught and returned as `isError: true` text (L5).
  A final catch-all in the `tools/call` handler does the same for backend start-up failures (L2).
- Timeouts are layered: per-action / navigation / expect timeouts from config (L8), settle and network-quiet caps
  (L9), a 5 s roots wait (L4), a 5 s heartbeat ping (L4), and the SDK's 60 s default request timeout (L14). The
  request's abort `signal` is passed down to handlers (L2, L5).

**Inferred**
- Returning tool failures as *results* (not protocol errors) is deliberate: the model sees the message and can
  self-correct (e.g. take a new snapshot after a stale ref).

### Unknowns (not established)
- Exact snapshot pruning rules (which nodes get refs, how generic containers collapse) live in the injected script and
  were only sampled, not fully read.
- Runtime behaviour was **not observed**: no server was launched, no browser started. All of the above is static.
- Whether incremental/diff snapshots exist in other config modes (`snapshot.mode`) was not traced.
- REA Evidence IDs are unavailable until the Node prerequisite is fixed (see Method).

## Design lessons we use in this repo

| Lesson | Used in |
|---|---|
| Keep the JSON-RPC/protocol layer separate from the tool backend | 08, 20 |
| Tool = name + description + JSON Schema + handler + read-only/destructive hint | 08, 09, 23 |
| Tool failures are `isError` results the model can read; protocol errors only for protocol problems | 08, 09, 20 |
| Lazy backend start; `tools/list` must be cheap | 08 |
| Show the model an accessibility tree with short refs, not raw HTML or pixels | 23 |
| Refs are stable per element; stale ref -> clear error that says "take a new snapshot" | 23 |
| Every action returns the new page state, so observe -> act is one round trip | 23 |
| Discovery documents (tool list / agent card) let clients find capabilities at runtime | 09, 20 |

---

## REA evidence pass (added 2026-10-24, after the Node.js upgrade)

REA (`rea-agents` CLI, `analyze-javascript-application`) ran on Node 22.23.4. This was static analysis only: nothing was executed.
The raw Evidence JSON (about 52 MB) stays local in `research/rea/` and is not committed. The IDs below identify it exactly.

| Pass | Target | Evidence ID | Scope |
|---|---|---|---|
| 1 | `@playwright/mcp` package directory | `ev_f844cb1169837962632dcf4ed16ebe458648bcabf627f44b78f1ade1bb5a42a4` | 4 JS files parsed, 445 AST nodes, 17 findings |
| 2 | `playwright-core`, selected sources `lib/coreBundle.js` and `lib/tools/cli-client/program.js` | `ev_f8ba2beaffe2703ff41eca2f87616c14fdad573ec71336aa731488ea2a55e73d` | 2 files parsed (46 others out of scope), 414,314 AST nodes, 405 modules, 1,205 findings |

### Observations (from the evidence)
- **Pass 1:** the `@playwright/mcp` package is a thin wrapper. It has 18 graph nodes (4 assets, 11 modules), with no Electron windows, IPC, preload or native addons.
- **Pass 2:** the bundle's module inventory includes `lib/entry/mcp.js`, `lib/serverRegistry.js`, `lib/tools/utils/socketConnection.js`, `lib/tools/utils/extension.js`, and the CLI-client modules `session.js`, `registry.js`, `channelSessions.js` and `output.js`.
- **Pass 2:** `lib/tools/cli-client/program.js` has three child-process spawn sites with stdio roles, at lines 200, 214–218 and 292–295. Listeners are registered on the child's `data`, `exit` and `close` events (lines 220, 229–237, 296–301). A timer is scheduled at line 223. Input parse/coerce boundaries are at lines 233, 289, 310, 316, 330 and 339.
- **Pass 2 semantic graph:** 21,983 nodes (10,063 functions, 208 call sites, 39 modules, 25 tasks, 9 listeners, 3 child processes, 3 stdio) and 3,221 relations.

### Inferences (not proven by static analysis)
- The CLI client launches a separate long-lived process and talks to it over stdio pipes. A timer bounds startup or waiting. Sessions are tracked through a registry. Together this suggests a **daemon/session model**: the browser outlives a single command, and later commands reattach to it.
- `socketConnection.js` and `extension.js` point to a second transport for attaching to an existing browser (the "extension" mode). This is consistent with the hand-read notes above.

### Unknowns
- The analysis left 21,112 semantic items unresolved (mostly dynamic call targets inside the bundle). Coverage is incomplete, and missing facts must not be read as absence.
- 46 inventoried files were outside the selected scope, so relationships through them are unknown.
- Nothing about runtime reachability, defaults or enforcement is proven. Where this pass and the hand-read notes overlap, the hand-read file and line references stay the stronger evidence for the tool registry and error handling.

### What this changed in our projects
- **Project 09:** the client launches the server as a child process with stdio pipes, a reader thread and a startup timeout. That matches the observed spawn, listener and timer pattern.
- **Project 25:** the daemon/session inference is taught there as "long-lived workers with leases".
