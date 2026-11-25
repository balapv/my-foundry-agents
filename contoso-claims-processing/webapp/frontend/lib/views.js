// HTML builders for the Claims Review workspace. Pure functions (no DOM access) so they can be
// tested with `node --test`. Every value is escaped; agent answers go through the safe Markdown
// renderer. These builders present facts and the agent's words; they draw no claim conclusions.

import { escapeHtml as esc, renderMarkdown, splitSections, plainText } from "./markdown.js";
import { citationDecorator, evidenceReferences } from "./sources.js";

export const HERO_PROMPT = "Review this claim and tell me what I should do next.";
const NOT_AVAILABLE = '<span class="muted">Not available</span>';
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function formatMoney(amount) {
  if (amount === null || amount === undefined || Number.isNaN(Number(amount))) return null;
  const value = Number(amount);
  const cents = Math.round(value * 100) % 100 !== 0;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: cents ? 2 : 0,
    maximumFractionDigits: 2,
  });
}

// Calendar dates (YYYY-MM-DD) are shown as written, never shifted by the browser's time zone.
export function formatDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? "");
  if (!match) return null;
  return `${MONTHS[Number(match[2]) - 1]} ${Number(match[3])}, ${match[1]}`;
}

export function formatTime(value) {
  const match = /^(\d{2}):(\d{2})/.exec(value ?? "");
  if (!match) return null;
  const hour = Number(match[1]);
  return `${((hour + 11) % 12) + 1}:${match[2]} ${hour < 12 ? "AM" : "PM"}`;
}

