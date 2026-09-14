#!/usr/bin/env node
// mcp-tools-probe.mjs — spawn the pinned claude-context MCP server over
// stdio and enumerate its advertised tools via a proper SDK handshake.
// This is the shape a real Claude Code session goes through, so what
// this probe sees is what an agent would see. Used by Wave 2 to score
// `agents_md_instructions`.

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const MCP_ENTRY = resolve(
  __dirname,
  "..",
  "node_modules",
  "@zilliz",
  "claude-context-mcp",
  "dist",
  "index.js",
);

async function main() {
  const transport = new StdioClientTransport({
    command: "node",
    args: [MCP_ENTRY],
    // Pass through only the env vars the local-only path needs. The parent
    // Python process has already refused to run if forbidden vars are set,
    // so nothing hosted can leak through here.
    env: {
      ...process.env,
      EMBEDDING_PROVIDER: process.env.EMBEDDING_PROVIDER || "Ollama",
      EMBEDDING_MODEL: process.env.EMBEDDING_MODEL || "nomic-embed-text",
      EMBEDDING_BASE_URL: process.env.EMBEDDING_BASE_URL || "http://127.0.0.1:11434",
      MILVUS_ADDRESS: process.env.MILVUS_ADDRESS || "127.0.0.1:19530",
    },
  });

  const client = new Client(
    { name: "cc-lab-mcp-probe", version: "0.1" },
    { capabilities: {} },
  );

  try {
    await client.connect(transport);
    const tools = await client.listTools();
    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          server_info: client.getServerVersion(),
          tool_count: tools.tools.length,
          tools: tools.tools.map((t) => ({
            name: t.name,
            description: (t.description || "").split("\n")[0].trim().slice(0, 200),
            required: t.inputSchema?.required || [],
            properties: Object.keys(t.inputSchema?.properties || {}),
          })),
        },
        null,
        2,
      ) + "\n",
    );
    await client.close();
  } catch (err) {
    process.stdout.write(
      JSON.stringify({ ok: false, error: err.message, stack: err.stack }) + "\n",
    );
    process.exit(1);
  }
}

main();
