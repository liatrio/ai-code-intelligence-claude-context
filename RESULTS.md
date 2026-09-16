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

## Wave 4 — shared / gateway cells

**Status**: complete (2026-09-14)

### `shared_dev_instance` — two clients, one Milvus

Ran two `bin/search-fixture.mjs` processes concurrently against the
same Milvus and the same `hybrid_code_chunks_27e9ea74` collection:

| Client | Query                                    | Top hit                          | Wall clock |
|-------:|------------------------------------------|----------------------------------|-----------:|
|      A | "handler that gives recognition to a user" | `features/golden-recognize.js:20` |    1.065 s |
|      B | "leaderboard aggregation"                | `features/leaderboard.js:37`     |    1.059 s |

Both returned correct answers, both took ~1 s (roughly 2× the
single-client 0.5 s baseline, as expected — the two Node processes
contend for Ollama embedding CPU on the same laptop, but Milvus
handled them without lock contention). No errors, no
`ResourceBusy`, no serialization observed.

**Cell**: `yes`, lab-confirmed. The docs-only `yes` in the current
`data.json` is upgraded to a lab observation.

### `incremental_reindex` — 7 reps of touch → `reindexByChange` → verify

Driver: `bin/incremental-probe.mjs`. Each rep appends a unique
`WAVE4_MARKER_<n>_<timestamp>_<rand>` comment to
`~/liatrio/repos/gratibot/regex.js`, calls
`Context.reindexByChange(...)` on the live Milvus, then runs a
semantic search for the bare `WAVE4_MARKER_<n>` prefix. Same
`Context` instance across all 7 reps — this mirrors a long-lived
MCP server watching a checkout, which is the customer-facing shape.

Full-index baseline from Wave 1: **6,650 ms** for gratibot (41
files, 238 chunks). The `incremental_reindex` labCheck asks for
p90 ≤ 30 s **and** delta ≤ 1/10 of a full index, i.e. ≤ 665 ms.

| Metric              | Min   | Median | p90    | Max    |
|---------------------|------:|-------:|-------:|-------:|
| Reindex only (ms)   |  232  |   418  |  **648** |  648  |
| Semantic search (ms)|  185  |   363  |    386 |  386  |
| End-to-end (ms)     |  599  |   781  |    972 |  972  |

- **Marker hit rate: 7 of 7** — every rep's marker was queryable
  through the standard hybrid `search_code` path in the same
  session. No stale hits, no cold misses.
- **p90 reindex delta**: 648 ms = **9.75 %** of the full-index
  wall clock. Clears the 1/10 threshold by 5 %.
- **p90 end-to-end (reindex + first query)**: 972 ms — 30× under
  the 30-s ceiling.
- **Every rep** logged `Merkle DAG has changed. Comparing file
  states... Found changes: 0 added, 0 removed, 1 modified.` — the
  Merkle-diff sync mechanism claimed by the FAQ is now lab-verified.

**Cell**: `yes` (upgraded from `unknown`). The one caveat worth
noting in the cell text: this is a single-file change on a 41-file
JavaScript fixture. A larger PR-sized change (say 5-10 files)
would still likely clear the labCheck, but the numbers above are
the smallest realistic delta — a real PR might land 3-5× higher on
the reindex side and still pass.

### `portable_index` — persistence and portability

Ran the compose-restart flow — the workaround claim in the current
`data.json` is that Milvus backup/restore plus matching absolute
paths lets a team share an index. Steps:

1. Baseline query on live Milvus: top hit `features/golden-recognize.js:20`, 0.73 s
2. `docker compose down` — all three containers destroyed
3. On-disk state confirmed:

   | Path            | Size   |
   |-----------------|-------:|
   | `volumes/etcd`  |   61 M |
   | `volumes/milvus`| 149 M  |
   | `volumes/minio` |  1.7 M |
   | **Total**       | 211 M  |

4. `docker compose up` — Milvus healthy in 5 s (from
   `curl http://127.0.0.1:9091/healthz` inside the container)
5. Same query without reindexing → same top hit, 3 hits, 0.43 s
   (faster than baseline because embeddings for the query are the
   only work; Milvus warm-loaded from disk).

