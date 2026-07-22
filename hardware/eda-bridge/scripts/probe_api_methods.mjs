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
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
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

const names = process.argv.slice(2);
if (names.length === 0) {
  names.push("dmt_Project", "dmt_Schematic", "sch_Document", "sch_PrimitiveComponent", "sch_PrimitiveWire");
}

const expression = `((names) => {
  const root = window._EXTAPI_ROOT_;
  function describeObject(name) {
    const value = root && root[name];
    const rows = [];
    let proto = value;
    const seen = new Set();
    while (proto && proto !== Object.prototype) {
      for (const key of Object.getOwnPropertyNames(proto)) {
        if (seen.has(key)) continue;
        seen.add(key);
        let entry = { key, type: typeof value?.[key] };
        try {
          if (typeof value?.[key] === "function") {
            entry.source = Function.prototype.toString.call(value[key]).slice(0, 500);
          }
        } catch (error) {
          entry.source = "<error: " + error.message + ">";
        }
        rows.push(entry);
      }
      proto = Object.getPrototypeOf(proto);
    }
    return { name, type: typeof value, rows };
  }
  return JSON.stringify(names.map(describeObject), null, 2);
})(${JSON.stringify(names)})`;

const result = await send("Runtime.evaluate", {
  expression,
  awaitPromise: true,
  returnByValue: true
});

if (result.exceptionDetails) {
  console.error(JSON.stringify(result.exceptionDetails, null, 2));
  process.exitCode = 1;
} else {
  console.log(JSON.stringify(result, null, 2));
}
ws.close();
