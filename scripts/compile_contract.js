// Compile contracts/CredentialRegistry.sol -> contracts/CredentialRegistry.json
// Usage:  npm install solc@0.8.24 && node scripts/compile_contract.js
const fs = require("fs"), path = require("path"), solc = require("solc");
const src = fs.readFileSync(path.join(__dirname, "..", "contracts", "CredentialRegistry.sol"), "utf8");
const out = JSON.parse(solc.compile(JSON.stringify({
  language: "Solidity",
  sources: { "CredentialRegistry.sol": { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 },
              outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } }
})));
(out.errors || []).forEach(e => console.error(e.formattedMessage));
if ((out.errors || []).some(e => e.severity === "error")) process.exit(1);
const c = out.contracts["CredentialRegistry.sol"]["CredentialRegistry"];
fs.writeFileSync(path.join(__dirname, "..", "contracts", "CredentialRegistry.json"),
  JSON.stringify({ abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 2));
console.log("Compiled OK -> contracts/CredentialRegistry.json");
