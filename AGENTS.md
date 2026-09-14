# Agent notes — `ai-code-intelligence-claude-context`

This is the PoC repo for the claude-context lab. The research pointer
lives at [`labs/claude-context/README.md`](https://github.com/liatrio/ai-code-intelligence/blob/main/labs/claude-context/README.md);
the reproducible protocol, harness, and results live *here*.

## What this PoC is for

Two things:

1. **Score the cells in `research/claude-context/data.json` from
   evidence, not marketing.** claude-context ships two very different
   default stacks — quickstart (Zilliz Cloud + OpenAI) vs FAQ
   (Milvus + Ollama). The research capability matrix scores what happens
   on the *local* path, because that is what a Liatrio client with a
   bring-your-own-cloud policy can actually adopt. `setup.py` refuses to
   flip onto the hosted path (`FORBIDDEN_ENV_VARS` in `versions.env`), so
   every wave in `RESULTS.md` is a measurement of the local recipe.
2. **Let another engineer or a client reproduce the numbers.** Pinned
   versions in `tools.lock.json` and `versions.env`, deterministic
   `setup.py --check`, fixture provenance recorded per-run. Fresh clone
   → `make check` → `make install` → `make index` should produce the
   same shape of output as the wave notes.

## What it is not for

- Not a benchmark of Zilliz Cloud, OpenAI, Voyage, Gemini, or OpenRouter.
- Not a benchmark of GPU-accelerated Milvus.
- Not a comparison of claude-context against CocoIndex Code, RepoWise,
  or SocratiCode. Cross-tool comparison lives on the research repo's
  matrix, not here.
- Not a chat interface for the fixture. Sessions are single-shot; the
  harness measures one question per session.

## Rules the harness enforces

- Fresh shell; no `OPENAI_API_KEY`, no `ZILLIZ_*`, no `VOYAGEAI_API_KEY`,
  no `GEMINI_API_KEY`, no `OPENROUTER_API_KEY`. If any of these leak in
  from a `.envrc` or a user profile, `setup.py --check` refuses.
- Transcripts do not land inside this repo or the research repo.
  Default landing is `~/.cache/ai-code-intelligence/claude-context/harness-runs/`
  (or the XDG / macOS equivalent).
- Both arms run with the same tool budget; the *only* difference is
  whether the `claude-context` MCP server is registered.
- Pass conditions in `prompts.md` are frozen before any run. Regrading
  a session after the fact is not allowed.

## Where to look for evidence

- Wave-by-wave notes and probe details: `RESULTS.md` in this repo.
- Cells settled and the exact `note` text used: `research/claude-context/data.json`
  on the research repo (updated on the corresponding research-repo branch).
- Every claim scored `no` or `no default` has a matching probe
  documented in `RESULTS.md` — usually a `lsof` snapshot, a docker
  `inspect`, or a Milvus data-file directory listing.
