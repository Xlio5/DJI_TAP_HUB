"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { validateCircuitDsl } = require("./circuit_dsl");
const { buildImportPlan } = require("./lceda_adapter");
const { sendJson, collectJson } = require("./http_utils");

const SERVER_PORT = Number(process.env.LCEDA_SERVER_PORT || 8787);
const ROOT = path.resolve(__dirname, "..");
const DEFAULT_DSL = path.join(ROOT, "dsl", "tun_nat_hub_v3s_evt.json");
const BRIDGE_START = 49620;
const BRIDGE_END = 49629;

function readDefaultDsl() {
  return JSON.parse(fs.readFileSync(DEFAULT_DSL, "utf8"));
}

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    const request = http.get(url, { timeout: 1000 }, (response) => {
      let body = "";
      response.on("data", (chunk) => { body += chunk; });
      response.on("end", () => {
        try {
          resolve({ statusCode: response.statusCode, body: JSON.parse(body) });
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on("timeout", () => {
      request.destroy(new Error("timeout"));
    });
    request.on("error", reject);
  });
}

async function discoverBridge() {
  for (let port = BRIDGE_START; port <= BRIDGE_END; port++) {
    const baseUrl = `http://127.0.0.1:${port}`;
    try {
      const result = await httpGetJson(`${baseUrl}/health`);
      if (result.statusCode === 200 && result.body && result.body.bridge) {
        return { ok: true, baseUrl, ...result.body };
      }
    } catch (_error) {
      // Continue scanning.
    }
  }
  return {
    ok: false,
    error: `No EasyEDA bridge found in ${BRIDGE_START}-${BRIDGE_END}.`
  };
}

async function handle(request, response) {
  const url = new URL(request.url, `http://${request.headers.host || "127.0.0.1"}`);

  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/health") {
    sendJson(response, 200, {
      ok: true,
      service: "tun-nat-hub-lceda-server",
      port: SERVER_PORT
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/gateway/health") {
    sendJson(response, 200, await discoverBridge());
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/projects/tun-nat-hub-v3s-evt") {
    sendJson(response, 200, readDefaultDsl());
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/projects/tun-nat-hub-v3s-evt/import-plan") {
    const dsl = readDefaultDsl();
    const errors = validateCircuitDsl(dsl);
    if (errors.length > 0) {
      sendJson(response, 422, { ok: false, errors });
      return;
    }
    sendJson(response, 200, { ok: true, plan: buildImportPlan(dsl) });
    return;
  }

  if (request.method === "POST" && url.pathname === "/api/validate") {
    const dsl = await collectJson(request);
    const errors = validateCircuitDsl(dsl);
    sendJson(response, errors.length === 0 ? 200 : 422, {
      ok: errors.length === 0,
      errors
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/") {
    fs.createReadStream(path.join(ROOT, "panel", "index.html")).pipe(response);
    return;
  }

  sendJson(response, 404, { ok: false, error: "Not found." });
}

function check() {
  const dsl = readDefaultDsl();
  const errors = validateCircuitDsl(dsl);
  if (errors.length > 0) {
    errors.forEach((error) => console.error(error));
    process.exit(1);
  }
  console.log("Circuit DSL check passed.");
}

if (process.argv.includes("--check")) {
  check();
} else {
  http.createServer((request, response) => {
    handle(request, response).catch((error) => sendJson(response, 500, {
      ok: false,
      error: error.message
    }));
  }).listen(SERVER_PORT, "127.0.0.1", () => {
    console.log(`Lceda server listening on http://127.0.0.1:${SERVER_PORT}`);
  });
}
