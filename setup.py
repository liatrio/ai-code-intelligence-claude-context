#!/usr/bin/env python3
"""
setup.py — install and drive the fully-local claude-context path for the lab.

Contract (#75 across the family):

  * Verifies environment: node, npm, docker, docker compose, ollama.
  * Refuses to proceed if any FORBIDDEN_ENV_VARS is set (see versions.env).
  * Installs pinned claude-context MCP + core packages into .cache/node_modules
    without touching global node_modules and without writing into the
    fixture repository.
  * Boots the pinned Milvus (standalone) stack via docker compose, bound to
    127.0.0.1 only.
  * Pulls the pinned Ollama embedding model.
  * Indexes a fixture path (`--index /abs/path`) by invoking the MCP server
    through its stdio JSON-RPC surface — this is what a real Claude Code
    session would do, so the wall-clock measured here is comparable.
  * Emits one JSON line per invocation summarising what happened, for the
    harness and for wave notes.

Not in scope: Zilliz Cloud, OpenAI/Voyage/Gemini/OpenRouter, LAN Milvus,
any hosted embedding endpoint. Those paths exist in claude-context — the
lab deliberately does not exercise them, because the whole point of the
`no_default_egress` cell is that the local path does not talk to any of
them, and the whole point of the private-fixture Wave 6 is that we can
run without a paid account.

Exit codes:
  0  success
  1  environment problem (missing tool, wrong version, forbidden env var set)
  2  install problem (npm failure, docker compose failure, ollama pull failure)
  3  index problem (fixture path missing, MCP surface unavailable, timeout)
  4  bad arguments
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent
VERSIONS_ENV_PATH = REPO_ROOT / "versions.env"
TOOLS_LOCK_PATH = REPO_ROOT / "tools.lock.json"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
NODE_MODULES_PREFIX = REPO_ROOT / ".cache"

# JSON summary lines are prefixed with this sentinel so the harness can
# `grep -E '^{"summary":' setup.py.log | tail -1` without accidentally
# picking up MCP tool-call JSON or Docker Compose progress noise.
SUMMARY_PREFIX = ""  # emit bare JSON on stdout; harness uses `grep -E '^{'`


# --------------------------------------------------------------------------
# versions.env loader
# --------------------------------------------------------------------------


def load_versions_env(path: Path) -> dict[str, str]:
    """Read a simple KEY=VALUE file, ignoring comments and blank lines.

    We do not use python-dotenv because this file has to boot on a stock
    Python 3 with only stdlib available.
    """
    if not path.exists():
        raise SystemExit(f"versions.env not found at {path}")
    out: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


VERSIONS = load_versions_env(VERSIONS_ENV_PATH)


def pin(key: str) -> str:
    if key not in VERSIONS:
        raise SystemExit(f"versions.env is missing required key: {key}")
    return VERSIONS[key]


# --------------------------------------------------------------------------
# Environment gate
# --------------------------------------------------------------------------


@dataclasses.dataclass
class CheckResult:
    ok: bool
    detail: str


def check_forbidden_env_vars() -> CheckResult:
    forbidden = [v.strip() for v in pin("FORBIDDEN_ENV_VARS").split(",") if v.strip()]
    hits = [name for name in forbidden if os.environ.get(name)]
    if hits:
        return CheckResult(
            False,
            "Refusing to proceed: the following env vars are set and would "
            "flip claude-context onto the hosted path this lab is not "
            f"measuring: {', '.join(hits)}. Unset them or use a fresh shell.",
        )
    return CheckResult(True, f"OK: none of {len(forbidden)} forbidden env vars set")


def check_node() -> CheckResult:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node:
        return CheckResult(False, "node not found on PATH")
    if not npm:
        return CheckResult(False, "npm not found on PATH")
    try:
        out = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
        # e.g. "v20.11.0"
        major = int(out.lstrip("v").split(".", 1)[0])
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"could not read node --version: {exc}")
    if major < 20:
        return CheckResult(False, f"node major {major} < 20 required by claude-context")
    return CheckResult(True, f"OK: node {out}, npm at {npm}")


def check_docker() -> CheckResult:
    docker = shutil.which("docker")
    if not docker:
        return CheckResult(False, "docker not found on PATH")
    try:
        out = subprocess.run(
            [docker, "version", "--format", "{{.Client.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        return CheckResult(False, f"docker daemon not reachable: {exc.stderr.strip()}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"docker version failed: {exc}")
    # docker compose (v2) sub-command:
    try:
        subprocess.run(
            [docker, "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"docker compose v2 not available: {exc}")
    return CheckResult(True, f"OK: docker {out} with compose v2")


def check_ollama() -> CheckResult:
    ollama = shutil.which("ollama")
    if not ollama:
        return CheckResult(
            False,
            "ollama not found on PATH — install from https://ollama.com/download "
            "or run `brew install ollama` on macOS. This lab pins the "
            "fully-local path; Ollama is not optional.",
        )
    try:
        out = subprocess.run(
            [ollama, "--version"], capture_output=True, text=True, timeout=10, check=True
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"could not read ollama --version: {exc}")
    return CheckResult(True, f"OK: {out}")


def run_all_checks() -> list[tuple[str, CheckResult]]:
    return [
        ("forbidden_env_vars", check_forbidden_env_vars()),
        ("node", check_node()),
        ("docker", check_docker()),
        ("ollama", check_ollama()),
    ]


# --------------------------------------------------------------------------
# Install: npm, docker compose up, ollama pull
# --------------------------------------------------------------------------


def _run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
         timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def npm_install() -> CheckResult:
    """Install the pinned MCP + core into .cache/node_modules."""
    NODE_MODULES_PREFIX.mkdir(parents=True, exist_ok=True)
    pkg = NODE_MODULES_PREFIX / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({"private": True, "name": "cc-lab-cache"}, indent=2))
    mcp = f"@zilliz/claude-context-mcp@{pin('CLAUDE_CONTEXT_MCP_VERSION')}"
    core = f"@zilliz/claude-context-core@{pin('CLAUDE_CONTEXT_CORE_VERSION')}"
    proc = _run(
        [
            "npm",
            "install",
            "--no-audit",
            "--no-fund",
            "--loglevel=error",
            mcp,
            core,
        ],
        cwd=NODE_MODULES_PREFIX,
        timeout=600,
    )
    if proc.returncode != 0:
        return CheckResult(False, f"npm install failed: {proc.stderr.strip()[:500]}")
    return CheckResult(True, f"OK: installed {mcp} and {core} into {NODE_MODULES_PREFIX}/node_modules")


def docker_compose_up() -> CheckResult:
    """Boot the Milvus stack via docker compose."""
    proc = _run(
        ["docker", "compose", "-f", str(COMPOSE_PATH), "up", "-d"],
        cwd=REPO_ROOT,
        timeout=600,
    )
    if proc.returncode != 0:
        return CheckResult(False, f"docker compose up failed: {proc.stderr.strip()[:500]}")
    # Poll Milvus healthcheck for up to 120s.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((pin("MILVUS_HOST"), int(pin("MILVUS_GRPC_PORT"))), timeout=2):
                return CheckResult(True, f"OK: Milvus reachable on {pin('MILVUS_HOST')}:{pin('MILVUS_GRPC_PORT')}")
        except OSError:
            time.sleep(2)
    return CheckResult(False, "Milvus did not become reachable within 120s")


def docker_compose_down() -> CheckResult:
    proc = _run(
        ["docker", "compose", "-f", str(COMPOSE_PATH), "down"],
        cwd=REPO_ROOT,
        timeout=180,
    )
    if proc.returncode != 0:
        return CheckResult(False, f"docker compose down failed: {proc.stderr.strip()[:300]}")
    return CheckResult(True, "OK: Milvus stack stopped")


def ollama_pull() -> CheckResult:
    model = pin("OLLAMA_EMBEDDING_MODEL")
    proc = _run(["ollama", "pull", model], timeout=1800)
    if proc.returncode != 0:
        return CheckResult(False, f"ollama pull {model} failed: {proc.stderr.strip()[:500]}")
    return CheckResult(True, f"OK: pulled {model}")


# --------------------------------------------------------------------------
# Fixture: compute claude-context's per-path collection identity
# --------------------------------------------------------------------------


def collection_hash_for(fixture: Path) -> str:
    """claude-context names collections `code_chunks_<md5(abs_path)>`.

    This function reproduces that identity without shelling out, so the lab
    can key its per-fixture state on the same string the tool itself uses.
    """
    absolute = str(fixture.resolve())
    return hashlib.md5(absolute.encode("utf-8")).hexdigest()  # noqa: S324


def fixture_git_head(fixture: Path) -> str | None:
    try:
        out = _run(["git", "-C", str(fixture), "rev-parse", "HEAD"], timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:  # noqa: BLE001
        return None
    return None


# --------------------------------------------------------------------------
# Index / search via the MCP surface
# --------------------------------------------------------------------------


def _mcp_env() -> dict[str, str]:
    """Environment for spawning `npx @zilliz/claude-context-mcp`.

    Deliberate: no OPENAI_*, no ZILLIZ_*, no VOYAGEAI_*, no GEMINI_*. If
    the caller's shell has them set, check_forbidden_env_vars() has already
    refused. Adds the local-only Milvus + Ollama pointers.
    """
    return {
        "EMBEDDING_PROVIDER": pin("EMBEDDING_PROVIDER"),
        "EMBEDDING_MODEL": pin("EMBEDDING_MODEL"),
        "EMBEDDING_BASE_URL": pin("EMBEDDING_BASE_URL"),
        "MILVUS_ADDRESS": f"{pin('MILVUS_HOST')}:{pin('MILVUS_GRPC_PORT')}",
        "MILVUS_TOKEN": pin("MILVUS_TOKEN"),
    }


def _mcp_cmd() -> list[str]:
    """Command line that spawns the pinned MCP server from .cache/node_modules."""
    return [
        "node",
        str(NODE_MODULES_PREFIX / "node_modules" / "@zilliz" / "claude-context-mcp" / "dist" / "index.js"),
    ]


def mcp_index_fixture(fixture: Path, *, timeout: float = 3600) -> tuple[CheckResult, dict[str, Any]]:
    """Index a fixture via the MCP `index_codebase` tool.

    Returns (result, timing) where timing has wall-clock seconds and
    the resolved collection identity.
    """
    if not fixture.exists():
        return CheckResult(False, f"fixture path missing: {fixture}"), {}
    fixture = fixture.resolve()
    coll = collection_hash_for(fixture)
    head = fixture_git_head(fixture) or "unknown"
    # We drive the MCP surface via JSON-RPC over stdio: initialize -> tools/call.
    # This keeps setup.py identical in *shape* to how a Claude Code session
    # would invoke the tool, so wall-clock here is comparable to the harness.
    initialize_req = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "cc-lab-setup", "version": "0.1"}},
    }
    call_req = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "index_codebase", "arguments": {"path": str(fixture), "force": True}},
    }
    payload = json.dumps(initialize_req) + "\n" + json.dumps(call_req) + "\n"
    started = time.monotonic()
    proc = subprocess.run(
        _mcp_cmd(),
        input=payload,
        env={**os.environ, **_mcp_env()},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    wall = time.monotonic() - started
    timing = {
        "fixture": str(fixture),
        "fixture_git_head": head,
        "collection_hash": coll,
        "wall_seconds": round(wall, 3),
        "mcp_exit_code": proc.returncode,
    }
    if proc.returncode != 0:
        return CheckResult(
            False,
            f"MCP index_codebase failed after {wall:.1f}s: {proc.stderr.strip()[:500]}",
        ), timing
    return CheckResult(True, f"OK: indexed {fixture} in {wall:.1f}s (collection {coll[:12]}...)"), timing


# --------------------------------------------------------------------------
# Summary emission
# --------------------------------------------------------------------------


def emit_summary(op: str, status: str, details: dict[str, Any]) -> None:
    payload = {
        "summary": True,
        "op": op,
        "status": status,
        "wall_seconds": details.pop("wall_seconds", None),
        "details": details,
    }
    # Bare JSON on its own line; the harness picks it up with `grep -E '^{'`.
    print(json.dumps(payload, sort_keys=True), flush=True)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_check(_args: argparse.Namespace) -> int:
    results = run_all_checks()
    print("Environment check:")
    all_ok = True
    for name, res in results:
        marker = "  ok" if res.ok else "FAIL"
        print(f"  [{marker}] {name}: {res.detail}")
        all_ok = all_ok and res.ok
    emit_summary(
        "check",
        "ok" if all_ok else "fail",
        {"results": [{"name": n, "ok": r.ok, "detail": r.detail} for n, r in results]},
    )
    return 0 if all_ok else 1


def cmd_install(_args: argparse.Namespace) -> int:
    env_gate = check_forbidden_env_vars()
    if not env_gate.ok:
        emit_summary("install", "fail", {"stage": "env_gate", "detail": env_gate.detail})
        print(env_gate.detail, file=sys.stderr)
        return 1
    steps: list[tuple[str, CheckResult]] = []
    for name, fn in [("npm_install", npm_install), ("docker_compose_up", docker_compose_up), ("ollama_pull", ollama_pull)]:
        started = time.monotonic()
        res = fn()
        wall = time.monotonic() - started
        steps.append((name, res))
        marker = "  ok" if res.ok else "FAIL"
        print(f"  [{marker}] {name} ({wall:.1f}s): {res.detail}")
        if not res.ok:
            emit_summary("install", "fail", {"stage": name, "detail": res.detail})
            return 2
    emit_summary("install", "ok", {"steps": [n for n, _ in steps]})
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    env_gate = check_forbidden_env_vars()
    if not env_gate.ok:
        emit_summary("index", "fail", {"stage": "env_gate", "detail": env_gate.detail})
        print(env_gate.detail, file=sys.stderr)
        return 1
    fixture = Path(args.fixture or os.environ.get("CLAUDE_CONTEXT_FIXTURE", "")).expanduser()
    if str(fixture) == "" or not fixture.exists():
        emit_summary("index", "fail", {"stage": "fixture_check", "detail": f"missing --fixture or bad path: {fixture}"})
        print(f"missing --fixture or bad path: {fixture}", file=sys.stderr)
        return 3
    res, timing = mcp_index_fixture(fixture)
    marker = "  ok" if res.ok else "FAIL"
    print(f"  [{marker}] index_codebase: {res.detail}")
    emit_summary(
        "index",
        "ok" if res.ok else "fail",
        {**timing, "detail": res.detail},
    )
    return 0 if res.ok else 3


def cmd_clean(_args: argparse.Namespace) -> int:
    """Tear down Milvus and remove local index / cache state.

    Explicitly does not delete Ollama models (they live in ~/.ollama and
    are expensive to re-pull), or fixture directories (they live outside
    the repo).
    """
    steps: list[str] = []
    res = docker_compose_down()
    steps.append(f"docker_compose_down={'ok' if res.ok else 'fail'}")
    for target in [NODE_MODULES_PREFIX, REPO_ROOT / "volumes"]:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            steps.append(f"removed={target.name}")
    emit_summary("clean", "ok", {"steps": steps})
    print("Clean:")
    for s in steps:
        print(f"  {s}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """Report the state of the local stack without side effects.

    Answers: is Milvus up? is Ollama running? is the MCP surface installed?
    """
    milvus_up = False
    try:
        with socket.create_connection((pin("MILVUS_HOST"), int(pin("MILVUS_GRPC_PORT"))), timeout=2):
            milvus_up = True
    except OSError:
        pass
    ollama_host, _, ollama_port = pin("OLLAMA_HOST").partition(":")
    ollama_up = False
    try:
        with socket.create_connection((ollama_host, int(ollama_port or "11434")), timeout=2):
            ollama_up = True
    except OSError:
        pass
    mcp_installed = (NODE_MODULES_PREFIX / "node_modules" / "@zilliz" / "claude-context-mcp" / "package.json").exists()
    state = {
        "milvus_up": milvus_up,
        "ollama_up": ollama_up,
        "mcp_installed": mcp_installed,
        "cache_prefix": str(NODE_MODULES_PREFIX),
    }
    print("Status:")
    for k, v in state.items():
        print(f"  {k}: {v}")
    emit_summary("status", "ok", state)
    return 0


# --------------------------------------------------------------------------
# argparse
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="setup.py", description="claude-context lab installer")
    sp = p.add_subparsers(dest="cmd", required=True)

    sp_check = sp.add_parser("--check", help="Verify environment prerequisites and forbidden env vars", prefix_chars="-")
    sp_check.set_defaults(fn=cmd_check)

    sp_install = sp.add_parser("--install", help="npm install + docker compose up + ollama pull (idempotent)", prefix_chars="-")
    sp_install.set_defaults(fn=cmd_install)

    sp_index = sp.add_parser("--index", help="Index a fixture through the MCP server (wall-clock reported)", prefix_chars="-")
    sp_index.add_argument("--fixture", help="Absolute path to the fixture repo", default=None)
    sp_index.set_defaults(fn=cmd_index)

    sp_status = sp.add_parser("--status", help="Report Milvus/Ollama/MCP-install state without side effects", prefix_chars="-")
    sp_status.set_defaults(fn=cmd_status)

    sp_clean = sp.add_parser("--clean", help="Stop Milvus, remove .cache/ and ./volumes/ (keeps Ollama models)", prefix_chars="-")
    sp_clean.set_defaults(fn=cmd_clean)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # We use double-dash subcommand names to keep the shape identical to the
    # setup.py contract in sibling PoCs (which use --check, --index, --clean).
    # argparse's subparsers do not accept leading dashes on the *name*, so we
    # rewrite argv[0] to strip the leading `--` before subparsers dispatch.
    if argv is None:
        argv = sys.argv[1:]
    remapped: list[str] = []
    for i, tok in enumerate(argv):
        if i == 0 and tok.startswith("--") and tok not in {"--help", "-h"}:
            remapped.append(tok[2:])  # subparser name
        else:
            remapped.append(tok)
    # Now argparse expects the first positional to be the subparser name, but
    # we added subparser names WITH the leading `--`. Rebuild the parser
    # without prefix_chars trickery: just alias subparser names to their
    # bare form on the fly.
    parser = argparse.ArgumentParser(prog="setup.py", description="claude-context lab installer")
    sp = parser.add_subparsers(dest="cmd", required=True)
    for name, fn, add_args in [
        ("check", cmd_check, None),
        ("install", cmd_install, None),
        ("index", cmd_index, lambda p: p.add_argument("--fixture", default=None)),
        ("status", cmd_status, None),
        ("clean", cmd_clean, None),
    ]:
        sub = sp.add_parser(name)
        if add_args is not None:
            add_args(sub)
        sub.set_defaults(fn=fn)

    try:
        args = parser.parse_args(remapped)
    except SystemExit as exc:
        return int(exc.code or 4)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
