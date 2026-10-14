const fs = require('fs');
const { JSDOM } = require('jsdom');

// Initialize DOM environment for testing browser-vendored libraries
const dom = new JSDOM('', { runScripts: 'outside-only' });

// Load and evaluate the exact vendored frontend assets
const markedCode = fs.readFileSync('./frontend/vendor/marked.min.js', 'utf8');
const purifyCode = fs.readFileSync('./frontend/vendor/purify.min.js', 'utf8');

dom.window.eval(markedCode);
dom.window.eval(purifyCode);

const marked = dom.window.marked;
const DOMPurify = dom.window.DOMPurify;

const summary = "Here is a bold **summary** with some bad code: <script>alert(1)</script> <img src=x onerror=alert(2)>";
const rawHtml = marked.parse(summary);
const cleanHtml = DOMPurify.sanitize(rawHtml);

console.log("RAW HTML:");
console.log(rawHtml);
console.log("\nCLEAN HTML:");
console.log(cleanHtml);

if (cleanHtml.includes('<script>') || cleanHtml.includes('onerror')) {
    console.error("TEST FAILED: HTML injection possible!");
    process.exit(1);
} else {
    console.log("TEST PASSED: Script tags and bad attributes were removed.");
}
