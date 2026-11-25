// Adds our own rules (autoconsent-rules/*.json, upstream's rule format) to a built autoconsent add-on's
// compact-rules.json. The compact set is re-encoded with the package's own encodeRules: it orders the rules and the
// string table into generic, frame and site ranges, and the content script trusts those ranges.
// usage: node autoconsent_rules.cjs <extracted npm package dir> <add-on dir>
const fs = require("fs");
const path = require("path");

const [pkg, addon] = process.argv.slice(2);
const { decodeRules, encodeRules } = require(path.resolve(pkg, "dist/autoconsent.cjs.js"));
const file = path.join(addon, "compact-rules.json");
const shipped = JSON.parse(fs.readFileSync(file, "utf8"));
const rules = decodeRules(shipped);
const dir = path.join(__dirname, "autoconsent-rules");
for (const name of fs.readdirSync(dir).filter((f) => f.endsWith(".json")).sort()) {
    const rule = JSON.parse(fs.readFileSync(path.join(dir, name), "utf8"));
    if (rules.some((r) => r.name === rule.name)) throw new Error(`rule ${rule.name} is already in the package`);
    rules.push(rule);
}
fs.writeFileSync(file, JSON.stringify(encodeRules(rules, shipped)));
