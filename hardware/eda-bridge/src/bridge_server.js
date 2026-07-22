"use strict";

const http = require("http");
const { randomUUID } = require("crypto");
const { sendJson, collectJson } = require("./http_utils");

const START_PORT = Number(process.env.EASYEDA_BRIDGE_START_PORT || 49620);
const END_PORT = Number(process.env.EASYEDA_BRIDGE_END_PORT || 49629);
const edaWindows = new Map();

function handle(request, response) {
  const url = new URL(request.url, `http://${request.headers.host || "127.0.0.1"}`);

  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  if (request.method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, {
      ok: true,
      service: "easyeda-bridge",
      bridge: true,
      edaWindowCount: edaWindows.size,
      edaWindows: Array.from(edaWindows.values())
    });
    return;
  }

  if (request.method === "GET" && url.pathname === "/eda-windows") {
    sendJson(response, 200, {
      ok: true,
      windows: Array.from(edaWindows.values())
    });
    return;
  }

  if (request.method === "POST" && url.pathname === "/eda-windows/register") {
    collectJson(request)
      .then((body) => {
        const id = body.id || randomUUID();
        const windowInfo = {
          id,
          title: body.title || "Lceda Pro Window",
          connectedAt: new Date().toISOString(),
          api: body.api || "unknown"
        };
        edaWindows.set(id, windowInfo);
        sendJson(response, 200, { ok: true, window: windowInfo });
      })
      .catch((error) => sendJson(response, 400, { ok: false, error: error.message }));
    return;
  }

  if (request.method === "POST" && url.pathname === "/execute") {
    collectJson(request)
      .then((body) => {
        sendJson(response, 202, {
          ok: false,
          accepted: true,
          mode: "dry-run",
          reason: "No live EDA WebSocket client is implemented yet.",
          scriptPreview: typeof body.script === "string" ? body.script.slice(0, 500) : ""
        });
      })
      .catch((error) => sendJson(response, 400, { ok: false, error: error.message }));
    return;
  }

  sendJson(response, 404, { ok: false, error: "Not found." });
}

function listenOnAvailablePort(port) {
  if (port > END_PORT) {
    console.error(`No available bridge port in ${START_PORT}-${END_PORT}.`);
    process.exit(1);
  }

  const server = http.createServer(handle);
  server.on("error", (error) => {
    if (error.code === "EADDRINUSE") {
      listenOnAvailablePort(port + 1);
      return;
    }
    throw error;
  });
  server.listen(port, "127.0.0.1", () => {
    console.log(`EasyEDA bridge listening on http://127.0.0.1:${port}`);
  });
}

listenOnAvailablePort(START_PORT);
