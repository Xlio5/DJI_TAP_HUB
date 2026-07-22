import fs from "node:fs";
import path from "node:path";

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

const expression = `(async () => {
  const api = window._EXTAPI_ROOT_;
  const projectUuid = await api.dmt_Project.createProject(
    "TUN_NAT_HUB V3S EVT",
    "TUN_NAT_HUB_V3S_EVT",
    "",
    "",
    "V3S USB gateway + Ethernet EVT hardware project",
    1
  );
  await api.dmt_Project.openProject(projectUuid);
  await api.dmt_Schematic.createSchematic({
    projectUuid,
    title: "TUN_NAT_HUB_V3S_EVT",
    name: "TUN_NAT_HUB_V3S_EVT"
  });
  const schematics = await api.dmt_Schematic.getAllSchematicsInfo();
  const schematic = schematics.find((item) => item.parentProjectUuid === projectUuid) || schematics[0];
  await api.dmt_Schematic.modifySchematicName(schematic.uuid, "TUN_NAT_HUB_V3S_EVT");

  const firstPageUuid = schematic.page[0].uuid;
  await api.dmt_Schematic.modifySchematicPageName(firstPageUuid, "01_V3S_MINIMUM_SYSTEM");

  const pageNames = [
    "02_POWER",
    "03_USB_OTG_GATEWAY",
    "04_BOOT_STORAGE",
    "05_ETHERNET_EPHY_RJ45",
    "06_UART_DEBUG_IO",
    "07_RGB_STATUS_RECOVERY"
  ];

  const pages = [{ page_no: 1, uuid: firstPageUuid, name: "01_V3S_MINIMUM_SYSTEM" }];
  for (let index = 0; index < pageNames.length; index++) {
    const uuid = await api.dmt_Schematic.createSchematicPage(schematic.uuid);
    await api.dmt_Schematic.modifySchematicPageName(uuid, pageNames[index]);
    pages.push({ page_no: index + 2, uuid, name: pageNames[index] });
  }

  await api.dmt_Schematic.reorderSchematicPages(schematic.uuid, pages.map((p) => ({
    uuid: p.uuid,
    name: p.name
  })));
  await api.sch_Document.save();
  const info = await api.dmt_Project.getCurrentProjectInfo();
  return { projectUuid, schematicUuid: schematic.uuid, pages, currentProject: info };
})()`;

const result = await send("Runtime.evaluate", {
  expression,
  awaitPromise: true,
  returnByValue: true
});

if (result.exceptionDetails) {
  console.error(JSON.stringify(result.exceptionDetails, null, 2));
  process.exitCode = 1;
} else {
  const value = result.result.value;
  console.log(JSON.stringify(value, null, 2));
  const manifestPath = path.resolve("..", "lceda", "TUN_NAT_HUB_V3S_EVT", "project_manifest.generated.json");
  fs.writeFileSync(manifestPath, JSON.stringify(value, null, 2));
}

ws.close();
