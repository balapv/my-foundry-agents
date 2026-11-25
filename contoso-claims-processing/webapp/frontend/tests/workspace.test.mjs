import { test } from "node:test";
import assert from "node:assert/strict";

import {
  HERO_PROMPT, claimHeader, summaryPanel, policyPanel, evidencePanel, errorView, progressView,
  conversationView, stageLabel, formatMoney, formatDate, formatTime,
} from "../lib/views.js";
import { buildSourceIndex } from "../lib/sources.js";
import { fixture, frontendSource, heroWorkspace, textOf } from "./helpers.mjs";

const workspace = heroWorkspace();
const index = buildSourceIndex(workspace);

// ---------------------------------------------------------------------------------------------
// Claim summary and policy
// ---------------------------------------------------------------------------------------------

test("the claim summary shows the CLM-10482 facts from the claims records", () => {
  const text = textOf(claimHeader(workspace) + summaryPanel(workspace));
  for (const value of [
    "Claim CLM-10482", "Jordan Lee", "2024 Contoso Trailstar Touring AWD", "Harbor Blue Metallic",
    "Nov 12, 2026 at 2:25 PM", "Collision", "Two-vehicle collision", "In Review",
    "Harborline Auto Body & Paint", "$7,850", "EST-HL-26-3391", "$1,000", "PAP-4471920",
  ]) {
    assert.ok(text.includes(value), value);
  }
});

test("missing claim facts are shown as not available, never filled in", () => {
  const partial = { claimId: "CLM-10482", recordsAvailable: false, summary: { claimId: "CLM-10482" }, policy: null, evidence: [] };
  const text = textOf(summaryPanel(partial) + policyPanel(partial));
  assert.match(text, /Some claim records could not be loaded/);
  assert.equal((text.match(/Not available/g) ?? []).length, 11);
  assert.match(text, /Policy records are not available/);
  assert.doesNotMatch(text, /Jordan Lee|\$7,850|\$1,000/);
});

test("the policy panel lists the policy term and coverages on record", () => {
  const text = textOf(policyPanel(workspace));
  for (const value of ["Policy PAP-4471920", "Active", "Apr 1, 2026 – Apr 1, 2027", "Woodgrove Bank", "Collision", "$1,000 deductible"]) {
    assert.ok(text.includes(value), value);
  }
});

test("formatters present values without shifting dates", () => {
  assert.equal(formatMoney(7850), "$7,850");
  assert.equal(formatMoney(1240.5), "$1,240.50");
  assert.equal(formatMoney(null), null);
  assert.equal(formatDate("2026-11-12"), "Nov 12, 2026");
  assert.equal(formatDate("not a date"), null);
  assert.equal(formatTime("14:25"), "2:25 PM");
  assert.equal(formatTime("00:05"), "12:05 AM");
});

// ---------------------------------------------------------------------------------------------
// Evidence panel
// ---------------------------------------------------------------------------------------------

test("the evidence panel lists the claim form, police report, repair estimate and five photographs", () => {
  const html = evidencePanel(workspace);
  const text = textOf(html);
  assert.match(text, /Evidence 8 items/);
  for (const [id, type] of [["DOC-10482-01", "Claim form"], ["DOC-10482-07", "Police report"], ["DOC-10482-08", "Repair estimate"]]) {
    assert.match(html, new RegExp(`class="evidence-item doc" data-open-doc="${id}"`));
    assert.ok(text.includes(type), type);
  }
  const photos = [...html.matchAll(/class="evidence-item photo" data-open-doc="(DOC-10482-0\d)"/g)].map((m) => m[1]);
  assert.deepEqual(photos, ["DOC-10482-02", "DOC-10482-03", "DOC-10482-04", "DOC-10482-05", "DOC-10482-06"]);
  assert.equal((html.match(/<img src="\/api\/claims\/CLM-10482\/evidence\/DOC-10482-0[2-6]"/g) ?? []).length, 5);
  for (const photo of workspace.evidence.filter((e) => e.kind === "photo")) {
    assert.ok(text.includes(photo.title), photo.title);
  }
  assert.match(text, /2 pages/);
});

test("company guidance documents are listed for inspection", () => {
  const html = evidencePanel(workspace);
  for (const slug of ["claims-handling-guidelines", "auto-coverage-guidance", "repair-estimate-review", "claims-escalation-guidance"]) {
    assert.match(html, new RegExp(`data-open-guidance="${slug}"`));
  }
});

test("an empty evidence package is stated plainly", () => {
  assert.match(textOf(evidencePanel({ ...workspace, evidence: [] })), /No evidence package is on file/);
});

// ---------------------------------------------------------------------------------------------
// Agent panel
// ---------------------------------------------------------------------------------------------