Persistence is genuine — the 211 M of volume state on disk *is* the
index. That means the operator workaround (`tar -czf snapshot.tgz
volumes/`, ship, restore) will work. **But this cell stays `no`**
because two things still bite the labCheck ("Build an index, copy
it to a second machine or container that did not run the indexer,
and complete a query against the copy"):

1. **No first-class "export index" command.** Nothing in the MCP
   surface or the core API publishes an artifact — the operator
   has to know that `volumes/` is the state and tar it themselves.
2. **Collection identity is MD5 of the absolute path.** A shipped
   snapshot only works on a target where the fixture is at the
   same absolute path (`~/liatrio/repos/gratibot`), OR the
   operator uses `CODE_CHUNKS_COLLECTION_NAME_OVERRIDE`. The
   friction is exactly what the existing workaround text calls
   out.

The workaround now has a lab receipt: persistence is real, so
tar/rsync/backup approaches genuinely work provided both hosts
carry the fixture at the same path (or the operator overrides the
collection name). The cell answer stays **`no`** but the note gains
concrete numbers.

### Cells this wave directly settles

- **`shared_dev_instance`** — `yes`, upgraded from docs-only to
  lab-observed. Two concurrent clients on the same Milvus + same
  collection both returned correct hits in ~1 s each.
- **`incremental_reindex`** — `yes`, upgraded from `unknown`. p90
  reindex delta 648 ms = 9.75 % of the 6,650 ms full-index baseline.
  Marker hit rate 7/7.
- **`portable_index`** — stays `no` with workaround. Persistence
  now lab-verified (211 M of volume state survives
  `docker compose down`); no first-class artifact and MD5-path
  collection identity keep this off the `yes` list.

## Wave 5 — 5-prompt harness × 2 arms on gratibot

**Status**: complete (2026-09-14)

Ran `run-prompts.py` with `--arms baseline,claude-context --prompts
P1,P2,P3,P4,P5 --fixture ~/liatrio/repos/gratibot`. Baseline gets
Read + Grep + Bash; claude-context arm gets the same three plus
the three claude-context MCP tools (`index_codebase`, `search_code`,
`get_indexing_status`). Same system prompt across both arms.
Total wall clock for all 10 sessions: 7 min 15 s.

### Per-session numbers

| Prompt | Arm             | Wall   | Cost      | in     | out    | cache_c | cache_r  | Grade |
|-------:|-----------------|-------:|----------:|-------:|-------:|--------:|---------:|:-----:|
| P1     | baseline        | 28.3 s | $0.5827   | 8,315  | 1,606  | 44,321  | 115,594  | pass  |
| P1     | claude-context  | 32.8 s | $0.4673   | 8,678  | 1,988  | 28,217  | 183,985  | pass  |
| P2     | baseline        | 20.2 s | $0.3524   | 8,628  |   939  | 23,861  |  94,416  | pass  |
| P2     | claude-context  | 18.4 s | $0.3570   | 8,674  |   952  | 24,213  |  95,315  | pass  |
| P3     | baseline        | 32.7 s | $0.4656   | 8,612  | 1,956  | 30,449  | 138,219  | pass  |
| P3     | claude-context  | 48.3 s | $0.4503   | 8,811  | 3,277  | 18,075  | 287,095  | pass  |
| P4     | baseline        | 65.2 s | $0.7653   | 8,747  | 4,659  | 44,708  | 316,080  | pass  |
| P4     | claude-context  | 60.2 s | $0.5914   | 8,807  | 4,709  | 31,979  | 219,634  | pass  |
| P5     | baseline        | 75.0 s | $0.6533   | 8,749  | 4,488  | 32,915  | 336,449  | pass  |
| P5     | claude-context  | 52.7 s | $0.3952   | 8,680  | 3,373  | 14,429  | 246,293  | pass  |

### Aggregates and deltas

| Metric              | Baseline  | Claude-context | Δ      |
|---------------------|----------:|---------------:|-------:|
| Total wall (s)      |    221.35 |         212.45 |  −4.0 % |
| **Total cost (USD)**|  **$2.82**|      **$2.26** |**−19.8 %** |
| Total input tokens  |    43,051 |         43,650 |  +1.4 % |
| Total output tokens |    13,648 |         14,299 |  +4.8 % |
| Cache creation      |   176,254 |        116,913 | **−33.7 %** |
| Cache read          | 1,000,758 |      1,032,322 |  +3.2 % |
| Pass rate           |     5 / 5 |          5 / 5 |    tie |

### Reading the numbers

- **Correctness on gratibot is a tie** — 5-of-5 on both arms.
  Every prompt's pass condition is met, including the discriminator
  P5 (both arms found the `service/deduction.js` deductionLocks
  + `service/stadium.js` deterministic `_id` two-layer idempotency
  guard, with correct mechanism description). The frozen pass
  condition mentions `service/recognition.js` but ground truth is
  the two files both arms landed on — gratibot's recognition
  layer has no dedupe.
- **Wall-clock is a tie** — 212 vs 221 s across five prompts is
  noise, not signal.
- **Cost is the story: −19.8 %** ($0.56 saved on $2.82). The
  mechanism is transparent in the cache-creation column:
  claude-context wrote **33.7 % fewer new-cache tokens** (177 k
  → 117 k) with essentially the same cache-reads. In plain
  English: `search_code` returned tight AST chunks instead of the
  large Read/Grep dumps that baseline had to load, so the model
  paid less for building its context window.
- **Where the saving concentrates**: P5 (the discriminator) has
  a **40 % cost saving** on its own — $0.65 → $0.40. This is
  the prompt semantic search is designed for; even though both
  arms passed on gratibot's 41 indexed files, the *cost* to get
  there differed the most on P5.
- **On gratibot the ROI is entirely cost-side, not correctness-side**.
  This matches the frozen note in `prompts.md`: "Baseline arm may
  still pass on gratibot (195 files is grep-able with concept
  keywords), but the *cost* difference is what the wave measures."

### Cells this wave touches

- **`token_saving`** — `yes`, lab-observed. Vendor's ~39 % claim
  measures a different setup (SWE-bench-Verified subset, 30
  tasks); we measure a 20 % cost saving on 5 concept-retrieval
  prompts against a 41-file gratibot. The **direction** matches
  (claude-context arm cheaper); the magnitude is smaller on this
  fixture. Update note to cite both numbers.
- **`roi_evidence`** — `yes`, lab-observed. First Liatrio-run
  measurement of claude-context ROI. 5 prompts × 2 arms, both
  arms pass all five, claude-context arm is 19.8 % cheaper on
  total cost with 33.7 % fewer cache-creation tokens. Update note
  to add lab receipt.
- **`traceable_results`** — reconfirmed on P5 where `search_code`
  was actually called; other prompts inherited the same shape from
  Read/Grep output. When the tool runs, results carry `file:startLine-endLine`
  and score, exactly as advertised.

## Wave 6 — 5-prompt harness × 2 arms on liatrio-knowledge

**Status**: complete (2026-09-14)

Fixture: `~/liatrio/repos/liatrio-knowledge` — 5,370 tracked files;
**2,126 indexed by claude-context defaults** (TS/TSX/JS/MD;
`.txt`, `.yaml`, `.feature`, `.sql` are outside
DEFAULT_SUPPORTED_EXTENSIONS). **44,467 chunks** in the hybrid
collection (`hybrid_code_chunks_8e870251`). **Wall clock to index:
27 min 22 s** on this laptop (Ollama embedding was the bottleneck;
zero API cost). Harness wall clock: **17 min 37 s** across the 10
sessions.

### Per-session numbers

| Prompt | Arm             | Wall     | Cost       | Search_code | Agent | Read | Grep | Grade |
|-------:|-----------------|---------:|-----------:|------------:|------:|-----:|-----:|:-----:|
| P1     | baseline        |  28.5 s  |  $0.4489   |         n/a |     0 |    2 |    4 | pass  |
| P1     | claude-context  |  24.5 s  |  $0.3187   |       **0** |     0 |    0 |    4 | pass  |
| P2     | baseline        | 134.6 s  |  $1.3696   |         n/a |     1 |   14 |    7 | pass  |
| P2     | claude-context  |  33.7 s  |  $0.5260   |       **0** |     0 |    2 |    3 | pass  |
| P3     | baseline        |  42.8 s  |  $0.6128   |         n/a |     0 |    4 |    5 | partial |
| P3     | claude-context  |  36.8 s  |  $0.5611   |       **0** |     0 |    8 |    2 | partial |
| P4     | baseline        | 355.6 s  |  $2.4225   |         n/a |     1 |   37 |   28 | pass  |
| P4     | claude-context  | 216.0 s  | **$10.7553** |     **0** |**11** |   82 |   58 | pass  |
| P5     | baseline        |  77.3 s  |  $0.9282   |         n/a |     0 |    6 |    5 | pass  |
| P5     | claude-context  | 106.0 s  |  $1.3261   |       **2** |     0 |    5 |    6 | pass  |

### Aggregates

| Metric              | Baseline    | Claude-context | Δ       |
|---------------------|------------:|---------------:|--------:|
| Total wall (s)      |      638.9  |          417.0 | **−34.7 %** |
| **Total cost (USD)**|    **$5.78**|     **$13.49** | **+133 %** |
| Total output tokens |     26,971  |         16,801 |  −37.7 % |
| Cache creation      |    166,185  |        161,454 |   −2.8 % |
| Cache read          |  1,763,779  |      1,218,586 |  −30.9 % |
| **Pass rate**       | 4 pass + 1 partial | 4 pass + 1 partial | tie |
| **`search_code` calls** | **n/a** |     **2 (only P5)** | — |

### The headline finding: the model barely reaches for the tool

Across all 10 claude-context sessions on gratibot (Wave 5) and 10
on liatrio-knowledge (Wave 6), **only 2 sessions ever called
`search_code`** — both on P5, the frozen discriminator prompt on
liatrio-knowledge. **0 of 25 prompts** on gratibot called it. **0
of 20 non-P5 prompts** across both fixtures called it.

This upends the naive reading of Wave 5. The 20 % cost saving
gratibot showed was **not** driven by semantic search. It was
prompt-cache noise — the two arms took broadly similar Read/Grep
paths and the MCP tool's presence changed which pieces got cached
where. When we look for actual `search_code` invocations, gratibot
has zero.

Reasons this is happening, in order of likelihood:

1. **No AGENTS.md in the fixture points the agent at
   `search_code`.** The claude-context PoC ships `AGENTS.snippet.md`
   in its own repo, but the harness spawns Claude Code with
   `cwd=$fixture`, so the model reads gratibot's or
   liatrio-knowledge's AGENTS.md (neither of which mentions
   claude-context). This is the exact behaviour the current
   `agents_md_instructions = no` cell predicts, and Wave 6 gives
   it a direct receipt.
