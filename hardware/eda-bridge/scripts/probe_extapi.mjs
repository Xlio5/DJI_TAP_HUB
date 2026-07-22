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
const expression = `(() => {
  function describe(name) {
    const value = window[name];
    const type = typeof value;
    let keys = [];
    let stringValue = "";
    try {
      keys = value && (type === "object" || type === "function")
        ? Object.getOwnPropertyNames(value).slice(0, 100)
        : [];
    } catch (error) {
      keys = ["<keys error: " + error.message + ">"];
    }
    try {
      stringValue = type === "string" ? value : String(value).slice(0, 300);
    } catch (error) {
      stringValue = "<string error: " + error.message + ">";
    }
    return { name, type, stringValue, keys };
  }

  return [
    "_EXTAPI_ROOT_",
    "_EXTAPI_SCRIPT_SPACES_",
    "_MSG_BUS2_EXTAPI_",
    "electronAPI",
    "panelCallByEditor",
    "PRO_EDITOR_MODE",
    "PRO_EDITOR_VERSION"
  ].map(describe);
})()`;

const result = await send("Runtime.evaluate", {
  expression,
  awaitPromise: true,
  returnByValue: true
});

console.log(JSON.stringify(result.result.value, null, 2));
ws.close();
