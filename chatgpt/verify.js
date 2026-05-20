#!/usr/bin/env node

import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const nodeMajor = Number(process.versions.node.split(".")[0] || 0);

const requiredFiles = [
  "server.js",
  "package.json",
  ".env.example",
  "README.md",
  "test-harness.html",
  "widget/app.html",
];

const optionalPaths = [".env", "static"];

console.log("\nFashion Trends MCP Apps Bridge Verification\n");

let allGood = true;

console.log(`Node.js version: ${process.versions.node}`);
if (nodeMajor >= 18) {
  console.log("PASS  Node.js satisfies the bridge requirement (18+).");
} else {
  console.log("FAIL  Node.js 18 or newer is required.");
  allGood = false;
}

console.log("\nChecking required files:\n");
for (const file of requiredFiles) {
  const path = resolve(__dirname, file);
  if (existsSync(path)) {
    const size = statSync(path).size;
    console.log(`PASS  ${file.padEnd(24)} ${(size / 1024).toFixed(1)} KB`);
  } else {
    console.log(`FAIL  ${file.padEnd(24)} missing`);
    allGood = false;
  }
}

console.log("\nChecking optional local paths:\n");
for (const file of optionalPaths) {
  const path = resolve(__dirname, file);
  if (existsSync(path)) {
    console.log(`INFO  ${file.padEnd(24)} present`);
  } else {
    console.log(`INFO  ${file.padEnd(24)} not present`);
  }
}

console.log("\nExpected runtime flow:\n");
console.log("1. Start the Python FastMCP server with MCP_TRANSPORT=http.");
console.log("2. Start this bridge with npm start.");
console.log("3. Open http://localhost:8787/preview to validate the widget locally.");
console.log("4. Point your MCP client at chatgpt/server.js or http://localhost:8787/mcp.");

if (allGood) {
  console.log("\nVerification passed.\n");
  process.exit(0);
}

console.log("\nVerification failed. Fix the missing requirement(s) above.\n");
process.exit(1);
