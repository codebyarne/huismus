// SPDX-FileCopyrightText: 2026 Huismus contributors
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Huismus in the Claude app (huismus/assistants/claude.py). The Claude app
// starts this with its own Node and talks MCP over stdin and stdout, one JSON
// message per line; each message goes on, as it is, to Huismus's /mcp on this
// computer, with the key. No dependencies: Node's own fetch is enough.
//
// Huismus need not be open when the Claude app starts. Then this answers
// initialize itself, offers no tools yet, and tells the Claude app the tools
// changed as soon as Huismus answers (notifications/tools/list_changed).

"use strict";

const fs = require("node:fs");
const readline = require("node:readline");

const KEY = process.env.HUISMUS_KEY || "";
// Written by the desktop app at every start: the port can differ.
const ADDRESS_FILE = process.env.HUISMUS_ADDRESS_FILE || "";
const FALLBACK_ADDRESS = process.env.HUISMUS_ADDRESS || "";
const NOT_OPEN = process.env.HUISMUS_NOT_OPEN || "Huismus is not open.";
const NOT_CONNECTED = process.env.HUISMUS_NOT_CONNECTED || "Huismus no longer knows this key.";
const RETRY_MS = Number(process.env.HUISMUS_RETRY_MS || 5000);

const INTERNAL_ERROR = -32603;

class NotOpen extends Error {}
class NotConnected extends Error {}

let waiting = null; // the timer while Huismus is not open

function address() {
  try {
    const written = fs.readFileSync(ADDRESS_FILE, "utf8").trim();
    if (written) return written;
  } catch {
    // Not there: the app never started on this computer, or is gone.
  }
  return FALLBACK_ADDRESS;
}

async function post(message) {
  let response;
  try {
    response = await fetch(address(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        Authorization: `Bearer ${KEY}`,
      },
      body: JSON.stringify(message),
    });
  } catch {
    throw new NotOpen();
  }
  // Another app on Huismus's old port answers with anything but this.
  if (response.status === 401) throw new NotConnected();
  if (response.status === 202) return null;
  if (!(response.headers.get("content-type") || "").startsWith("application/json")) {
    throw new NotOpen();
  }
  return response.json();
}

function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}

function waitForHuismus() {
  if (waiting) return;
  waiting = setInterval(async () => {
    try {
      await post({ jsonrpc: "2.0", id: "huismus-wacht", method: "ping" });
    } catch {
      return;
    }
    clearInterval(waiting);
    waiting = null;
    send({ jsonrpc: "2.0", method: "notifications/tools/list_changed" });
  }, RETRY_MS);
}

function textOf(error) {
  return error instanceof NotConnected ? NOT_CONNECTED : NOT_OPEN;
}

// What the Claude app gets when Huismus does not answer.
function answerWithout(message, error) {
  waitForHuismus();
  const id = message.id;
  if (message.method === "initialize") {
    const asked = (message.params || {}).protocolVersion;
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: asked || "2025-06-18",
        capabilities: { tools: { listChanged: true } },
        serverInfo: { name: "huismus", title: "Huismus", version: "0" },
        instructions: textOf(error),
      },
    };
  }
  if (message.method === "tools/list") return { jsonrpc: "2.0", id, result: { tools: [] } };
  if (message.method === "tools/call") {
    return {
      jsonrpc: "2.0",
      id,
      result: { content: [{ type: "text", text: textOf(error) }], isError: true },
    };
  }
  return { jsonrpc: "2.0", id, error: { code: INTERNAL_ERROR, message: textOf(error) } };
}

async function handle(message) {
  const isRequest = message && typeof message === "object" && "method" in message && "id" in message;
  let answer;
  try {
    answer = await post(message);
  } catch (error) {
    if (isRequest) send(answerWithout(message, error));
    return;
  }
  if (answer === null) return;
  // Huismus's own tools never change, but this program's do: none while
  // Huismus is closed, all of them once it is open.
  if (message.method === "initialize" && answer.result) {
    answer.result.capabilities = { ...answer.result.capabilities, tools: { listChanged: true } };
  }
  send(answer);
}

// One at a time, in order: Huismus answers each before the next goes.
let queue = Promise.resolve();
readline.createInterface({ input: process.stdin }).on("line", (line) => {
  if (!line.trim()) return;
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    send({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Not JSON." } });
    return;
  }
  queue = queue.then(() => handle(message));
}).on("close", () => {
  queue.then(() => process.exit(0));
});