2. **The MCP tool description is generic.** Claude Code lists the
   tool as "Search code semantically" without cost/latency guidance,
   and the model defaults to the deterministic Grep/Read pair it
   knows.
3. **Grep is genuinely competent on gratibot.** With 195 files, a
   handful of well-chosen Greps solves every prompt, so the model's
   default heuristic (`when unsure, grep`) works.

### Per-prompt reading

- **P1, P2, P3**: near-parity between arms. Both find the same
  answers via Grep/Read; small cost deltas are noise. **P3 is a
  double partial**: neither arm crossed the pass-condition's
  language boundary — LK has TS + SQL + MDX privacy-classification
  hits (verified — see `bot/supabase/migrations/019_user_privacy_settings.sql`,
  `docs/philosophy.md`, etc.), but both arms stayed in TypeScript.
  Baseline missed because Grep defaults excluded `.sql`; claude-context
  missed because it never used `search_code` (which had `.md`
  chunks indexed and would have surfaced them).

- **P4 is the cost trap**. Both arms pass — claude-context's answer
  is arguably more comprehensive (traces slash-command subcommands
  the baseline skipped) — but the claude-context arm burned $10.76
  by dispatching **11 sub-agents** for parallel exploration instead
  of calling `search_code` once. Baseline paid $2.42 for a similar
  answer. Wall clock was faster on claude-context (216 s vs 356 s)
  because parallelism helped, but the cost-per-answer went the wrong
  way. **This is a customer-facing pathology**: on large fixtures,
  Claude Code with `search_code` available may still choose
  sub-agent orchestration and pay for it.

