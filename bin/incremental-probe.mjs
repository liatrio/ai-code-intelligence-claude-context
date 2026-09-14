#!/usr/bin/env node
// incremental-probe.mjs — Wave 4's incremental_reindex probe.
//
// Loops: append a distinctive marker comment to one gratibot file,
// call Context.reindexByChange (the Merkle-diff sync path), then
// verify the new marker is queryable via semanticSearch. Records
// wall clock per rep and reports median + full range across N reps.
//
// The labCheck for `incremental_reindex` (research/capabilities.json)
// asks for:
//   - median + full range across ≥7 reps
//   - p90 ≤ 30 s
//   - delta ≤ 1/10 of a full index
// Baseline full-index wall clock for gratibot (Wave 1) = 6.65 s, so
// the delta target = 0.665 s.
//
// Keeps ONE Context instance alive across all reps because the
// realistic customer workflow is a long-lived MCP server watching a
// checkout, not a fresh Node process per file change.

import { Context, MilvusVectorDatabase } from "@zilliz/claude-context-core";
import { createMcpConfig } from "@zilliz/claude-context-mcp/dist/config.js";
import { createEmbeddingInstance } from "@zilliz/claude-context-mcp/dist/embedding.js";
import { readFileSync, writeFileSync } from "fs";
import { resolve } from "path";

console.log = (...args) => process.stderr.write("[LOG] " + args.join(" ") + "\n");
console.warn = (...args) => process.stderr.write("[WARN] " + args.join(" ") + "\n");

function parseArgs(argv) {
  const out = { path: null, reps: 7, target: "regex.js" };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--path") out.path = argv[++i];
    else if (argv[i] === "--reps") out.reps = parseInt(argv[++i], 10);
    else if (argv[i] === "--target") out.target = argv[++i];
  }
  if (!out.path) {
    process.stderr.write("--path is required\n");
    process.exit(2);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const targetPath = resolve(args.path, args.target);
  const originalSource = readFileSync(targetPath, "utf8");

  const config = createMcpConfig();
  const embedding = createEmbeddingInstance(config);
  const vectorDatabase = new MilvusVectorDatabase({
    address: config.milvusAddress,
    ...(config.milvusToken && { token: config.milvusToken }),
  });
  const context = new Context({ embedding, vectorDatabase });

  const reps = [];
  try {
    for (let i = 1; i <= args.reps; i++) {
      // Marker is unique per rep so a stale hit from a previous rep
      // can't accidentally pass.
      const marker = `WAVE4_MARKER_${i}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      const marker_query = `WAVE4_MARKER_${i}`;

      // Restore, then append a fresh distinctive comment.
      writeFileSync(targetPath, originalSource + `\n// ${marker} — gratibot marker for incremental probe rep ${i}\n`);

      // Measure reindexByChange wall clock.
      const t0 = Date.now();
      const stats = await context.reindexByChange(args.path);
      const reindexMs = Date.now() - t0;

      // Verify the marker is queryable. Semantic-search wall clock is
      // separate from the reindex wall clock; the labCheck cares about
      // "queryable in seconds", so this is the customer-facing latency.
      const t1 = Date.now();
      const results = await context.semanticSearch(args.path, marker_query, 5);
      const queryMs = Date.now() - t1;

      const found = results.some((r) => (r.content || "").includes(marker));
      reps.push({
        rep: i,
        marker,
        reindex_ms: reindexMs,
        query_ms: queryMs,
        end_to_end_ms: reindexMs + queryMs,
        marker_found: found,
        added: stats.added || 0,
        removed: stats.removed || 0,
      });

      process.stderr.write(
        `[rep ${i}] reindex=${reindexMs}ms query=${queryMs}ms found=${found} +${stats.added || 0}/-${stats.removed || 0}\n`,
      );
    }
  } finally {
    // Always restore the original file so the fixture stays clean.
    writeFileSync(targetPath, originalSource);
    // One last reindex to bring Milvus back into sync with the file
    // on disk. Skip failure — main-loop stats are the point.
    try {
      await context.reindexByChange(args.path);
    } catch (e) {
      process.stderr.write("[teardown] final reindex failed: " + e.message + "\n");
    }
  }

  // Summarize.
  const reindex_all = reps.map((r) => r.reindex_ms).sort((a, b) => a - b);
  const query_all = reps.map((r) => r.query_ms).sort((a, b) => a - b);
  const e2e_all = reps.map((r) => r.end_to_end_ms).sort((a, b) => a - b);
  const median = (arr) => arr[Math.floor(arr.length / 2)];
  const p90 = (arr) => arr[Math.floor(arr.length * 0.9)];

  process.stdout.write(
    JSON.stringify(
      {
        ok: true,
        op: "incremental_probe",
        path: args.path,
        target_file: targetPath,
        reps,
        summary: {
          reindex_ms: {
            min: reindex_all[0],
            median: median(reindex_all),
            p90: p90(reindex_all),
            max: reindex_all[reindex_all.length - 1],
          },
          query_ms: {
            min: query_all[0],
            median: median(query_all),
            p90: p90(query_all),
            max: query_all[query_all.length - 1],
          },
          end_to_end_ms: {
            min: e2e_all[0],
            median: median(e2e_all),
            p90: p90(e2e_all),
            max: e2e_all[e2e_all.length - 1],
          },
          marker_hit_rate: reps.filter((r) => r.marker_found).length / reps.length,
        },
      },
      null,
      2,
    ) + "\n",
  );
}

main().catch((err) => {
  process.stdout.write(
    JSON.stringify({ ok: false, error: err.message, stack: err.stack }) + "\n",
  );
  process.exit(1);
});
