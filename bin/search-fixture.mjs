#!/usr/bin/env node
// search-fixture.mjs — sibling of index-fixture.mjs. Calls
// `Context.semanticSearch(...)` directly for wave probes; the harness
// uses the full MCP surface through Claude Code.
//
// Usage: node bin/search-fixture.mjs --path /abs/path --query "..." [--limit N]

import { Context, MilvusVectorDatabase } from "@zilliz/claude-context-core";
import { createMcpConfig } from "@zilliz/claude-context-mcp/dist/config.js";
import { createEmbeddingInstance } from "@zilliz/claude-context-mcp/dist/embedding.js";

console.log = (...args) => process.stderr.write("[LOG] " + args.join(" ") + "\n");
console.warn = (...args) => process.stderr.write("[WARN] " + args.join(" ") + "\n");

function parseArgs(argv) {
  const out = { path: null, query: null, limit: 5 };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--path") out.path = argv[++i];
    else if (argv[i] === "--query") out.query = argv[++i];
    else if (argv[i] === "--limit") out.limit = parseInt(argv[++i], 10);
  }
  if (!out.path || !out.query) {
    process.stderr.write("--path and --query are required\n");
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
  const results = await context.semanticSearch(args.path, args.query, args.limit);
  const wall = (Date.now() - started) / 1000;

  process.stdout.write(
    JSON.stringify({
      ok: true,
      op: "search_code",
      path: args.path,
      query: args.query,
      wall_seconds: Number(wall.toFixed(3)),
      results: results.map((r) => ({
        file: r.relativePath || r.path,
        start_line: r.startLine,
        end_line: r.endLine,
        score: r.score,
        preview: (r.content || "").split("\n").slice(0, 3).join(" | ").slice(0, 200),
      })),
    }) + "\n",
  );
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({ ok: false, error: err.message, stack: err.stack }) + "\n",
  );
  process.exit(1);
});
