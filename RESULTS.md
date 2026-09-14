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

**Status**: pending

Planned probes:
- `make check` — every environment gate passes, no forbidden env vars set.
- `make install` — wall clock for `npm install`, `docker compose up -d`,
  `ollama pull nomic-embed-text`.
- `make index FIXTURE=~/liatrio/repos/gratibot` — wall clock for first-index,
  final Milvus collection size (`docker exec cc-lab-milvus ls -la /var/lib/milvus`),
  number of chunks indexed.
- Sanity search via the MCP server: one hand-crafted query, verify hits
  include the expected file:line range.

---

## Wave 2 — yes-cell confirmations on gratibot

**Status**: pending

Planned probes:
- `vector_store_local` — inspect `./volumes/milvus/` to confirm on-disk
  vectors are present locally after Wave 1's index.
- `local_embeddings` — kill outbound network for the duration of a
  second `--index` run (either by `pfctl` block on 80/443 to non-loopback
  or by watching `lsof -iTCP -sTCP:ESTABLISHED` and confirming no
  sockets to non-loopback). Wall clock should be indistinguishable from
  Wave 1's second run.
- `agents_md_instructions` — JSON-RPC `initialize` + `tools/list` probe
  against `node dist/index.js` in the pinned MCP; record advertised
  tool names and counts.
- `traceable_results` — call `search_code` on a canned query; verify
  each hit has `path`, `start.line`, `end.line`, `score`.

---

## Wave 3 — no-cell and defaults confirmations

**Status**: pending

Planned probes:
- `no_default_egress` — this is the headline probe. Run in two modes,
  captured 30s each with `lsof -iTCP -sTCP:ESTABLISHED`:
  1. **Stock quickstart** (out of scope for the lab but documented
     here for completeness): if the README's Zilliz + OpenAI env vars
     were set, what would leak. Recorded from source inspection only,
     not measured, because the lab refuses to run that path.
  2. **Local-only** (the pinned lab path): measured. Expect zero
     non-loopback sockets during boot and a Wave-1 index.
- `semantic_cache` — five back-to-back searches of the same query
  against the same collection; wall clock and result determinism.
- `no_source_dependency` — populate `node_modules/` in gratibot, verify
  claude-context respects `.gitignore` and does not index it.

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