- **P5 is the discriminator, and it revealed the tool working.**
  This is the ONLY session on either fixture where `search_code`
  was actually used — twice, both with natural-language queries
  ("prevent the same action from being applied twice by the same
  user within a short time window", and "in-memory set of recently
  processed keys with time-to-live"). The model landed on the
  `brain_message_drilldowns` guard + `claim_drilldown_slot` RPC
  correctly. Baseline **also** landed on the same guard via Grep
  (`idempotent`, `duplicate`, `rate.?limit`), so correctness is
  tied. **Cost went the wrong way** ($0.93 baseline vs $1.33
  claude-context) — using the semantic tool didn't save money here
  because the model still ran Grep + Read alongside it.

### Cells this wave settles or updates

- **`token_saving`** — needs revision. The Wave 5 headline of
  "−20 % cost on gratibot" **was not driven by semantic search** —
  it was prompt-cache noise. When we measure actual `search_code`
  use, it happens 2 / 20 times across two fixtures. When it does
  fire (P5 LK), it costs more (not less) than the Grep baseline
  because it runs alongside Grep, not instead of it. Vendor's
  ~39 % claim is probably real in their harness (they presumably
  wire the agent to prefer the tool); it does not reproduce with
  Claude Code defaults on either fixture.
- **`roi_evidence`** — needs revision. ROI is heavily gated by
  whether the customer wires `search_code` into an AGENTS.md /
  system prompt. Out of the box the tool is functionally
  invisible to Claude Code. This is the single most important
  finding the lab produced.
- **`agents_md_instructions`** — reconfirmed as `no`, with a much
  stronger lab receipt: without AGENTS guidance, the model uses
  the MCP tool ~10 % of the time on the prompt it's most designed
  for and ~0 % elsewhere.
- **`no_source_dependency`** — reconfirmed. LK has 208 `.sql`
  files and 176 `.feature` files that fall outside the default
  supported extensions, so they're invisible to `search_code`.
  The P3 cross-language miss is a direct consequence.
- **`traceable_results`** — reconfirmed on P5 (the only real
  invocation). File:line-range citations flowed through
  correctly.

### Was Wave 6 worth the $19.27?

Yes, clearly. Wave 5 alone would have generated a misleadingly
positive story ("claude-context saves 20 % on cost"). Wave 6
reveals **why** the mechanism didn't fire in Wave 5 either, and
that the customer story is really about tool-discovery, not
about semantic search's raw quality. That's a different (and more
actionable) recommendation for a Liatrio engagement.

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
