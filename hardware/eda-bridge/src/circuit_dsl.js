"use strict";

function validateCircuitDsl(value) {
  const errors = [];

  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return ["DSL root must be an object."];
  }

  requireString(value, "project", errors);
  requireString(value, "revision", errors);

  if (!Array.isArray(value.blocks)) {
    errors.push("blocks must be an array.");
  } else {
    const blockNames = new Set();
    value.blocks.forEach((block, index) => {
      const prefix = `blocks[${index}]`;
      requireString(block, "name", errors, prefix);
      requireString(block, "purpose", errors, prefix);
      if (block && block.name) {
        if (blockNames.has(block.name)) errors.push(`${prefix}.name is duplicated.`);
        blockNames.add(block.name);
      }
      if (!Array.isArray(block.components)) {
        errors.push(`${prefix}.components must be an array.`);
      } else {
        block.components.forEach((component, cIndex) => {
          const cPrefix = `${prefix}.components[${cIndex}]`;
          requireString(component, "ref", errors, cPrefix);
          requireString(component, "value", errors, cPrefix);
          requireString(component, "footprint", errors, cPrefix);
        });
      }
    });
  }

  if (!Array.isArray(value.nets)) {
    errors.push("nets must be an array.");
  } else {
    const netNames = new Set();
    value.nets.forEach((net, index) => {
      const prefix = `nets[${index}]`;
      requireString(net, "name", errors, prefix);
      if (net && net.name) {
        if (netNames.has(net.name)) errors.push(`${prefix}.name is duplicated.`);
        netNames.add(net.name);
      }
      if (!Array.isArray(net.pins)) {
        errors.push(`${prefix}.pins must be an array.`);
      } else if (net.pins.length < 1) {
        errors.push(`${prefix}.pins must not be empty.`);
      }
    });
  }

  return errors;
}

function requireString(object, key, errors, prefix = "") {
  const label = prefix ? `${prefix}.${key}` : key;
  if (!object || typeof object[key] !== "string" || object[key].trim() === "") {
    errors.push(`${label} must be a non-empty string.`);
  }
}

module.exports = { validateCircuitDsl };
