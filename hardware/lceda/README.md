# Lceda Pro Workspace

Place the Lceda Pro project here:

```text
hardware/lceda/TUN_NAT_HUB_V3S_EVT/
```

Recommended Lceda project name:

```text
TUN_NAT_HUB_V3S_EVT
```

Use local/offline project storage during EVT so that the generated schematic,
PCB, BOM, Gerber, and production files can be versioned with the repository.

Suggested output subdirectories inside the Lceda project:

```text
docs/
fabrication/
exports/
  schematic_pdf/
  pcb_pdf/
  bom/
  gerber/
  pick_place/
```

Do not commit large temporary caches if Lceda Pro creates them. Commit source
schematic/PCB files, exported PDFs, BOM, Gerber, and assembly files when they
represent an intentional hardware revision.
