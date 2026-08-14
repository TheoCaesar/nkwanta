/* Check that every Mermaid diagram in a markdown file will actually render.
 *
 *     npm install mermaid jsdom
 *     node scripts/validate-diagrams.mjs docs/09-system-design.md
 *
 * Worth having because the failure is silent: a broken diagram renders as a grey box
 * with an error in it, and nothing in the Python test suite can see that. One was caught
 * this way — a semicolon inside a `sequenceDiagram` note, which the parser reads as a
 * statement separator.
 *
 * Not part of pytest because it needs a JavaScript parser. Run it after editing a
 * diagram; `tests/test_design_docs.py` covers everything else about the document.
 */
import fs from "fs";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { pretendToBeVisual: true });
global.window = dom.window; global.document = dom.window.document;
Object.defineProperty(global, "navigator", { value: dom.window.navigator, configurable: true });
global.DOMPurify = { sanitize: (x) => x };

const mermaid = (await import("mermaid")).default;
mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });

const md = fs.readFileSync(process.argv[2], "utf8");
const blocks = [...md.matchAll(/```mermaid\n([\s\S]*?)```/g)].map(m => m[1]);
console.log(`found ${blocks.length} diagrams\n`);

let bad = 0;
for (const [i, code] of blocks.entries()) {
  const kind = code.trim().split("\n")[0].slice(0, 28);
  try {
    await mermaid.parse(code);
    console.log(`  ok    #${i + 1}  ${kind}`);
  } catch (e) {
    bad++;
    console.log(`  FAIL  #${i + 1}  ${kind}\n        ${String(e.message).split("\n")[0]}`);
  }
}
console.log(bad ? `\n${bad} diagram(s) will not render` : "\nall diagrams parse");
