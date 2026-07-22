# Lceda Pro AI Bridge

This workspace follows the architecture described in the referenced CSDN
article: AI produces a circuit DSL, a local Node gateway validates and serves
that DSL, and a Lceda Pro extension imports it through the EDA-side JavaScript
API.

The first goal is environment readiness, not automatic full schematic drawing.
The bridge currently provides:

- A local HTTP gateway.
- Circuit DSL validation.
- A built-in TUN_NAT_HUB V3s EVT DSL example.
- A Lceda Pro extension skeleton.
- A browser panel skeleton for manual import.

## Quick Start

```powershell
cd C:\work\tun_-nat_-hub\hardware\eda-bridge
npm.cmd start
```

Then open:

```text
http://127.0.0.1:17321/health
http://127.0.0.1:17321/api/projects/tun-nat-hub-v3s-evt
```

## Directory Layout

```text
hardware/eda-bridge/
  README.md
  package.json
  src/
    gateway.js
    circuit_dsl.js
    lceda_adapter.js
  dsl/
    tun_nat_hub_v3s_evt.json
  extension/
    manifest.json
    main.js
  panel/
    index.html
```

## Bridge Flow

```text
AI / DSL file
   |
   v
Node gateway
   |
   v
Lceda Pro extension / panel
   |
   v
EDA API creates schematic objects
```

## Current Limit

Lceda Pro project files are proprietary application files. This bridge avoids
guessing that format. The intended integration path is through the Lceda Pro
extension runtime, where the extension can access the official in-app `eda`
JavaScript object.

The adapter currently emits an import plan. Once the exact Lceda Pro extension
API methods are confirmed in the local client, implement those calls in
`extension/main.js` and `src/lceda_adapter.js`.
