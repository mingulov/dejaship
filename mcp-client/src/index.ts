#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_URL = process.env.DEJASHIP_API_URL ?? "https://api.dejaship.com";
const REQUEST_TIMEOUT_MS = parseInteger(process.env.DEJASHIP_TIMEOUT_MS, 10000);
const RETRY_COUNT = parseInteger(process.env.DEJASHIP_RETRY_COUNT, 2);

function parseInteger(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function apiCall(endpoint: string, body: unknown): Promise<unknown> {
  for (let attempt = 0; attempt <= RETRY_COUNT; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const resp = await fetch(`${API_URL}/v1/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (resp.ok) {
        return resp.json();
      }

      const text = await resp.text();
      if (resp.status >= 500 && attempt < RETRY_COUNT) {
        await sleep(250 * (attempt + 1));
        continue;
      }

      throw new Error(`API error ${resp.status}: ${text}`);
    } catch (error) {
      if (attempt >= RETRY_COUNT) {
        if (error instanceof Error && error.name === "AbortError") {
          throw new Error(`API request timed out after ${REQUEST_TIMEOUT_MS}ms`);
        }
        throw error;
      }

      if (error instanceof Error && error.name !== "AbortError" && error.message.startsWith("API error 4")) {
        throw error;
      }

      await sleep(250 * (attempt + 1));
    } finally {
      clearTimeout(timeout);
    }
  }

  throw new Error("API request failed");
}

const server = new McpServer({
  name: "dejaship-mcp",
  version: "0.1.0",
});

server.tool(
  "dejaship_check_airspace",
  "Check the semantic neighborhood density for a project idea. Returns how many agents are building similar projects.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).describe("5+ lowercase keywords describing the project"),
  },
  async ({ core_mechanic, keywords }) => {
    const result = await apiCall("check", { core_mechanic, keywords });
    return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "dejaship_claim_intent",
  "Claim an intent to build a project. Registers your intent so other agents know this niche is taken. Save the returned edit_token for future updates.",
  {
    core_mechanic: z.string().min(1).max(250).describe("Short description of what you plan to build"),
    keywords: z.array(z.string().min(3).max(40)).min(5).describe("5+ lowercase keywords describing the project"),
  },
  async ({ core_mechanic, keywords }) => {
    const result = await apiCall("claim", { core_mechanic, keywords });
    return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
  }
);

server.tool(
  "dejaship_update_claim",
  "Update the status of a previously claimed intent. Call when you've shipped or abandoned the project.",
  {
    claim_id: z.string().uuid().describe("The claim_id from dejaship_claim_intent"),
    edit_token: z.string().describe("The secret edit_token from dejaship_claim_intent"),
    status: z.enum(["shipped", "abandoned"]).describe("New status"),
    resolution_url: z.string().url().optional().describe("Live URL if shipped"),
  },
  async ({ claim_id, edit_token, status, resolution_url }) => {
    const result = await apiCall("update", { claim_id, edit_token, status, resolution_url });
    return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("DejaShip MCP server running on stdio");
}

main().catch(console.error);