test("the hero prompt is the suggested first question", () => {
  assert.equal(HERO_PROMPT, "Review this claim and tell me what I should do next.");
  const page = frontendSource("index.html");
  for (const id of ["hero-prompt", "composer", "message", "send-button", "reset-button", "conversation", "summary", "evidence", "viewer"]) {
    assert.match(page, new RegExp(`id="${id}"`), id);
  }
});

test("progress uses a small set of honest stage labels", () => {
  assert.equal(stageLabel("sending", true), "Sending the claim and its evidence to the review agent…");
  assert.equal(stageLabel("sending", false), "Sending your question to the review agent…");
  assert.equal(stageLabel("records", true), "Checking claims records…");
  assert.equal(stageLabel("guidance", false), "Searching company guidance…");
  assert.equal(stageLabel("something-new", true), "The agent is reviewing the claim…");
  const slow = textOf(progressView({ stage: "reviewing", elapsedSeconds: 75 }, true));
  assert.match(slow, /75s/);
  assert.match(slow, /taking longer than usual/);
  assert.doesNotMatch(textOf(progressView({ stage: "reviewing", elapsedSeconds: 12 }, true)), /longer than usual/);
});

test("errors are friendly, carry a reference and offer the right recovery", () => {
  const retry = errorView({ code: "agent_error", message: "The review agent could not complete this request.", reference: "CR-7K2Q9M", retry: "retry" });
  assert.match(textOf(retry), /The review agent could not complete this request\. Reference CR-7K2Q9M Try again/);
  assert.match(retry, /role="alert"/);
  assert.match(retry, /data-action="retry"/);
  const fresh = errorView({ code: "timeout", message: "The review took too long.", retry: "new_review" });
  assert.match(fresh, /data-action="reset">Start a new review/);
  assert.match(textOf(errorView(undefined)), /Something went wrong while reviewing this claim/);
  assert.doesNotMatch(errorView({ message: "<img src=x onerror=1>" }), /<img/);
});

test("a completed conversation shows prompts, the agent's answer and the evidence that was sent", () => {
  const turns = [
    { turnId: "t1", prompt: HERO_PROMPT, status: "completed", elapsedSeconds: 55.6, answer: fixture("hero-review.md"), evidenceAttached: { documents: 3, photos: 5 } },
    { turnId: "t2", prompt: "Show me why you flagged the headlamp.", status: "completed", elapsedSeconds: 10.4, answer: fixture("headlamp-followup.md"), evidenceAttached: { documents: 0, photos: 0 } },
    { turnId: "t3", prompt: "Can you deny the claim based on this?", status: "running", stage: "writing", elapsedSeconds: 3 },
  ];
  const html = conversationView(turns, index, "t1");
  assert.equal((html.match(/class="msg msg-user"/g) ?? []).length, 3);
  assert.equal((html.match(/class="attached"/g) ?? []).length, 1);
  assert.match(textOf(html), /Claim evidence sent with this request: 3 documents and 5 photographs/);
  assert.equal((html.match(/Evidence referenced in this answer/g) ?? []).length, 2);
  assert.match(textOf(html), /Preparing the response… 3s/);
});

test("user prompts are escaped", () => {
  const html = conversationView([{ turnId: "t1", prompt: "<script>x</script>", status: "running", stage: "queued" }], index, "t1");
  assert.doesNotMatch(html, /<script>/);
});

// ---------------------------------------------------------------------------------------------
// Nothing internal reaches the page
// ---------------------------------------------------------------------------------------------

test("the workspace payload and rendered page carry no internal identifiers or hidden metadata", () => {
  const raw = JSON.stringify(workspace);
  for (const pattern of [/sha256|sha-?256|"hash"/i, /[A-Za-z]:\\\\|\/Users\/|\/home\//, /https?:\/\//, /prompt|rubric|expected|answer_key/i,
    /photos\.json|evidence-source|\.json"/i, /conversation|response_id|resp_|conv_/i, /get_claim|get_policy|get_vehicle|claims_operations|file_search/i,
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i]) {
    assert.doesNotMatch(raw, pattern, String(pattern));
  }
  const page = claimHeader(workspace) + summaryPanel(workspace) + policyPanel(workspace) + evidencePanel(workspace) +
    conversationView([{ turnId: "t1", prompt: HERO_PROMPT, status: "completed", answer: fixture("hero-review.md"), evidenceAttached: { documents: 3, photos: 5 } }], index, "t1");
  for (const pattern of [/sha256/i, /get_claim|get_policy|get_vehicle|get_customer_claim_history|file_search|claims_operations/i, /conversationId|responseId|conv_|resp_/]) {
    assert.doesNotMatch(page, pattern, String(pattern));
  }
});
