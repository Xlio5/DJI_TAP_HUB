const targets = await fetch("http://127.0.0.1:9222/json/list").then((r) => r.json());
const page = targets.find((target) => target.type === "page" && /editor/.test(target.url));

if (!page) {
  console.error("No Lceda editor page found on DevTools port 9222.");
  process.exit(1);
}

let nextId = 1;
const pending = new Map();
const ws = new WebSocket(page.webSocketDebuggerUrl);

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
  });
}

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(JSON.stringify(message.error)));
  else resolve(message.result);
});

await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve, { once: true });
  ws.addEventListener("error", reject, { once: true });
});

await send("Runtime.enable");

const expression = `async () => {
  const bridgeBaseUrl = "http://127.0.0.1:49620";
  const serverBaseUrl = "http://127.0.0.1:8787";
  const apiRoot = window._EXTAPI_ROOT_;
  const apiKeys = apiRoot ? Object.getOwnPropertyNames(apiRoot).sort() : [];

  window.TunNatHubLcedaBridge = {
    bridgeBaseUrl,
    serverBaseUrl,
    apiRoot,
    apiKeys,
    async getImportPlan() {
      return fetch(serverBaseUrl + "/api/projects/tun-nat-hub-v3s-evt/import-plan").then((r) => r.json());
    },
    describeApi(prefix = "") {
      return apiKeys.filter((key) => key.startsWith(prefix)).map((key) => {
        const value = apiRoot[key];
        return {
          key,
          type: typeof value,
          methods: value && (typeof value === "object" || typeof value === "function")
            ? Object.getOwnPropertyNames(value).slice(0, 80)
            : []
        };
      });
    }
  };

  const registerResponse = await fetch(bridgeBaseUrl + "/eda-windows/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: document.title,
      api: "_EXTAPI_ROOT_",
      url: location.href,
      apiKeyCount: apiKeys.length
    })
  }).then((r) => r.json());

  return {
    ok: true,
    title: document.title,
    href: location.href,
    hasExtApiRoot: !!apiRoot,
    apiKeyCount: apiKeys.length,
    apiKeys: apiKeys.slice(0, 120),
    registerResponse
  };
}`;

const result = await send("Runtime.evaluate", {
  expression: `(${expression})()`,
  awaitPromise: true,
  returnByValue: true
});

console.log(JSON.stringify(result.result.value, null, 2));
ws.close();
