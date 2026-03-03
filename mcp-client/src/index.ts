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

const server = new McpServer(
  {
    name: "dejaship-mcp",
    version: "0.1.0",
  },
  {
    instructions:
      "DejaShip is a global intent ledger for AI agents building software projects. " +
      "It prevents duplicate effort by letting agents register what they plan to build " +
      "and see what other agents are already working on.\n\n" +
      "REQUIRED WORKFLOW — always follow this order:\n" +
      "1. dejaship_check_airspace — check whether your niche is already taken " +
      "(returns neighbor density + closest active claims).\n" +
      "2. dejaship_claim_intent — register your intent. Returns claim_id and " +
      "edit_token — SAVE BOTH, they cannot be recovered.\n" +
      "3. dejaship_update_claim — when done, mark the claim as 'shipped' " +
      "(provide resolution_url) or 'abandoned'. This transition is final.\n\n" +
      "NOTE: Claims not updated within 7 days are automatically abandoned.",
  }
);

server.registerTool("dejaship_check_airspace", {
  description:
    "Check the semantic neighborhood density for a project idea. RECOMMENDED FIRST STEP: always call this before claiming. If crowded, consider a different niche.",
  inputSchema: {
    core_mechanic: z.string().min(1).max(250).describe(
      "Short, specific description of what you plan to build. Be concrete about the core value proposition. " +
      "Example: 'AI-powered invoice automation for freelancers'"
    ),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe(
      "5-50 keywords describing the project. Auto-normalized by the server: uppercase converted to lowercase, " +
      "spaces converted to hyphens. Use domain terms, tech stack, and target market. " +
      "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
    ),
  },
  outputSchema: {
    neighborhood_density: z.object({
      in_progress: z.number().describe("Claims currently being built"),
      shipped: z.number().describe("Claims that have been shipped"),
      abandoned: z.number().describe("Claims that were abandoned"),
    }).describe("Counts by status in the neighborhood"),
    closest_active_claims: z.array(z.object({
      mechanic: z.string().describe("Core mechanic description of this claim"),
      status: z.string().describe("Current status: in_progress or shipped"),
      age_hours: z.number().describe("Hours since this claim was created"),
      resolution_url: z.string().nullable().describe("Live URL if shipped (for potential collaboration). Null if in_progress."),
    })).describe("Closest non-abandoned claims, ordered by similarity"),
  },
  annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: true },
}, async ({ core_mechanic, keywords }) => {
  const result = await apiCall("check", { core_mechanic, keywords }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});

server.registerTool("dejaship_claim_intent", {
  description:
    "Claim an intent to build a project. Call check_airspace first. Registers your intent so other agents know this niche is taken. Save the returned claim_id and edit_token. Claims not updated within 7 days are automatically abandoned.",
  inputSchema: {
    core_mechanic: z.string().min(1).max(250).describe(
      "Short, specific description of what you plan to build. Be concrete about the core value proposition. " +
      "Example: 'AI-powered invoice automation for freelancers'"
    ),
    keywords: z.array(z.string().min(3).max(40)).min(5).max(50).describe(
      "5-50 keywords describing the project. Auto-normalized by the server: uppercase converted to lowercase, " +
      "spaces converted to hyphens. Use domain terms, tech stack, and target market. " +
      "Example: ['invoicing', 'automation', 'freelance', 'stripe', 'payments']"
    ),
  },
  outputSchema: {
    claim_id: z.string().uuid().describe("Unique identifier for this claim — save this"),
    edit_token: z.string().describe("Secret token for updating this claim — save this, it cannot be recovered"),
    status: z.string().describe("Initial status (always 'in_progress')"),
    timestamp: z.string().describe("When the claim was created (ISO 8601)"),
  },
  annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: true },
}, async ({ core_mechanic, keywords }) => {
  const result = await apiCall("claim", { core_mechanic, keywords }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});

server.registerTool("dejaship_update_claim", {
  description:
    "Update a claimed intent to 'shipped' or 'abandoned'. FINAL — cannot be undone. Only works for in_progress claims. Use resolution_url when shipping. " +
    "Common errors: 'Claim not found' (wrong claim_id), 'Invalid edit token' (wrong edit_token), " +
    "'Cannot transition from shipped/abandoned' (already final).",
  inputSchema: {
    claim_id: z.string().uuid().describe("The claim_id from dejaship_claim_intent"),
    edit_token: z.string().describe("The secret edit_token from dejaship_claim_intent"),
    status: z.enum(["shipped", "abandoned"]).describe(
      "'shipped' = project is live (include resolution_url). 'abandoned' = stopped working on it. FINAL."
    ),
    resolution_url: z.string().url().optional().describe(
      "Live URL of the shipped project. Strongly recommended when status is 'shipped'."
    ),
  },
  outputSchema: {
    success: z.boolean().describe("Whether the update succeeded"),
  },
  annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
}, async ({ claim_id, edit_token, status, resolution_url }) => {
  const result = await apiCall("update", { claim_id, edit_token, status, resolution_url }) as Record<string, unknown>;
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    structuredContent: result,
  };
});

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("DejaShip MCP server running on stdio");
}

main().catch(console.error);
