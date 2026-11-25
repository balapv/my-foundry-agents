import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export const TESTS_DIR = dirname(fileURLToPath(import.meta.url));
export const FRONTEND_DIR = dirname(TESTS_DIR);

export function fixture(name) {
  return readFileSync(join(TESTS_DIR, "fixtures", name), "utf8");
}

// The CLM-10482 workspace exactly as GET /api/claims/CLM-10482 returns it.
// tests/test_webapp.py keeps this fixture identical to the live backend payload.
export function heroWorkspace() {
  return JSON.parse(fixture("workspace-CLM-10482.json"));
}

export function frontendSource(relativePath) {
  return readFileSync(join(FRONTEND_DIR, relativePath), "utf8");
}

// Visible text of an HTML fragment (tags removed, common entities decoded).
export function textOf(html) {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&middot;/g, "·")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}
