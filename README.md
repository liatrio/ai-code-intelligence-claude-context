# `ai-code-intelligence-claude-context`

A stand-alone reproducible lab for
[`@zilliz/claude-context`](https://github.com/zilliztech/claude-context)
against the AI-Code-Intelligence research repo
[`liatrio/ai-code-intelligence`](https://github.com/liatrio/ai-code-intelligence),
tracking issue
[#84](https://github.com/liatrio/ai-code-intelligence/issues/84).

Sibling PoCs (same shape, different tool):
[`ai-code-intelligence-semgrep`](https://github.com/liatrio/ai-code-intelligence-semgrep),
[`ai-code-intelligence-codebase-memory`](https://github.com/liatrio/ai-code-intelligence-codebase-memory),
[`ai-code-intelligence-socraticode`](https://github.com/liatrio/ai-code-intelligence-socraticode),
[`ai-code-intelligence-gitnexus`](https://github.com/liatrio/ai-code-intelligence-gitnexus),
[`ai-code-intelligence-graphify`](https://github.com/liatrio/ai-code-intelligence-graphify),
[`ai-code-intelligence-repowise`](https://github.com/liatrio/ai-code-intelligence-repowise).

## Family

**Indexing.** claude-context is a semantic-retrieval MCP server: AST-aware
chunks embedded into a vector index, hybrid BM25 + dense-vector search,
Merkle-tree incremental sync. Answers "*where does the code for concept
X live?*" and "*is there already a helper that does Y?*" It does not
answer "*who calls X?*" — that is a structural-graph tool's job.

## What this lab measures

Six-wave protocol against the fully-local claude-context path (Milvus in
Docker Compose + Ollama for embeddings). The lab deliberately does **not**
exercise the quickstart-default hosted path (Zilliz Cloud + OpenAI); see
`AGENTS.md` for why, and the `no_default_egress` cell on
[`research/claude-context/data.json`](https://github.com/liatrio/ai-code-intelligence/blob/main/research/claude-context/data.json)
for what the `lsof` probe covers when the two paths are compared.

- **Fixtures**: `liatrio/gratibot` (public, JS/Node, 195 files) and
  `liatrio-labs/liatrio-knowledge` (private, TS/SQL/Gherkin/Docusaurus,
  5,370 tracked files).
- **Harness arms**: `baseline` (Read/Grep only) vs `claude-context`
  (Read/Grep/Bash **plus** the pinned MCP server).
- **Prompts**: five semantic-retrieval prompts with pass conditions
  frozen in `prompts.md` before any run.
- **Waves**: install/index smoke, yes-cell confirmations, no-cell
  confirmations, shared/gateway probes, gratibot harness, liatrio-
  knowledge harness. Results in `RESULTS.md`.

## Prerequisites

- Node ≥ 20, npm ≥ 10 (claude-context's monorepo engines minimum).
- Docker ≥ 20.10.13 with `docker compose` v2 (for Milvus standalone).
- [Ollama](https://ollama.com/download) ≥ 0.3.0, running on `127.0.0.1:11434`.
- Claude Code CLI (`claude` or `claude-code`) on PATH.

No cloud accounts, no API keys, no login flow. `setup.py --check` will
refuse to proceed if any hosted-provider env var is set (see
`FORBIDDEN_ENV_VARS` in `versions.env`).

## Contract files (#75)

| Contract file       | Purpose                                                             |
| ------------------- | ------------------------------------------------------------------- |
| `setup.py`          | `--check`, `--install`, `--index`, `--status`, `--clean`             |
| `AGENTS.snippet.md` | Paste-in snippet for a client project's `AGENTS.md`                  |
| `prompts.md`        | 5 prompts + frozen pass conditions                                  |
| `RESULTS.md`        | Wave-by-wave findings; grows as waves land                          |
| `run-prompts.py`    | Two-arm Claude Code harness                                         |

## Usage

Clone a fixture outside this repo:

```bash
git clone https://github.com/liatrio/gratibot.git ~/liatrio/repos/gratibot
```

Bring up the local stack and index the fixture:

```bash
make check                                                # env gate
make install                                              # npm + docker compose + ollama pull
python3 setup.py --index --fixture ~/liatrio/repos/gratibot
```

Run the harness:

```bash
python3 run-prompts.py --fixture ~/liatrio/repos/gratibot
```

Tear it all down:

```bash
make clean
```

## Where the numbers land

- Wave-by-wave rationale and probe details: [`RESULTS.md`](RESULTS.md).
- Cells settled by the lab: [`research/claude-context/data.json`](https://github.com/liatrio/ai-code-intelligence/blob/main/research/claude-context/data.json).
- Cell rationale: [`research/claude-context/answers.md`](https://github.com/liatrio/ai-code-intelligence/blob/main/research/claude-context/answers.md).

## Licence

The lab code in this repository is MIT.
[`@zilliz/claude-context-mcp`](https://www.npmjs.com/package/@zilliz/claude-context-mcp)
and
[`@zilliz/claude-context-core`](https://www.npmjs.com/package/@zilliz/claude-context-core)
are MIT.
[Milvus](https://github.com/milvus-io/milvus) is Apache-2.0.
[Ollama](https://github.com/ollama/ollama) is MIT.
`nomic-embed-text` (the pinned embedding model) is Apache-2.0.
