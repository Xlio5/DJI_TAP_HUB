"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { validateCircuitDsl } = require("./circuit_dsl");
const { buildImportPlan } = require("./lceda_adapter");

const PORT = Number(process.env.LCEDA_BRIDGE_PORT || 17321);
const ROOT = path.resolve(__dirname, "..");
const DEFAULT_DSL = path.join(ROOT, "dsl", "tun_nat_hub_v3s_evt.json");

function readDefaultDsl() {
  return JSON.parse(fs.readFileSync(DEFAULT_DSL, "utf8"));
}

function sendJson(response, statusCode, body) {
  response.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "http://127.0.0.1:17321",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  });
  response.end(JSON.stringify(body, null, 2));
}

function collectJson(request) {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
      if (body.length > 2 * 1024 * 1024) {
        reject(new Error("Request body too large."));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (error) {
        reject(new Error("Invalid JSON body."));
      }
    });
    request.on("error", reject);
  });
}

async function handle(request, response) {
  const url = new URL(request.url, `http://${request.headers.host || "127.0.0.1"}`);

  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, {
      ok: true,
      service: "tun-nat-hub-lceda-bridge",
      port: PORT,
      lcedaProject: "TUN_NAT_HUB_V3S_EVT"
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/api/projects/tun-nat-hub-v3s-evt") {
    const dsl = readDefaultDsl();
    sendJson(response, 200, dsl);
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
    try {
      const dsl = await collectJson(request);
      const errors = validateCircuitDsl(dsl);
      sendJson(response, errors.length === 0 ? 200 : 422, {
        ok: errors.length === 0,
        errors
      });
    } catch (error) {
      sendJson(response, 400, { ok: false, errors: [error.message] });
    }
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
  }).listen(PORT, "127.0.0.1", () => {
    console.log(`Lceda bridge listening on http://127.0.0.1:${PORT}`);
  });
}
