# Lceda Pro API Probe Notes

## Current Result

The Lceda Pro desktop client can be accessed through Chrome DevTools Protocol
when launched with:

```powershell
C:\Program Files\lceda-pro\lceda-pro.exe --remote-debugging-port=9222 --edaDebug
```

The editor page is exposed at:

```text
http://127.0.0.1:9222/json/list
```

The expected editor target URL is:

```text
https://pro.lceda.cn/editor?cll=warn
```

## Discovered Globals

`window.eda` is not present in this Lceda Pro version.

The actual extension API root is:

```text
window._EXTAPI_ROOT_
```

Important API groups discovered:

- `sch_Document`
- `sch_Primitive`
- `sch_PrimitiveComponent`
- `sch_PrimitivePin`
- `sch_PrimitiveWire`
- `sch_Netlist`
- `sch_Drc`
- `pcb_Document`
- `pcb_Primitive`
- `pcb_PrimitiveComponent`
- `pcb_PrimitivePad`
- `pcb_PrimitiveVia`
- `pcb_Net`
- `pcb_Drc`
- `dmt_Project`
- `dmt_Schematic`
- `dmt_Pcb`
- `sys_MessageBus`
- `sys_FileSystem`
- `sys_Dialog`
- `sys_Window`

Other useful globals:

- `window._MSG_BUS2_EXTAPI_`
- `window.electronAPI`
- `window.panelCallByEditor`
- `window.PRO_EDITOR_MODE`
- `window.PRO_EDITOR_VERSION`

## Local Bridge Ports

Following the referenced architecture:

- Bridge: `49620-49629`
- Server: `8787`
- Panel: `http://127.0.0.1:8787/`

## Commands

Start local services:

```powershell
cd C:\work\tun_-nat_-hub\hardware\eda-bridge
.\start_bridge.cmd
```

Probe CDP:

```powershell
npm.cmd run probe-cdp
npm.cmd run probe-extapi
```

Inject bridge into Lceda editor page:

```powershell
npm.cmd run inject-lceda
```

After injection, the editor page has:

```javascript
window.TunNatHubLcedaBridge
```

This object can fetch the local DSL import plan and inspect `_EXTAPI_ROOT_`.

## Next Implementation Step

Map the Circuit DSL operations to the discovered `sch_*` APIs:

1. Create or select schematic document.
2. Place block-level component placeholders.
3. Replace placeholders with library devices after library API review.
4. Add wires/net labels.
5. Run ERC.
6. Export schematic PDF/BOM.
