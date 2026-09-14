#!/usr/bin/env node
// index-fixture.mjs — thin Node helper called by `setup.py --index`.
//
// Rationale: the raw JSON-RPC over stdio path against `@zilliz/claude-context-mcp`
// stalled during Wave 1 because that server requires a proper MCP handshake
// (initialize → initialize response → initialized notification → tools/call)
// and driving it with a single-shot stdin pipe from Python interleaves the
// two request frames before the server has finished initializing.
//
// The MCP server itself internally calls the same `Context.indexCodebase(...)`
// method this helper calls, using the same embedding + Milvus config, so the
// wall-clock and index shape produced here match what a real MCP session
// would produce. The harness (`run-prompts.py`) still drives the MCP surface
// end-to-end through Claude Code, because that IS the customer-facing path.
//
// Emits a single JSON line to stdout: `{"ok": true, ...}` on success.
//
// Usage:
//   node bin/index-fixture.mjs --path /abs/path/to/fixture [--force]

import { Context, MilvusVectorDatabase } from "@zilliz/claude-context-core";
import { createMcpConfig } from "@zilliz/claude-context-mcp/dist/config.js";
import { createEmbeddingInstance } from "@zilliz/claude-context-mcp/dist/embedding.js";

// Silence the noisy console output the MCP config module emits at import.
console.log = (...args) => process.stderr.write("[LOG] " + args.join(" ") + "\n");
console.warn = (...args) => process.stderr.write("[WARN] " + args.join(" ") + "\n");

function parseArgs(argv) {
  const out = { path: null, force: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--path") out.path = argv[++i];
    else if (argv[i] === "--force") out.force = true;
  }
  if (!out.path) {
    process.stderr.write("--path is required\n");
    process.exit(2);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  const config = createMcpConfig();
  const embedding = createEmbeddingInstance(config);
  const vectorDatabase = new MilvusVectorDatabase({
    address: config.milvusAddress,
    ...(config.milvusToken && { token: config.milvusToken }),
  });
  const context = new Context({ embedding, vectorDatabase });

  const started = Date.now();
  let lastProgressPhase = null;
  const result = await context.indexCodebase(
    args.path,
    (progress) => {
      // Progress bumps are numerous; print only phase transitions on stderr.
      if (progress.phase !== lastProgressPhase) {
        lastProgressPhase = progress.phase;
        process.stderr.write(
          `[progress] ${progress.phase} ${progress.current}/${progress.total} (${progress.percentage.toFixed(1)}%)\n`,
        );
      }
    },
    args.force,
  );
  const wall = (Date.now() - started) / 1000;

  const summary = {
    ok: true,
    op: "index_codebase",
    path: args.path,
    force: args.force,
    wall_seconds: Number(wall.toFixed(3)),
    indexed_files: result.indexedFiles,
    total_chunks: result.totalChunks,
    status: result.status,
    collection_name: context.getCollectionName(args.path),
  };
  process.stdout.write(JSON.stringify(summary) + "\n");
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({
      ok: false,
      op: "index_codebase",
      error: err && err.message ? err.message : String(err),
      stack: err && err.stack ? err.stack : null,
    }) + "\n",
  );
  process.exit(1);
});
