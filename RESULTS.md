# Results

Wave-by-wave findings from the claude-context lab
(tracking [#84](https://github.com/liatrio/ai-code-intelligence/issues/84)).

**Pinned versions** (all): `@zilliz/claude-context-mcp@0.1.15`,
`@zilliz/claude-context-core@0.1.15`, `milvusdb/milvus:v2.4.13`,
`quay.io/coreos/etcd:v3.5.5`, `minio/minio:RELEASE.2023-03-20T20-16-18Z`,
Ollama ≥ 0.3.0 with `nomic-embed-text:v1.5` (768-dim).

**Fixtures** (both):
- `liatrio/gratibot` @ `<commit-recorded-in-wave-1>` (public, JS/Node, 195 files, 148 tracked `.js`)
- `liatrio-labs/liatrio-knowledge` @ `<commit-recorded-in-wave-6>` (private, TS/SQL/Gherkin/Docusaurus, 5,370 tracked files)

**Stack**: fully local. No Zilliz Cloud, no hosted OpenAI/Voyage/Gemini,
no login flow, `FORBIDDEN_ENV_VARS` gated by `setup.py --check`.

---

## Wave 1 — install + first-index smoke on gratibot

**Status**: complete (2026-09-14)

**Machine**: Apple M2 Pro, 25 GiB Metal GPU, macOS.
**Fixture**: `~/liatrio/repos/gratibot` @ `7c94a642` (public, JS/Node, 195
total files, 148 tracked `.js`).

### Install wall clock

Cold install measured from a clean `.cache/`, no Docker layers pre-pulled,
no Ollama models present:

| Step | Wall clock |
|------|-----------:|
| `npm install` (`@zilliz/claude-context-mcp@0.1.15` + `@zilliz/claude-context-core@0.1.15`) | ~14 s (cold) / 0.5 s (warm) |
| `docker compose up -d` (etcd + minio + milvus-standalone, all bound `127.0.0.1`) | 30–90 s (cold pull) / <1 s (warm) |
| `ollama pull nomic-embed-text` (~274 MB) | ~9 s on this network |
| **Total cold install** | ~1–2 min |

### First-index of gratibot

```
$ python3 setup.py --index --fixture ~/liatrio/repos/gratibot
  [  ok] index_codebase: OK: indexed /Users/paulhenson/liatrio/repos/gratibot
         in 7.2s (41 files, 238 chunks, collection 27e9ea74627e...)
```

- **Wall clock**: 7.19 s (setup.py) / 6.65 s (helper) — the 0.5 s delta is
  Python subprocess boot + argument parse.
- **Files indexed**: 41 of 148 tracked `.js`. The rest were filtered by
  claude-context's built-in ignore patterns (node_modules is excluded by
  default) and by the AST splitter's supported-extension list.
- **Chunks**: 238 total. Average ~5.8 chunks per file.
- **Collection**: `hybrid_code_chunks_27e9ea74` — the `hybrid_` prefix
  confirms claude-context's default hybrid (dense + BM25 sparse) mode
  is active. This is important for later probes: any capability scored
  against the *default* claude-context config is scored against hybrid,
  not dense-only.
- **Collection identity**: MD5 of the absolute fixture path (matches
  claude-context's documented naming — cross-checked with the helper's
  emitted `collection_name`).

### Sanity semantic search

Query: "handler that gives recognition to a user"

Top 5 hits (0.72 s wall clock):

| Score | File | Lines |
|-----:|------|-------|
| 0.0099 | `features/golden-recognize.js` | 20–67 (`respondToRecognitionMessage`) |
| 0.0099 | `service/recognition.js` | 245–254 (golden fistbump guard) |
| 0.0098 | `features/recognize.js` | 110–123 (error handler) |
| 0.0098 | `service/recognition.js` | 214–243 (`gratitudeErrors`) |
| 0.0097 | `features/redeem.js` | 18–91 |

Top hit is the correct handler function. Scores cluster tightly
(~0.0097–0.0099) — this is the RRF (Reciprocal Rank Fusion) score
normalisation from Milvus's hybrid search, not an absolute similarity.
Ranking works; absolute values are not comparable across queries.

### Corrections landed during Wave 1

Three genuine reproducibility notes came out of Wave 1 — a client
following the initial pin would have hit all three:

1. **MinIO registry**. Docker Hub's `minio/minio` namespace no longer
   returns images (`docker pull minio/minio:latest` returns
   `repository does not exist`). The canonical registry is now
   `quay.io/minio/minio`. Updated `docker-compose.yml`, `versions.env`,
   and `tools.lock.json`.
2. **Docker port bindings**. Docker Desktop refused to bind host ports
   for etcd (2379) and MinIO (9000/9001) even with `lsof` reporting no
   holder — a known Docker Desktop quirk. Neither service needs host
   exposure for the lab (Milvus talks to them over the internal Docker
   network at `etcd:2379` and `minio:9000`), so dropped those `ports:`
   entries. Milvus's 19530 is still bound and reachable.
3. **Milvus version**. Initial pin `v2.4.13` failed to load hybrid
   collections: `createHybridCollection` succeeded but subsequent
   `loadCollection` errored with `there is no vector index on field:
   [sparse_vector]`. The BM25 sparse-index handling stabilises in
   Milvus 2.5.x; bumped to `v2.5.20` and it worked on first attempt.
   A client trying the initial pin would have hit this immediately.

Also: driving the MCP server directly with a single-shot JSON-RPC pipe
from Python stalled (the SDK's stdio server needs a proper `initialize` →
response → `initialized` notification → `tools/call` handshake).
Switched `setup.py --index` to a small Node helper (`bin/index-fixture.mjs`)
that calls the same `Context.indexCodebase(...)` method the MCP server
itself invokes internally, with the same config wiring. The **harness**
(`run-prompts.py`) still drives the full MCP surface through Claude
Code — that path is fine because the MCP SDK client library handles
the handshake correctly. This is a `setup.py`-only shortcut, not a
change to what the customer-facing arm measures.

### Cells this wave directly informs

- **`install_without_repo_writes`** — verified: no writes into
  `~/liatrio/repos/gratibot` during install or index (`git status` clean
  before and after both). All state lands in this repo (`node_modules/`,
  `volumes/`) and in `~/.ollama/models/`.
- **`traceable_results`** — verified: every search hit has file,
  `start_line`, `end_line`, and score.
- **`no_source_dependency`-adjacent** — indirectly noted: 41 files
  indexed of 148 tracked (node_modules and other deps not present, and
  ignore patterns filter out dependency-shape directories by default).
  Full probe follows in Wave 3.
- **`agents_md_instructions`** — not yet directly probed; MCP tool list
  is scheduled for Wave 2.

---

## Wave 2 — yes-cell confirmations on gratibot

**Status**: complete (2026-09-14)

### `agents_md_instructions` — MCP `tools/list` probe

Spawned the pinned MCP server via a proper `@modelcontextprotocol/sdk`
client handshake (see `bin/mcp-tools-probe.mjs`). Advertised surface:

- **Server**: `Context MCP Server` v1.0.0
- **Tool count**: **4**

| Tool | Required args | All properties |
|------|---------------|----------------|
| `index_codebase` | `path` | `path`, `force`, `splitter`, `customExtensions`, `ignorePatterns` |
| `search_code` | `path`, `query` | `path`, `query`, `limit`, `extensionFilter` |
| `clear_index` | `path` | `path` |
| `get_indexing_status` | `path` | `path` |

No `resources/`, `prompts/`, or `logging/` surface — just the four tools.
Every tool takes an **absolute path** as the codebase key, matching the
per-path collection identity (MD5 of absolute path). This is what an
agent sees when it opens the MCP over stdio; the `agents_md_instructions`
cell scores against this shape.

### `vector_store_local` — on-disk vector state

After Wave 1's first-index of gratibot (238 chunks in
`hybrid_code_chunks_27e9ea74`):

