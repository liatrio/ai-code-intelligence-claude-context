<!--
This snippet is meant to be pasted into a client project's AGENTS.md
alongside snippets from other AI-code-intelligence tools. It says one
thing: when the agent is asking a *semantic* question about the codebase
— "is there already something that does X?", "what other places use a
similar pattern?", "where does the code for concept Y live?" — reach for
claude-context. When the agent is asking a *structural* question —
"who calls this?", "what breaks if I change this signature?", "how does
value V flow from source to sink?" — that is a different tool's job.

The snippet composes with sibling tool snippets. It does not tell the
agent to use claude-context for everything; it tells the agent to notice
which shape of question it is asking and pick the tool that answers that
shape.
-->

# claude-context

**When to reach for it**

Use claude-context when your question is about **finding code by concept
or intent** rather than by name or structure:

- "Is there already a helper that formats a duration as a human-readable
  string?"
- "Where is the code that handles rate-limit backoff for the Slack API?"
- "Show me every place that looks like it validates a Bolt event payload."
- "What are the existing implementations of a middleware that redacts PII
  before logging?"
- "Are there other places in this codebase that do session cleanup on
  process exit?"

The pattern: you have a *concept* in mind, not a symbol name or a call
graph question. Grep will only match if you already know the words; a
call-graph tool needs a starting node. claude-context asks a vector
index built from AST-aware chunks + BM25 keywords, so it can bridge
"payload sanitiser" the human said and `scrubSensitiveFields` the code
called it.

**When NOT to reach for it**

- "Who calls `X`?" — use a call-graph or LSP-shaped tool.
- "What breaks if I change this function's signature?" — a
  structural-graph or type-aware tool.
- "Does user input reach this sink?" — a taint / SAST tool (Semgrep).
- "Show me every implementation of interface `Y`." — LSP find-implementations.

**How to call it**

The MCP server is `@zilliz/claude-context-mcp`, wired over stdio. The
lab pins the fully-local configuration: Milvus (Docker Compose,
loopback) + Ollama (`nomic-embed-text`). No Zilliz Cloud, no OpenAI
key, no external network dependency.

Available tools:

- `index_codebase(path, force?)` — build or refresh the collection.
  The path becomes the identity (MD5 of absolute path); use one
  canonical absolute path per codebase or you will get two collections.
- `search_code(query, path, limit?)` — semantic + BM25 hybrid search.
  Returns file, line range, and matched chunk.
- `clear_index(path)` — drop the collection for a path.
- `get_indexing_status(path)` — poll during a large first index.

**Freshness owner**

claude-context ships **Merkle-tree incremental sync**: after a first
full index, subsequent `index_codebase` calls detect changed chunks
and re-embed only those. The lab measures how much of the "seconds on
a typical PR" claim survives contact with real fixtures — see the
`incremental_reindex` cell on `research/claude-context/data.json`
before quoting the number.

**One rule for composition**

If you also have a structural-graph MCP (GitNexus, CodebaseMemory,
Graphify) or SCIP indexer wired in, ask claude-context *first* when
the question is about concept discovery. Take the file paths it
returns and hand them to the structural tool for a "now, who calls
this?" follow-up. Reversing that order — asking a graph tool a
concept question — burns tokens on structural traversals that never
converge on the right node.
