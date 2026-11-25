import { test } from "node:test";
import assert from "node:assert/strict";

import { escapeHtml, renderMarkdown, splitSections, plainText } from "../lib/markdown.js";
import { buildSourceIndex, findCitations, citationDecorator, evidenceReferences, statementUnits } from "../lib/sources.js";
import { answerView, referencesView } from "../lib/views.js";
import { fixture, heroWorkspace, textOf } from "./helpers.mjs";

const index = buildSourceIndex(heroWorkspace());

// ---------------------------------------------------------------------------------------------
// Safe rendering
// ---------------------------------------------------------------------------------------------

test("agent text cannot inject markup, scripts, links or images", () => {
  const hostile = [
    "## Recommendation",
    "<script>alert(1)</script> <img src=x onerror=alert(2)> <a href=\"javascript:alert(3)\">x</a>",
    "[click me](javascript:alert(4)) ![pic](https://example.com/x.png)",
    "| a | b |",
    "|---|---|",
    "| <iframe src=//evil> | \" onmouseover=\"alert(5) |",
    "```",
    "<style>body{display:none}</style>",
    "```",
  ].join("\n");
  for (const html of [renderMarkdown(hostile), answerView(hostile, index)]) {
    assert.doesNotMatch(html, /<(script|img|a|iframe|style)\b/i);
    // Every real tag carries only the renderer's own fixed attributes.
    for (const [, attrs] of html.matchAll(/<\/?[a-z][a-z0-9]*((?:\s[^>]*)?)>/gi)) {
      for (const [, name] of attrs.matchAll(/\s([\w-]+)=/g)) {
        assert.ok(["class", "start", "type", "data-docs", "data-page", "data-guidance", "title"].includes(name), name);
      }
    }
    assert.match(html, /&lt;script&gt;/);
  }
  assert.equal(escapeHtml(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
});

test("markdown structures render without changing the words", () => {
  const md = "Intro **bold** and *em*.\n\n1. one\n2. two\n   - nested\n\n| Source | Finding |\n|---|---|\n| A | B |\n\n> quoted";
  const html = renderMarkdown(md);
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<em>em<\/em>/);
  assert.match(html, /<ol><li>one<\/li><li>two<ul><li>nested<\/li><\/ul><\/li><\/ol>/);
  assert.match(html, /<div class="md-table"><table><thead><tr><th>Source<\/th><th>Finding<\/th><\/tr><\/thead><tbody><tr><td>A<\/td><td>B<\/td><\/tr>/);
  assert.match(html, /<blockquote>/);
});

test("a list directly after a paragraph is a list, not part of the paragraph", () => {
  const html = renderMarkdown("Next steps:\n- first\n- second");
  assert.match(html, /<p>Next steps:<\/p>\s*<ul><li>first<\/li><li>second<\/li><\/ul>/);
});

// ---------------------------------------------------------------------------------------------
// Structured answer: sections become cards; all of the agent's words are preserved
// ---------------------------------------------------------------------------------------------

test("the recorded hero review renders as one card per agent section", () => {
  const md = fixture("hero-review.md");
  const sections = splitSections(md).map((s) => s.heading);
  assert.deepEqual(sections, ["Recommendation", "Coverage", "What checks out", "Needs review", "Why", "Next step", "Sources"]);
  const html = answerView(md, index);
  assert.equal((html.match(/<section class="answer-card/g) ?? []).length, 7);
  for (const cls of ["recommendation", "coverage", "what-checks-out", "needs-review", "why", "next-step", "sources"]) {
    assert.match(html, new RegExp(`answer-card section-${cls}"`));
  }
  // Every word of the agent's answer is still present in the rendered text.
  const rendered = textOf(html).replace(/\s+/g, "");
  for (const word of plainText(md).split(/\s+/).filter((w) => /\w/.test(w))) {
    assert.ok(rendered.includes(word.replace(/[*_`#]/g, "")), `missing word: ${word}`);
  }
});

test("an answer without headings is shown as the agent wrote it, not as invented sections", () => {
  const md = "I could not retrieve the claim record, so I cannot review the claim yet.";
  const html = answerView(md, index);
  assert.match(html, /answer-plain/);
  assert.doesNotMatch(html, /answer-card|section-/);
  assert.equal(textOf(html), md);
});

test("a malformed or unexpected answer is displayed safely as text", () => {
  const md = '{"recommendation": "approve", "<b>": 1}';
  const html = answerView(md, index);
  assert.match(html, /answer-plain/);
  assert.equal(textOf(html), md);
  assert.doesNotMatch(html, /<b>/);
});

// ---------------------------------------------------------------------------------------------
// Citation mapping
// ---------------------------------------------------------------------------------------------

test("known document IDs, ranges and pages map to the claim's evidence", () => {
  const cases = [
    ["DOC-10482-01", ["DOC-10482-01"], null],
    ["DOC-10482-08, page 1, line 1", ["DOC-10482-08"], 1],
    ["DOC-10482-07, pages 1–2", ["DOC-10482-07"], 1],
    ["DOC-10482-07, pp. 1–2", ["DOC-10482-07"], 1],
    ["DOC-10482-01, p. 1", ["DOC-10482-01"], 1],
    ["DOC-10482-02–06", ["DOC-10482-02", "DOC-10482-03", "DOC-10482-04", "DOC-10482-05", "DOC-10482-06"], null],
    ["DOC-10482-02 through DOC-10482-04", ["DOC-10482-02", "DOC-10482-03", "DOC-10482-04"], null],
    ["DOC-10482-02-05", ["DOC-10482-02", "DOC-10482-03", "DOC-10482-04", "DOC-10482-05"], null],
  ];
  for (const [text, ids, page] of cases) {
    const [found] = findCitations(`See ${text}.`, index);
    assert.ok(found, text);
    assert.deepEqual(found.documentIds, ids, text);
    assert.equal(found.page, page, text);
  }
});

test("citations that are not in the claim's evidence stay plain text", () => {
  const decorate = citationDecorator(index);
  for (const text of ["DOC-10471-03", "DOC-10482-09", "DOC-10482-99", "DOC-10482-06–01"]) {
    assert.deepEqual(findCitations(text, index), [], text);
    assert.equal(decorate(text), text);
  }
  assert.equal(decorate("PAP-4471920 and CLM-10482"), "PAP-4471920 and CLM-10482");
});

test("source buttons carry the exact evidence and page they cite", () => {
  const html = citationDecorator(index)("Estimate DOC-10482-08, page 1, line 1 and photos DOC-10482-02–06.");
  assert.match(html, /<button type="button" class="cite" data-docs="DOC-10482-08" data-page="1" title="Open Repair estimate EST-HL-26-3391">DOC-10482-08, page 1<\/button>, line 1/);
  assert.match(html, /data-docs="DOC-10482-02 DOC-10482-03 DOC-10482-04 DOC-10482-05 DOC-10482-06"/);
});

test("guidance titles named by the agent link to that guidance document", () => {
  const html = citationDecorator(index)("Repair Estimate Review Guidelines §10 applies.");
  assert.match(html, /<button type="button" class="cite cite-guidance" data-guidance="repair-estimate-review">Repair Estimate Review Guidelines<\/button> §10/);
  assert.equal(citationDecorator(index)("Some Other Manual §2"), "Some Other Manual §2");
});

// ---------------------------------------------------------------------------------------------
// "Evidence referenced in this answer" (visual evidence comparison)
// ---------------------------------------------------------------------------------------------

test("the headlamp follow-up surfaces the estimate, reports, photographs and guidance the agent cited", () => {
  const md = fixture("headlamp-followup.md");
  const groups = evidenceReferences(md, index);
  assert.deepEqual(groups.map((g) => g.key), ["estimate", "reports", "photos", "guidance"]);
  const byKey = Object.fromEntries(groups.map((g) => [g.key, g]));
  assert.deepEqual(byKey.estimate.items.map((i) => i.documentId), ["DOC-10482-08"]);
  assert.deepEqual(byKey.reports.items.map((i) => i.documentId), ["DOC-10482-01", "DOC-10482-07"]);
  assert.equal(byKey.photos.items.length, 5);
  assert.deepEqual(byKey.guidance.items.map((g) => g.guidanceId).sort(), ["claims-handling-guidelines", "repair-estimate-review"]);
  // Every quoted statement is verbatim agent text from the answer.
  const units = statementUnits(md);
  for (const group of groups) {
    assert.ok(group.statements.length > 0, group.key);
    for (const statement of group.statements) assert.ok(units.includes(statement), statement);
  }
});

test("the references panel uses the agent's statements and opens the cited items", () => {
  const html = referencesView(fixture("headlamp-followup.md"), index);
  assert.match(html, /Evidence referenced in this answer/);
  assert.match(html, /data-open-doc="DOC-10482-08"/);
  for (let n = 2; n <= 6; n += 1) assert.match(html, new RegExp(`data-open-doc="DOC-10482-0${n}"`));
  assert.match(html, /data-open-guidance="repair-estimate-review"/);
  assert.doesNotMatch(html, /<(script|iframe|style)\b/i);
});

test("the Sources section counts as citations but is not quoted as a finding", () => {
  const md = "## Why\nThe estimate DOC-10482-08 lists the line.\n\n## Sources\n- DOC-10482-01, pages 1–2";
  const groups = evidenceReferences(md, index);
  const reports = groups.find((g) => g.key === "reports");
  assert.ok(reports);
  assert.deepEqual(reports.statements, []);
  assert.deepEqual(groups.find((g) => g.key === "estimate").statements, ["The estimate DOC-10482-08 lists the line."]);
});

test("an answer that cites nothing shows no references panel", () => {
  assert.equal(referencesView("No evidence is cited here.", index), "");
});
