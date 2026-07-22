const targets = await fetch("http://127.0.0.1:9222/json/list").then((r) => r.json());
const page = targets.find((target) => target.type === "page" && /editor/.test(target.url));

if (!page) {
  console.error("No Lceda editor page found on DevTools port 9222.");
  process.exit(1);
}

const expressionArg = process.argv.slice(2).join(" ");
if (!expressionArg) {
  console.error("Usage: node scripts/eval_lceda.mjs <javascript-expression>");
  process.exit(2);
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
const result = await send("Runtime.evaluate", {
  expression: `(async () => (${expressionArg}))()`,
  awaitPromise: true,
  returnByValue: true
});

if (result.exceptionDetails) {
  console.error(JSON.stringify(result.exceptionDetails, null, 2));
  process.exitCode = 1;
} else {
  console.log(JSON.stringify(result.result.value, null, 2));
}

ws.close();