// Timestamps are shown in the claim's local time zone when known.
export function formatTimestamp(value, timeZone) {
  const date = new Date(value ?? "");
  if (!value || Number.isNaN(date.getTime())) return null;
  const options = { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" };
  try {
    return date.toLocaleString("en-US", { ...options, timeZone: timeZone || undefined, timeZoneName: "short" });
  } catch {
    return date.toLocaleString("en-US", { ...options, timeZone: "UTC", timeZoneName: "short" });
  }
}

const show = (value) => (value === null || value === undefined || value === "" ? NOT_AVAILABLE : esc(value));

function fact(label, valueHtml, extra = "") {
  return `<div class="fact${extra}"><dt>${esc(label)}</dt><dd>${valueHtml}</dd></div>`;
}

// --------------------------------------------------------------------------------------------------
// Claim summary and policy facts
// --------------------------------------------------------------------------------------------------

export function statusClass(status) {
  return `status status-${String(status ?? "unknown").toLowerCase().replace(/[^a-z]+/g, "-")}`;
}

export function claimHeader(workspace) {
  const s = workspace.summary ?? {};
  const status = s.claimStatus ? `<span class="${statusClass(s.claimStatus)}">${esc(s.claimStatus)}</span>` : "";
  const subtitle = [s.policyholder, s.vehicle].filter(Boolean).map(esc).join(" &middot; ");
  return `<div class="claim-title"><h1>Claim ${esc(workspace.claimId)}</h1>${status}</div>` +
    (subtitle ? `<p class="claim-subtitle">${subtitle}</p>` : "");
}

export function summaryPanel(workspace) {
  const s = workspace.summary ?? {};
  const loss = [formatDate(s.lossDate), formatTime(s.lossTime)].filter(Boolean).join(" at ");
  const vehicle = s.vehicle ? esc(s.vehicle) + (s.vehicleColor ? `<span class="sub">${esc(s.vehicleColor)}</span>` : "") : NOT_AVAILABLE;
  const estimate = formatMoney(s.estimateTotal);
  const facts = [
    fact("Claim", show(s.claimId)),
    fact("Status", s.claimStatus ? `<span class="${statusClass(s.claimStatus)}">${esc(s.claimStatus)}</span>` : NOT_AVAILABLE),
    fact("Policyholder", show(s.policyholder)),
    fact("Policy", show(s.policyId)),
    fact("Vehicle", vehicle, " wide"),
    fact("Date of loss", loss ? esc(loss) : NOT_AVAILABLE),
    fact("Claim type", show(s.claimType)),
    fact("Loss description", show(s.causeOfLoss)),
    fact("Loss location", show(s.lossLocation), " wide"),
    fact("Repair facility", show(s.repairFacility), " wide"),
    fact("Repair estimate", estimate ? `<span class="amount">${esc(estimate)}</span>${s.estimateId ? `<span class="sub">${esc(s.estimateId)}</span>` : ""}` : NOT_AVAILABLE),
    fact("Collision deductible", formatMoney(s.collisionDeductible) ? `<span class="amount">${esc(formatMoney(s.collisionDeductible))}</span>` : NOT_AVAILABLE),
  ];
  const note = workspace.recordsAvailable === false
    ? '<p class="notice">Some claim records could not be loaded. Facts that are not available are marked.</p>'
    : "";
  const asOf = workspace.recordsAsOf ? `<p class="as-of">Claims records as of ${esc(formatTimestamp(workspace.recordsAsOf, s.lossTimeZone))}</p>` : "";
  return `<h2>Claim summary</h2>${note}<dl class="facts">${facts.join("")}</dl>${asOf}`;
}

function limitsText(coverage) {
  const parts = [];
  const deductible = formatMoney(coverage.deductible);
  if (deductible) parts.push(`${deductible} deductible`);
  for (const limit of coverage.limits ?? []) {
    const amount = formatMoney(limit.amount);
    if (amount) parts.push(`${amount} ${String(limit.limitType ?? "").toLowerCase()}`.trim());
  }
  return parts.join(" &middot; ");
}

export function policyPanel(workspace) {
  const p = workspace.policy;
  if (!p) return `<h2>Policy</h2><p class="muted">Policy records are not available.</p>`;
  const term = [formatDate(p.termEffectiveDate), formatDate(p.termExpirationDate)].filter(Boolean).join(" \u2013 ");
  const rows = (list) => (list ?? []).map((c) => `<li><span>${esc(c.coverageName)}</span><span class="limits">${limitsText(c)}</span></li>`).join("");
  return `<h2>Policy ${esc(p.policyId)}</h2>
<dl class="facts">
  ${fact("Product", show(p.productName), " wide")}
  ${fact("Policy status", show(p.policyStatus))}
  ${fact("Policy term", term ? esc(term) : NOT_AVAILABLE)}
  ${p.lossPayee ? fact("Loss payee", esc(p.lossPayee), " wide") : ""}
</dl>
<details class="coverages"><summary>Coverages on record</summary>
  <h3>Vehicle coverages</h3><ul class="coverage-list">${rows(p.vehicleCoverages)}</ul>
  <h3>Policy coverages</h3><ul class="coverage-list">${rows(p.policyCoverages)}</ul>
</details>`;
}

// --------------------------------------------------------------------------------------------------
// Evidence panel
// --------------------------------------------------------------------------------------------------

function docMeta(item, timeZone) {
  const parts = [item.documentId];
  if (item.pageCount) parts.push(`${item.pageCount} ${item.pageCount === 1 ? "page" : "pages"}`);
  if (item.source) parts.push(item.source);
  const received = formatTimestamp(item.receivedAt, timeZone);
  if (received) parts.push(`Received ${received}`);
  return parts.map(esc).join(" &middot; ");
}

export function evidencePanel(workspace) {
  const tz = workspace.summary?.lossTimeZone;
  const items = workspace.evidence ?? [];
  const documents = items.filter((i) => i.kind === "pdf");
  const photos = items.filter((i) => i.kind === "photo");
  if (!items.length) {
    return `<h2>Evidence</h2><p class="muted">No evidence package is on file for this claim.</p>${guidanceList(workspace)}`;
  }
  const docs = documents.map((d) => `
<li><button type="button" class="evidence-item doc" data-open-doc="${esc(d.documentId)}">
  <span class="doc-icon" aria-hidden="true">PDF</span>
  <span class="doc-text"><span class="doc-type">${esc(d.documentType)}</span>
  <span class="doc-title">${esc(d.title)}</span>
  <span class="doc-meta">${docMeta(d, tz)}</span></span>
</button></li>`).join("");
  const thumbs = photos.map((p) => `
<li><button type="button" class="evidence-item photo" data-open-doc="${esc(p.documentId)}" title="${esc(p.title)}">
  <img src="${esc(p.url)}" alt="${esc(p.title)}" loading="lazy" width="${Number(p.widthPx) || 1536}" height="${Number(p.heightPx) || 1024}">
  <span class="photo-caption"><span class="photo-id">${esc(p.documentId)}</span>${esc(p.title)}</span>
</button></li>`).join("");
  const photoReceived = photos.length ? formatTimestamp(photos[0].receivedAt, tz) : null;
  return `<h2>Evidence <span class="count">${items.length} items</span></h2>
<h3>Documents</h3><ul class="doc-list">${docs || '<li class="muted">No documents.</li>'}</ul>
<h3>Photographs <span class="count">${photos.length}</span></h3>
${photoReceived ? `<p class="as-of">Submitted by ${esc(photos[0].source ?? "")} &middot; Received ${esc(photoReceived)}</p>` : ""}
<ul class="photo-grid">${thumbs || '<li class="muted">No photographs.</li>'}</ul>
${guidanceList(workspace)}`;
}

export function guidanceList(workspace) {
  const list = (workspace.guidance ?? []).map((g) => `
<li><button type="button" class="evidence-item guide" data-open-guidance="${esc(g.guidanceId)}">${esc(g.title)}</button></li>`).join("");
  return list ? `<h3>Company guidance</h3><ul class="guide-list">${list}</ul>` : "";
}

// --------------------------------------------------------------------------------------------------
// Agent conversation
// --------------------------------------------------------------------------------------------------

export const STAGES = {
  queued: "Starting\u2026",
  verifying: "Verifying the claim evidence package\u2026",
  sending: { first: "Sending the claim and its evidence to the review agent\u2026", followUp: "Sending your question to the review agent\u2026" },
  reviewing: "The agent is reviewing the claim\u2026",
  records: "Checking claims records\u2026",
  guidance: "Searching company guidance\u2026",
  writing: "Preparing the response\u2026",
};
export const SLOW_SECONDS = 60;

export function stageLabel(stage, firstTurn) {
  const label = STAGES[stage] ?? STAGES.reviewing;
  return typeof label === "string" ? label : label[firstTurn ? "first" : "followUp"];
}

function sectionClass(heading) {
  const key = String(heading ?? "").toLowerCase().replace(/[^a-z ]/g, "").trim();
  const known = ["recommendation", "coverage", "what checks out", "needs review", "why", "next step", "sources"];
  const match = known.find((k) => key === k || key.startsWith(`${k} `) || key.startsWith(k));
  return match ? ` section-${match.replace(/ /g, "-")}` : "";
}

// The agent's answer, rendered without changing its words. Top-level sections become cards; an answer
// without headings is shown as one block. Known evidence citations become buttons.
export function answerView(markdown, index) {
  const decorate = citationDecorator(index);
  const sections = splitSections(markdown);
  const structured = sections.some((s) => s.heading);
  if (!structured) {
    return `<div class="answer answer-plain">${renderMarkdown(markdown, { decorate })}</div>`;
  }
  const cards = sections.map((s) => {
    const title = s.heading ? `<h3 class="card-title">${decorate(esc(s.heading))}</h3>` : "";
    return `<section class="answer-card${sectionClass(s.heading)}">${title}${renderMarkdown(s.body, { decorate, headingOffset: 3 })}</section>`;
  });
  return `<div class="answer answer-structured">${cards.join("")}</div>`;
}

export function referencesView(markdown, index) {
  const groups = evidenceReferences(markdown, index);
  if (!groups.length) return "";
  const decorate = citationDecorator(index);
  const body = groups.map((g) => {
    const items = g.items.map((item) => {
      if (g.key === "guidance") {
        return `<button type="button" class="ref-item guide" data-open-guidance="${esc(item.guidanceId)}">${esc(item.title)}</button>`;
      }
      if (item.kind === "photo") {
        return `<button type="button" class="ref-item ref-photo" data-open-doc="${esc(item.documentId)}" title="${esc(item.title)}">
<img src="${esc(item.url)}" alt="${esc(item.title)}" loading="lazy"><span>${esc(item.documentId)} &middot; ${esc(item.title)}</span></button>`;
      }
      return `<button type="button" class="ref-item ref-doc" data-open-doc="${esc(item.documentId)}"><span class="doc-icon" aria-hidden="true">PDF</span><span>${esc(item.documentId)} &middot; ${esc(item.title)}</span></button>`;
    }).join("");
    const quotes = g.statements.slice(0, 4).map((s) => `<li>${decorate(esc(plainText(s)))}</li>`).join("");
    return `<div class="ref-group ref-${g.key}"><h4>${esc(g.label)}</h4><div class="ref-items">${items}</div>${quotes ? `<ul class="ref-quotes">${quotes}</ul>` : ""}</div>`;
  }).join("");
  return `<details class="references" open><summary>Evidence referenced in this answer</summary>
<p class="ref-note">Items the agent cited, with the agent's own statements about them. Open any item to inspect it.</p>
<div class="ref-groups">${body}</div></details>`;
}

export function errorView(error) {
  const message = error?.message || "Something went wrong while reviewing this claim.";
  const reference = error?.reference ? `<span class="reference">Reference ${esc(error.reference)}</span>` : "";
  let action = "";
  if (error?.retry === "retry") action = '<button type="button" class="link-button" data-action="retry">Try again</button>';
  else if (error?.retry === "new_review") action = '<button type="button" class="link-button" data-action="reset">Start a new review</button>';
  return `<div class="error-card" role="alert"><p>${esc(message)}</p><p class="error-meta">${reference}${action}</p></div>`;
}

function attachmentNote(turn) {
  const a = turn.evidenceAttached;
  if (!a || !(a.documents || a.photos)) return "";
  const parts = [];
  if (a.documents) parts.push(`${a.documents} ${a.documents === 1 ? "document" : "documents"}`);
  if (a.photos) parts.push(`${a.photos} ${a.photos === 1 ? "photograph" : "photographs"}`);
  return `<p class="attached">Claim evidence sent with this request: ${parts.join(" and ")}</p>`;
}

export function progressView(turn, firstTurn) {
  const seconds = Math.floor(turn.elapsedSeconds ?? 0);
  const slow = seconds >= SLOW_SECONDS
    ? '<p class="slow">This is taking longer than usual. The agent is still working; you can keep waiting or start a new review.</p>'
    : "";
  return `<div class="progress" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span>
<span class="progress-label">${esc(stageLabel(turn.stage, firstTurn))}</span><span class="elapsed">${seconds}s</span></div>${slow}`;
}

export function conversationView(turns, index, firstTurnId) {
  return turns.map((turn) => {
    const first = turn.turnId === firstTurnId;
    const user = `<div class="msg msg-user"><div class="bubble">${esc(turn.prompt)}</div></div>`;
    let agent;
    if (turn.status === "completed" && turn.answer) {
      const seconds = turn.elapsedSeconds ? `<span class="elapsed">${Math.round(turn.elapsedSeconds)}s</span>` : "";
      agent = `<div class="msg msg-agent"><div class="agent-label">Claims review agent ${seconds}</div>${attachmentNote(turn)}${answerView(turn.answer, index)}${referencesView(turn.answer, index)}</div>`;
    } else if (turn.status === "failed") {
      agent = `<div class="msg msg-agent">${errorView(turn.error)}</div>`;
    } else {
      agent = `<div class="msg msg-agent">${progressView(turn, first)}</div>`;
    }
    return `<article class="exchange" data-turn="${esc(turn.turnId)}">${user}${agent}</article>`;
  }).join("");
}
