import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const processes = [
  ["bridge", "node", ["src/bridge_server.js"]],
  ["server", "node", ["src/server.js"]]
];

for (const [name, command, args] of processes) {
  const child = spawn(command, args, {
    cwd: root,
    stdio: ["ignore", "pipe", "pipe"],
    shell: false
  });

  child.stdout.on("data", (data) => process.stdout.write(`[${name}] ${data}`));
  child.stderr.on("data", (data) => process.stderr.write(`[${name}] ${data}`));
  child.on("exit", (code) => {
    console.log(`[${name}] exited with code ${code}`);
  });
}

process.on("SIGINT", () => {
  for (const child of process._getActiveHandles()) {
    if (child && typeof child.kill === "function") child.kill();
  }
  process.exit(0);
});