| Location                             | Size   | What lives there |
|--------------------------------------|-------:|------------------|
| `./volumes/etcd/`                    | 122 MB | Milvus metadata (collection schemas, index configs) |
| `./volumes/milvus/rdb_data/`         |        | RocksDB metadata KV (12 files: `OPTIONS-*`, `MANIFEST-*`, `CURRENT`, `LOCK`, `IDENTITY`, `LOG`, `.log`) |
| `./volumes/milvus/rdb_data_meta_kv/` |        | RocksDB collection-metadata KV |
| **Total Milvus dir**                 | 149 MB | (mostly WAL headroom for a fresh Milvus) |
| `./volumes/minio/a-bucket/`          |  44 KB | Actual vector chunk objects |
| `~/.context/mcp-codebase-snapshot.json`|  519 B | Per-codebase index status (MCP-owned) |
| `~/.context/merkle/27e9ea74...json`  |        | Merkle-tree snapshot for gratibot — the incremental-reindex artifact |

Everything is on local disk; nothing is uploaded anywhere. The
Merkle-tree artifact is directly relevant to Wave 4's
`incremental_reindex` probe.

### `local_embeddings` + `no_default_egress` — network egress probe

Ran a 45-second `lsof -iTCP -sTCP:ESTABLISHED` sampling loop
(500 ms cadence) filtering to `node|ollama|milvus|python|docker`
processes, subtracting loopback (`127.0.0.1`, `localhost`, `::1`,
`0.0.0.0`, unspecified). During the window, `setup.py --index --force`
re-indexed gratibot (6.94 s wall — nearly identical to the Wave 1 first
index; the Merkle sync is short-circuited by `--force`).

