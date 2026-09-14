# claude-context prompts

Five prompts, two arms, two fixtures. Pass conditions are frozen here
before any run — do not edit them after Wave 1 boots.

Each prompt is designed to exercise **semantic retrieval**, the trade
claude-context is scored on in `research/claude-context/data.json`. The
baseline arm (Read / Grep only) can answer every prompt with enough
effort; the claude-context arm gets a semantic index. The 20 sessions
(5 prompts × 2 arms × 2 fixtures) settle whether the vector index
buys correctness, wall-clock, cost, or (for a fair `no`) none of them.

Discriminator (Prompt 5): the last prompt is the one where grep-only
should struggle, because the concept the human describes never appears
literally in the code. Answering it correctly requires either
extensive Read exploration or a semantic index — this is the prompt
claude-context is designed for.

## Fixtures

- **`gratibot`** — Waves 1–5, public JS/Node, 195 files.
- **`liatrio-knowledge`** — Wave 6, private TS/SQL/Gherkin/Docusaurus,
  5,370 tracked files.

Both fixtures are addressed by absolute path (`--fixture` on `setup.py
--index`, `CLAUDE_CONTEXT_FIXTURE` env var elsewhere).

## Prompt 1 — Concept discovery

> "Is there existing code in this repository that formats or generates a
> human-readable time span or duration (e.g. 'about 3 hours ago', '2
> days')? If so, name the file(s) and describe the function(s)."

**Pass conditions**

- On `gratibot`: cites `service/timeouts.js` (or the file that owns
  `remainingHoursUntilReset` / cooldown-time math) and names the
  function(s) that produce a human-facing duration string. A miss is
  citing a file that *reads* the timestamp but does not format one.
- On `liatrio-knowledge`: cites at least one TS or MDX file that
  actually formats a duration for user display; a bare `Date` import
  or `Intl.RelativeTimeFormat` symbol alone does not pass.
- Answers `no such helper exists` unambiguously if the search is
  exhausted and nothing matches (allowed pass — the point is
  correctness, not manufactured hits).

## Prompt 2 — Duplicate-detection / "is there already"

> "Is there already a helper that returns the count of gratitudes /
> recognitions a user has received in the last N days? If so, quote
> the function signature and the file. If not, list the closest
> existing helpers I could compose."

**Pass conditions**

- On `gratibot`: names the recognition-count-in-window function (in
  `service/recognition.js` or the nearest owning module) OR names the
  two closest primitives it would be built from and calls out that no
  single-helper exists.
- On `liatrio-knowledge`: same shape against whichever domain object
  the fixture models (issue counts, doc-view counts, sprint
  velocity — one clean pass condition per fixture, decided at Wave 6
  before results are graded).

## Prompt 3 — Cross-language / mixed-file concept

> "Where in this codebase is the logic that decides whether a message
> should be redacted, sanitised, or otherwise transformed before it is
> stored or displayed? Give file paths and a one-line description of
> each site."

**Pass conditions**

- Names at least two of: input validation, escape/scrub, template
  rendering escape, structured-log field redaction. A single hit is
  a fail — the concept is deliberately plural and the point is to
  see whether the tool assembles the concept from multiple sites.
- On `liatrio-knowledge`: at least one hit must span a language
  boundary (TS + SQL, or MDX + TS) — this is where a JS-only grep
  would drop hits.

## Prompt 4 — Pattern-shape ("show me every place that…")

> "Show me every place in this codebase that reacts to a Slack event
> by writing to the database. For each site, give the file, the line
> range of the handler, and one sentence describing what is written."

**Pass conditions**

- On `gratibot`: names both the recognition path (`features/recognize.js`
  → `insertOne` in `service/recognition.js`) and the deduction path
  (`service/deduction.js:createDeduction`). Missing one is a partial
  pass; missing both is a fail.
- On `liatrio-knowledge`: whatever the fixture equivalent is (Slack
  event ingest → DB write); decided at Wave 6 pre-grade.

## Prompt 5 — Discriminator (semantic > grep)

> "This codebase has some form of *idempotency guard* — a check that
> prevents the same action from being applied twice by the same user
> in a short window (regardless of what it's called in the code). Find
> it. Explain the mechanism (in-memory set, DB lookup, TTL, per-user
> vs global) and the file(s) that implement it."

**Pass conditions**

- Names the correct file(s): on `gratibot`, this is the
  `service/deduction.js` + `service/recognition.js` guard(s) that
  reject a repeat action within the cooldown window; the word
  "idempotency" does not appear in the source, so pass **requires**
  identifying the mechanism (cooldown timer, uniqueness check on
  timestamp+user, or the rate-limit filter — whichever the fixture
  actually implements).
- Baseline arm may still pass on `gratibot` (195 files is grep-able
  with concept keywords), but the *cost* difference is what the wave
  measures. On `liatrio-knowledge`'s 5,370 files, the discriminator
  is expected to bite — this is the prompt where semantic search
  should out-perform grep on both wall-clock and correctness.

## Grading

Each session lands one of `pass`, `partial`, `fail`, judged against
the pass conditions above with no re-interpretation after seeing
results. `partial` on Prompt 4 (one path, not both) counts as
`partial`, not `pass`, for the ROI tally.

Both arms are run with the same tool budget (Read, Grep, Bash) and
the same system prompt. The only difference between arms is whether
the `claude-context` MCP server is registered. The harness
(`run-prompts.py`) enforces this.
