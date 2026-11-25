// Deterministic mapping from evidence identifiers cited in an agent answer to the claim's evidence.
//
// This module only recognizes identifiers (DOC-nnnnn-nn, ranges and page numbers) and guidance titles
// that the claim's evidence catalog already lists, so the adjuster can open the cited item. It never
// decides what the evidence means: the statements it collects are the agent's own words, quoted
// unchanged. Identifiers that are not in the catalog stay plain text.

import { escapeHtml, splitSections } from "./markdown.js";

const CITATION =
  /\bDOC-(\d{5})-(\d{2})(?:\s*(?:[\u2013\u2014-]|to|through)\s*(?:DOC-\1-)?(\d{2})(?!\d))?(?:,?\s*(?:pages?|pp?\.)\s*(\d{1,2})(?:\s*(?:[\u2013\u2014-]|to|and)\s*\d{1,2})?(?!\d))?/g;
const MAX_RANGE = 30;

export function buildSourceIndex(workspace) {
  const docs = new Map();
  for (const item of workspace?.evidence ?? []) docs.set(item.documentId, item);
  const guidance = (workspace?.guidance ?? []).filter((g) => g.title && g.guidanceId);
  return { docs, guidance };
}

function expand(claim, first, last, index) {
  const start = parseInt(first, 10);
  const end = last === undefined ? start : parseInt(last, 10);
  if (end < start || end - start > MAX_RANGE) return [];
  const ids = [];
  for (let n = start; n <= end; n += 1) {
    const id = `DOC-${claim}-${String(n).padStart(2, "0")}`;
    if (index.docs.has(id)) ids.push(id);
  }
  return ids;
}

// All citations of catalogued evidence in a text: [{ text, documentIds, page }].
export function findCitations(text, index) {
  const found = [];
  for (const match of String(text ?? "").matchAll(CITATION)) {
    const ids = expand(match[1], match[2], match[3], index);
    if (ids.length) found.push({ text: match[0], documentIds: ids, page: match[4] ? Number(match[4]) : null });
  }
  return found;
}

export function citedDocumentIds(text, index) {
  return [...new Set(findCitations(text, index).flatMap((c) => c.documentIds))];
}

export function citedGuidance(text, index) {
  const lower = String(text ?? "").toLowerCase();
  return index.guidance.filter((g) => lower.includes(g.title.toLowerCase()));
}

// Decorates escaped inline HTML: known citations and guidance titles become buttons.
export function citationDecorator(index) {
  return (html) => {
    let out = html;
    for (const g of index.guidance) {
      const title = escapeHtml(g.title);
      out = out.split(title).join(
        `<button type="button" class="cite cite-guidance" data-guidance="${escapeHtml(g.guidanceId)}">${title}</button>`,
      );
    }
    return out.replace(CITATION, (whole, claim, first, last, page) => {
      const ids = expand(claim, first, last, index);
      if (!ids.length) return whole;
      const titles = ids.map((id) => index.docs.get(id).title).join("; ");
      const pageAttr = page ? ` data-page="${Number(page)}"` : "";
      return `<button type="button" class="cite" data-docs="${ids.join(" ")}"${pageAttr} title="Open ${escapeHtml(titles)}">${whole}</button>`;
    });
  };
}

// --------------------------------------------------------------------------------------------------
// "Evidence referenced in this answer": the cited items, grouped by evidence type, each group with
// the agent's own statements that cite it.
// --------------------------------------------------------------------------------------------------

const GROUPS = [
  { key: "estimate", label: "Repair estimate", test: (d) => d.documentType === "Repair estimate" },
  { key: "reports", label: "Claim form and police report", test: (d) => ["Claim form", "Police report"].includes(d.documentType) },
  { key: "photos", label: "Photographs", test: (d) => d.kind === "photo" },
  { key: "other", label: "Other evidence", test: () => true },
];

// Statement units of a Markdown fragment: whole table rows, whole list items, sentences of paragraphs.
export function statementUnits(markdown) {
  const units = [];
  const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
  let paragraph = [];
  const flush = () => {
    const text = paragraph.join(" ").trim();
    if (text) units.push(...text.split(/(?<=[.!?])\s+(?=[A-Z*\u201c"(])/));
    paragraph = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || /^#{1,6}\s/.test(line) || /^\|?\s*:?-{3,}/.test(line)) {
      flush();
      continue;
    }
    if (line.startsWith("|")) {
      flush();
      units.push(line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()).filter(Boolean).join(" \u2014 "));
    } else if (/^([-*+]|\d{1,3}[.)])\s+/.test(line)) {
      flush();
      units.push(line.replace(/^([-*+]|\d{1,3}[.)])\s+/, ""));
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return units.filter((u) => u.trim());
}

export function evidenceReferences(markdown, index) {
  const sections = splitSections(markdown);
  // The answer's own "Sources" list cites everything; quoting it adds nothing, but its items still count.
  const quotable = sections.filter((s) => !/^sources?\b/i.test(s.heading ?? "")).map((s) => s.body).join("\n\n");
  const units = statementUnits(quotable);
  const cited = citedDocumentIds(markdown, index);
  const groups = [];
  const placed = new Set();
  for (const group of GROUPS) {
    const items = cited.filter((id) => !placed.has(id) && group.test(index.docs.get(id))).map((id) => index.docs.get(id));
    if (!items.length) continue;
    items.forEach((item) => placed.add(item.documentId));
    const ids = new Set(items.map((i) => i.documentId));
    const statements = units.filter((u) => citedDocumentIds(u, index).some((id) => ids.has(id)));
    groups.push({ key: group.key, label: group.label, items, statements: [...new Set(statements)] });
  }
  const guidance = citedGuidance(markdown, index);
  if (guidance.length) {
    const statements = units.filter((u) => citedGuidance(u, index).length);
    groups.push({ key: "guidance", label: "Company guidance", items: guidance, statements: [...new Set(statements)] });
  }
  return groups;
}
