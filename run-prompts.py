#!/usr/bin/env python3
"""
run-prompts.py — two-arm Claude Code harness for the claude-context lab.

Shape mirrors the harnesses in sibling PoCs (CBM, Semgrep). Differences
called out inline:

* Arm A ("baseline"): claude-code is spawned with Read, Grep, and Bash
  only. No MCP server registered.
* Arm B ("claude-context"): same tool budget PLUS the pinned
  `@zilliz/claude-context-mcp` server, wired over stdio into
  claude-code's `--mcp-config` file. The server reads a per-run env
  block from setup.py's pinned versions.env, so no OPENAI_* / ZILLIZ_*
  can leak in from the operator's shell.

Guards:

* Refuses to write transcripts into the PoC repo or the research repo,
  because a session transcript can contain the entire liatrio-knowledge
  fixture in its context and neither repo should ever hold that. Default
  landing is `$XDG_CACHE_HOME/ai-code-intelligence/claude-context/harness-runs/`.
* Refuses to start if any FORBIDDEN_ENV_VARS is set.
* Refuses to start unless setup.py --check passes.

One JSON line per session appears on stdout for the wave notes; full
transcripts + cost breakdowns are written to per-session files under
the runs directory.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
PROMPTS_PATH = REPO_ROOT / "prompts.md"
SETUP_PY = REPO_ROOT / "setup.py"

# The research repo lives next to this PoC on the operator's disk.
# We block transcripts from landing anywhere inside it (or inside this
# repo) because either would leak fixture content into a git tree.
FORBIDDEN_RUN_ROOTS = [
    REPO_ROOT,
    REPO_ROOT.parent / "ai-code-intelligence",
]


def default_runs_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "ai-code-intelligence" / "claude-context" / "harness-runs"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ai-code-intelligence" / "claude-context" / "harness-runs"
    return Path.home() / ".cache" / "ai-code-intelligence" / "claude-context" / "harness-runs"


def assert_runs_dir_safe(runs_dir: Path) -> None:
    resolved = runs_dir.resolve()
    for bad in FORBIDDEN_RUN_ROOTS:
        try:
            resolved.relative_to(bad.resolve())
        except ValueError:
            continue
        raise SystemExit(
            f"Refusing to write harness transcripts under {bad}. "
            f"Set --runs-dir to a path outside every checked-in repo."
        )


# --------------------------------------------------------------------------
# Prompts loader
# --------------------------------------------------------------------------


@dataclasses.dataclass
class Prompt:
    id: str
    title: str
    question: str
    pass_conditions: str


_PROMPT_HEADER = re.compile(r"^##\s+Prompt\s+(\d+)\s+—\s+(.+)$")


def load_prompts(path: Path) -> list[Prompt]:
    """Extract the five prompts from prompts.md.

    Each prompt is a section starting with `## Prompt N — Title`. The
    quoted block that follows (`> "..."`) is the question the model
    sees; the `**Pass conditions**` block is metadata the harness does
    not send to the model (grading happens post-hoc).
    """
    text = path.read_text()
    prompts: list[Prompt] = []
    current_id: str | None = None
    current_title: str | None = None
    current_question: list[str] = []
    current_pass: list[str] = []
    mode: str | None = None  # "question" | "pass" | None
    for line in text.splitlines():
        m = _PROMPT_HEADER.match(line)
        if m:
            if current_id and current_title:
                prompts.append(
                    Prompt(
                        id=f"P{current_id}",
                        title=current_title.strip(),
                        question=_clean_question("\n".join(current_question)),
                        pass_conditions="\n".join(current_pass).strip(),
                    )
                )
            current_id = m.group(1)
            current_title = m.group(2)
            current_question = []
            current_pass = []
            mode = "question"
            continue
        if line.startswith("**Pass conditions**"):
            mode = "pass"
            continue
        if line.startswith("## "):
            # A new top-level section that isn't a prompt (like Grading).
            if current_id and current_title:
                prompts.append(
                    Prompt(
                        id=f"P{current_id}",
                        title=current_title.strip(),
                        question=_clean_question("\n".join(current_question)),
                        pass_conditions="\n".join(current_pass).strip(),
                    )
                )
                current_id = None
                current_title = None
                current_question = []
                current_pass = []
                mode = None
            continue
        if mode == "question":
            current_question.append(line)
        elif mode == "pass":
            current_pass.append(line)
    if current_id and current_title:
        prompts.append(
            Prompt(
                id=f"P{current_id}",
                title=current_title.strip(),
                question=_clean_question("\n".join(current_question)),
                pass_conditions="\n".join(current_pass).strip(),
            )
        )
    return prompts


def _clean_question(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(">"):
            s = s.lstrip("> ").strip()
        lines.append(s)
    result = " ".join(lines).strip()
    # Strip surrounding quotes if the whole prompt was written as > "..."
    # spanning multiple lines (the per-line check misses the wrap-around
    # case). Only strip when both ends match — never inside the string.
    if result.startswith('"') and result.endswith('"'):
        result = result[1:-1]
    return result


# --------------------------------------------------------------------------
# Environment gate
# --------------------------------------------------------------------------


FORBIDDEN_ENV_VARS_DEFAULT = [
    "OPENAI_API_KEY",
    "VOYAGEAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ZILLIZ_URI",
    "ZILLIZ_CLOUD_URI",
    "ZILLIZ_TOKEN",
    "ZILLIZ_CLOUD_TOKEN",
]


def check_forbidden_env() -> list[str]:
    return [k for k in FORBIDDEN_ENV_VARS_DEFAULT if os.environ.get(k)]


def require_setup_check_pass() -> None:
    proc = subprocess.run(
        [sys.executable, str(SETUP_PY), "--check"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(
            "setup.py --check failed; refusing to start harness. Output:\n"
            + proc.stdout + proc.stderr
        )


# --------------------------------------------------------------------------
# MCP config synthesis
# --------------------------------------------------------------------------


def load_versions_env() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in (REPO_ROOT / "versions.env").read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def mcp_config_for(fixture: Path) -> dict[str, Any]:
    """Emit an mcp-config JSON that claude-code will consume for Arm B."""
    vers = load_versions_env()
    mcp_entry = str(REPO_ROOT / "node_modules" / "@zilliz" / "claude-context-mcp" / "dist" / "index.js")
    return {
        "mcpServers": {
            "claude-context": {
                "command": "node",
                "args": [mcp_entry],
                "env": {
                    "EMBEDDING_PROVIDER": vers["EMBEDDING_PROVIDER"],
                    "EMBEDDING_MODEL": vers["EMBEDDING_MODEL"],
                    "EMBEDDING_BASE_URL": vers["EMBEDDING_BASE_URL"],
                    "MILVUS_ADDRESS": f"{vers['MILVUS_HOST']}:{vers['MILVUS_GRPC_PORT']}",
                    "MILVUS_TOKEN": vers.get("MILVUS_TOKEN", ""),
                    "CLAUDE_CONTEXT_FIXTURE": str(fixture),
                },
            }
        }
    }


# --------------------------------------------------------------------------
# Claude Code invocation
# --------------------------------------------------------------------------


CLAUDE_BIN_ENV = "CLAUDE_CODE_BIN"


def claude_bin() -> str:
    override = os.environ.get(CLAUDE_BIN_ENV)
    if override:
        return override
    for cand in ["claude", "claude-code"]:
        found = shutil.which(cand)
        if found:
            return found
    raise SystemExit(
        f"Could not find `claude` or `claude-code` on PATH. Set {CLAUDE_BIN_ENV} to override."
    )


def run_session(
    *,
    prompt: Prompt,
    arm: str,
    fixture: Path,
    runs_dir: Path,
    mcp_config_path: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    """Spawn one claude-code session, capture stream-json output.

    Returns a summary dict suitable for one JSON line on stdout.
    """
    session_id = f"{arm}--{prompt.id}--{fixture.name}--{int(time.time())}"
    session_dir = runs_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    argv: list[str] = [
        claude_bin(),
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", "acceptEdits",
    ]
    # Tool budget: Read, Grep, Bash for both arms; Arm B additionally
    # gets any tools the claude-context MCP registers.
    allowed_tools = ["Read", "Grep", "Bash"]
    if arm == "claude-context":
        argv += ["--mcp-config", str(mcp_config_path)]
        # Grant the MCP server's tools; MCP prefixes are `mcp__<server>__<tool>`.
        allowed_tools += [
            "mcp__claude-context__index_codebase",
            "mcp__claude-context__search_code",
            "mcp__claude-context__get_indexing_status",
        ]
    argv += ["--allowedTools", ",".join(allowed_tools)]

    system_prompt = (
        "You are answering a single-shot question about the codebase at "
        f"{fixture}. You have Read, Grep, and Bash. Answer concisely with "
        "file:line citations. Do not modify any file. When asked to look "
        "for a concept, prefer the search tool most suited to *concept* "
        "questions; when asked about structure or callers, prefer Grep/Read."
    )
    argv += ["--append-system-prompt", system_prompt]
    argv += [prompt.question]

    (session_dir / "argv.json").write_text(json.dumps(argv, indent=2))
    if dry_run:
        return {
            "session_id": session_id,
            "arm": arm,
            "prompt_id": prompt.id,
            "fixture": str(fixture),
            "dry_run": True,
            "argv": argv,
        }

    started = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=str(fixture),
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    wall = time.monotonic() - started

    (session_dir / "stdout.jsonl").write_text(proc.stdout)
    (session_dir / "stderr.log").write_text(proc.stderr)

    # Parse the final `result` line for cost + token totals if present.
    cost_usd: float | None = None
    total_tokens: dict[str, int] | None = None
    result_text: str | None = None
    for line in reversed(proc.stdout.splitlines()):
        if not line.strip():
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "result":
            cost_usd = evt.get("total_cost_usd")
            usage = evt.get("usage") or {}
            total_tokens = {
                "input": usage.get("input_tokens"),
                "output": usage.get("output_tokens"),
                "cache_creation": usage.get("cache_creation_input_tokens"),
                "cache_read": usage.get("cache_read_input_tokens"),
            }
            result_text = evt.get("result") or evt.get("message", {}).get("content")
            break

    summary = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "arm": arm,
        "prompt_id": prompt.id,
        "prompt_title": prompt.title,
        "fixture": str(fixture),
        "wall_seconds": round(wall, 3),
        "exit_code": proc.returncode,
        "cost_usd": cost_usd,
        "tokens": total_tokens,
        "result_text": result_text,
        "session_dir": str(session_dir),
    }
    (session_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run-prompts.py", description="claude-context two-arm harness")
    p.add_argument("--fixture", required=True, help="Absolute path to the fixture repo")
    p.add_argument(
        "--arms",
        default="baseline,claude-context",
        help="Comma-separated arms to run (default: both)",
    )
    p.add_argument(
        "--prompts",
        default="P1,P2,P3,P4,P5",
        help="Comma-separated prompt IDs to run (default: all five)",
    )
    p.add_argument(
        "--runs-dir",
        default=str(default_runs_dir()),
        help=f"Where to write per-session transcripts (default: {default_runs_dir()})",
    )
    p.add_argument("--dry-run", action="store_true", help="Print argv without spawning claude")
    p.add_argument("--skip-check", action="store_true", help="Skip setup.py --check gate (not recommended)")
    return p


def main() -> int:
    args = build_parser().parse_args()

    hits = check_forbidden_env()
    if hits:
        raise SystemExit(
            "Refusing to start: forbidden env vars set: " + ", ".join(hits) + ". "
            "Unset them or start a fresh shell — the lab measures the local-only path."
        )

    if not args.skip_check:
        require_setup_check_pass()

    fixture = Path(args.fixture).expanduser().resolve()
    if not fixture.exists():
        raise SystemExit(f"Fixture path missing: {fixture}")

    runs_dir = Path(args.runs_dir).expanduser().resolve()
    assert_runs_dir_safe(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)

    prompts_all = load_prompts(PROMPTS_PATH)
    want_ids = {s.strip() for s in args.prompts.split(",") if s.strip()}
    prompts = [p for p in prompts_all if p.id in want_ids]
    if not prompts:
        raise SystemExit(f"No prompts matched --prompts={args.prompts}")

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in arms:
        if arm not in {"baseline", "claude-context"}:
            raise SystemExit(f"Unknown arm: {arm}. Valid: baseline, claude-context")

    mcp_config_path: Path | None = None
    if "claude-context" in arms:
        mcp_config_path = runs_dir / f"mcp-config-{fixture.name}.json"
        mcp_config_path.write_text(json.dumps(mcp_config_for(fixture), indent=2))

    print(json.dumps({"harness": "start", "fixture": str(fixture), "runs_dir": str(runs_dir),
                       "arms": arms, "prompts": [p.id for p in prompts]}))
    for arm in arms:
        for prompt in prompts:
            summary = run_session(
                prompt=prompt,
                arm=arm,
                fixture=fixture,
                runs_dir=runs_dir,
                mcp_config_path=mcp_config_path if arm == "claude-context" else None,
                dry_run=args.dry_run,
            )
            print(json.dumps(summary))
    print(json.dumps({"harness": "done", "fixture": str(fixture), "runs_dir": str(runs_dir)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