Result:

```
=== Non-loopback TCP connections observed during probe window ===
(none — no non-loopback TCP connections established by node/ollama/milvus/python/docker during the window)
```

**Zero** non-loopback TCP connections from any process in the pipeline.
Embeddings computed locally by Ollama on 127.0.0.1:11434, Milvus reached
on 127.0.0.1:19530, all inter-container traffic on the Docker bridge
network. The local-only path is genuinely local.

This does two things at once:
- Confirms `local_embeddings` at yes on the fully-local path.
- Confirms the *lab-pinned* config does not egress. `no_default_egress`
  needs a follow-up: the quickstart-default hosted config (Zilliz Cloud
  + OpenAI) would egress by construction, but that path is out of scope
  per issue #84's local-only constraint. The cell answer will note both.

### `traceable_results` — reconfirmed

Wave 1's sanity search already exercised this: every result had
`file`, `start.line`, `end.line`, and `score`. Wave 2 re-runs the same
shape via the MCP's `search_code` tool during Wave 5's harness; no new
probe needed here.

### Cells this wave directly settles

- **`agents_md_instructions`** — 4 structured MCP tools, absolute-path
  keying, no per-agent wiring needed beyond stdio.
- **`vector_store_local`** — 149 MB Milvus state + 44 KB MinIO objects
  on local disk; queryable without network.
- **`local_embeddings`** — Ollama loopback-only during index; zero
  external calls to any embedding provider.
- **`no_default_egress`** (partial) — the *pinned lab config* egresses
  nothing. The full cell answer includes the quickstart-hosted path
  from source inspection; Wave 3 will note the mode split explicitly.
- **`traceable_results`** — reconfirmed from Wave 1.

### Notes for later waves

- The client-side snapshot at `~/.context/mcp-codebase-snapshot.json`
  is written by the MCP server, **not** by `bin/index-fixture.mjs`. In
  Wave 1 the snapshot got stuck showing `"status": "indexfailed"` from
  the Milvus 2.4.13 crash even after 2.5.20 succeeded, because setup.py's
  helper bypasses the snapshot-update code path. Cleared it manually
  before Wave 2 started. **Wave 5's harness uses the MCP directly, so
  the snapshot will track correctly under harness runs.**
- `docker exec cc-lab-milvus ls /var/lib/milvus` shows the container's
  view of the same files bind-mounted from `./volumes/milvus/` — no
  hidden data outside the bind mount.

---

## Wave 3 — no-cell and defaults confirmations

**Status**: complete (2026-09-14)

### `no_default_egress` — hosted quickstart path (source inspection)

Wave 2 established that the *lab-pinned* local-only config makes zero
outbound TCP calls. Wave 3 completes the picture by documenting what
the quickstart-default config does, straight from the source at
`node_modules/@zilliz/claude-context-mcp/dist/config.js`:

```js
// config.js line 66
embeddingProvider: envManager.get('EMBEDDING_PROVIDER') || 'OpenAI',
```

And the Milvus default (line 82):

```js
milvusAddress: envManager.get('MILVUS_ADDRESS'), // Optional, can be resolved from token
milvusToken: envManager.get('MILVUS_TOKEN'),
```

With no env vars set, claude-context defaults to:

- **Embedding provider: OpenAI** — requires `OPENAI_API_KEY` and talks
  to `api.openai.com` for every embedding call.
- **Milvus: auto-resolve from `MILVUS_TOKEN`** — this is the Zilliz
  Cloud path (no local Milvus assumed by default).

So the *default zero-config path* is OpenAI + Zilliz Cloud, exactly what
the portfolio doc's essay asserts. An operator following the quickstart
gets a config that egresses to two hosted endpoints; making it local
requires knowing `EMBEDDING_PROVIDER=Ollama` and `MILVUS_ADDRESS=127.0.0.1:19530`
from the FAQ, not from the top of the README.

The **`no_default_egress` cell answer** is therefore **`no`** — for a
first-time user, the default path egresses. `workaround` is the set of
env vars pinned in this lab's `versions.env`.

### `semantic_cache` — 5 back-to-back identical queries

Query: `"handler that gives recognition to a user"`, `limit=5`, against
gratibot's hybrid collection. Between-run cadence is only Python + Node
process startup (~500 ms), so any answer cache would show up clearly.

| Run | Wall (s) | Top hit                                      | Top score |
|----:|---------:|----------------------------------------------|----------:|
|   1 |    0.643 | `features/golden-recognize.js:20`            | 0.009901  |
|   2 |    0.564 | `features/golden-recognize.js:20`            | 0.009901  |
|   3 |    0.533 | `features/golden-recognize.js:20`            | 0.009901  |
|   4 |    0.704 | `features/golden-recognize.js:20`            | 0.009901  |
|   5 |    0.513 | `features/golden-recognize.js:20`            | 0.009901  |

