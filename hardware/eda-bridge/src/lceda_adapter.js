"use strict";

const fs = require("fs");
const path = require("path");
const { validateCircuitDsl } = require("./circuit_dsl");

function buildImportPlan(dsl) {
  return {
    project: dsl.project,
    revision: dsl.revision,
    summary: {
      blocks: dsl.blocks.length,
      components: dsl.blocks.reduce((count, block) => count + block.components.length, 0),
      nets: dsl.nets.length
    },
    steps: [
      "Create or open the Lceda Pro project TUN_NAT_HUB_V3S_EVT.",
      "Create schematic sheets for each DSL block.",
      "Place components block by block.",
      "Apply reference design values from Lichee Pi Zero and Dock.",
      "Create named nets and attach component pins.",
      "Run ERC, then export schematic PDF and BOM."
    ],
    blocks: dsl.blocks.map((block) => ({
      name: block.name,
      purpose: block.purpose,
      components: block.components.map((component) => component.ref)
    })),
    nets: dsl.nets.map((net) => ({
      name: net.name,
      pinCount: net.pins.length
    }))
  };
}

function loadDsl(filePath) {
  const absolute = path.resolve(filePath);
  const dsl = JSON.parse(fs.readFileSync(absolute, "utf8"));
  const errors = validateCircuitDsl(dsl);
  if (errors.length > 0) {
    const error = new Error("Circuit DSL validation failed.");
    error.details = errors;
    throw error;
  }
  return dsl;
}

if (require.main === module) {
  const filePath = process.argv[2];
  if (!filePath) {
    console.error("Usage: node src/lceda_adapter.js <dsl-json>");
    process.exit(2);
  }
  try {
    const dsl = loadDsl(filePath);
    console.log(JSON.stringify(buildImportPlan(dsl), null, 2));
  } catch (error) {
    console.error(error.message);
    if (error.details) error.details.forEach((detail) => console.error(`- ${detail}`));
    process.exit(1);
  }
}

module.exports = { buildImportPlan, loadDsl };