- **Mean wall clock**: 0.591 s, **spread**: 0.191 s.
- **Top hit and score identical on every run** — deterministic, but that
  is a property of the underlying vectors, not a semantic cache.
- Flat wall-clock distribution: run 5 (0.513 s) is faster than run 1
  (0.643 s), which is the opposite of what an answer-cache pattern
  would look like (a cache would put run 1 at ~0.6 s and runs 2–5
  clustered around 0.05 s).

**Cell: `no`.** Every semantic search re-runs Ollama's `nomic-embed-text`
on the query, then re-runs Milvus's hybrid retrieval. Nothing between
identical queries is memoised.

### `no_source_dependency` — dependency-source probe

Gratibot has `node_modules/` populated (476 top-level entries) with
`.js` files scattered across every package's `dist/`, `lib/`, etc.
Counts:

| Location                                     | `.js` count |
|----------------------------------------------|------------:|
| Total in fixture                             | 9,313       |
| Inside `node_modules/`                       | 9,232       |
| Outside `node_modules/` (repo code + tests)  |    81       |
| **Actually indexed by claude-context**       |    **41**   |

The 40 non-indexed non-`node_modules` files are all under `test/**` —
matching claude-context's default ignore pattern for test directories.
The 9,232 `node_modules` files are ignored by the default ignore
pattern for `node_modules`.

**Read**: claude-context's default ignore patterns exclude dependency
source *even when it is present on disk*. That means:

- A dependency **whose source is not present** is definitely not
  answerable — the tool wouldn't scan it even if you added it.
- A dependency **whose source IS present** is still not answerable
  without the operator explicitly overriding
  `customIgnorePatterns` / `customExtensions` on the
  `index_codebase` call — an opt-in the vendor recommends against
  because it dilutes the collection with vendor code.

**Cell: `no`** (documentation-adjacent tool — DocsGPT / RAGFlow / Context7 —
is the right shape for this question). `workaround`: pass
`customIgnorePatterns=[]` and pin `customExtensions` to force
dep-source inclusion, but noise will dominate signal on a real project.

### Cells this wave directly settles

- **`no_default_egress`** — `no`. Quickstart defaults egress to OpenAI +
  Zilliz Cloud; the fully-local config used by this lab is available
  but is *not* the default. Note captures the mode split.
- **`semantic_cache`** — `no`. Recomputes every query; 0.19 s spread
  across 5 runs is process noise, not a cache signal.
- **`no_source_dependency`** — `no`. `node_modules` excluded by
  default; even opt-in override drowns primary code with vendor noise.

---

## Wave 4 — shared / gateway cells

**Status**: pending

Planned probes:
- `shared_dev_instance` — start two MCP client processes both talking
  to the same Milvus instance; verify both can query the same
  collection without corrupting state. `netstat -an | grep 19530`
  to confirm loopback bind.
- `portable_index` — dump the Milvus collection with the Milvus CLI /
  Attu, tar the `./volumes/milvus/` state, move to a fresh checkout on
  another path, restore, query. If a semantic query returns the same
  top-5, the index is portable.
- `incremental_reindex` — this is the second headline probe. Time
  four scenarios on gratibot: cold first index, warm identical rerun,
  warm one-file change (touch a single `.js`), warm one-line change.
  Compare against the vendor's "seconds on a typical PR" claim.

---

## Wave 5 — 5-prompt harness × 2 arms on gratibot

**Status**: pending

Planned:
- 10 sessions total (5 prompts × 2 arms).
- Per-session: wall clock, cost (from Claude Code's `result` event),
  input/output/cache-read token totals, and hand-graded pass/partial/fail
  against `prompts.md`.
- Summary table at bottom of this wave: which prompts benefited from
  the claude-context arm, which did not, and by what margin.

---

## Wave 6 — same harness on liatrio-knowledge

**Status**: pending

Planned:
- Same 10-session shape, private fixture (5,370 tracked files, TS + SQL +
  Gherkin + MDX + Docusaurus).
- Wave-6-specific pass conditions for prompts 2 and 4 recorded in
  `prompts.md` pre-run (currently marked "decided at Wave 6 pre-grade");
  those pin the fixture-specific expectations before graders see the
  transcripts.
- Compare wall clock and cost against Wave 5's gratibot numbers — the
  Semgrep lab showed the size effect compresses both arms toward each
  other; the CBM lab showed the graph tool crossed the wall-clock line
  on the larger fixture. Where does claude-context land?

---

## Summary (fills in as waves land)

- Cells lifted from `unknown` to `yes`/`no`: **TBD**.
- Cells lab-verified without a status change: **TBD**.
- Cells nuanced by harness runs: **TBD**.
- Cells not resolvable in this lab (out of scope, e.g. `commercial_use`
  under LGPL for a hosted-only feature): **TBD**.
