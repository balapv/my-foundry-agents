// Contoso Claims Review: browser entry point. Wires the page to the backend API. All claims reasoning
// happens in the Foundry agent; this file only presents facts, evidence and the agent's answers.

import { ApiError, ReviewController, httpApi } from "./lib/review.js";
import { buildSourceIndex, citedDocumentIds } from "./lib/sources.js";
import {
  HERO_PROMPT, claimHeader, conversationView, errorView, evidencePanel, formatTimestamp, policyPanel, summaryPanel,
} from "./lib/views.js";
import { escapeHtml as esc } from "./lib/markdown.js";

const CLAIM_PATTERN = /^CLM-\d{5}$/;
const $ = (id) => document.getElementById(id);
const api = httpApi();
let workspace = null;
let index = buildSourceIndex(null);
let controller = null;
let viewerPhotos = [];
let viewerPosition = -1;
const rendered = new Map(); // turnId -> signature of the last render

function requestedClaim(defaultClaimId) {
  const value = new URLSearchParams(window.location.search).get("claim");
  return value && CLAIM_PATTERN.test(value) ? value : defaultClaimId;
}

// -- conversation -------------------------------------------------------------------------------

function signature(turn) {
  return [turn.turnId, turn.status, turn.stage, Math.floor(turn.elapsedSeconds ?? 0), turn.error?.reference ?? ""].join("|");
}

function renderConversation(ctrl) {
  const list = $("conversation");
  const turns = ctrl.turns;
  if (!turns.length) {
    list.replaceChildren();
    rendered.clear();
  }
  const keep = new Set(turns.map((t) => t.turnId));
  for (const node of [...list.children]) {
    if (!keep.has(node.dataset.turn)) {
      rendered.delete(node.dataset.turn);
      node.remove();
    }
  }
  let added = false;
  turns.forEach((turn, position) => {
    const sig = signature(turn);
    let node = list.querySelector(`[data-turn="${CSS.escape(turn.turnId)}"]`);
    if (node && rendered.get(turn.turnId) === sig) return;
    const template = document.createElement("template");
    template.innerHTML = conversationView([turn], index, ctrl.firstTurnId);
    const fresh = template.content.firstElementChild;
    if (node) node.replaceWith(fresh);
    else {
      const before = list.children[position] ?? null;
      list.insertBefore(fresh, before);
      added = true;
    }
    rendered.set(turn.turnId, sig);
    if (turn.status !== "running") added = true;
  });

  $("empty-state").hidden = turns.length > 0;
  $("message").disabled = ctrl.busy;
  $("send-button").disabled = ctrl.busy;
  $("reset-button").disabled = turns.length === 0;
  $("message").placeholder = ctrl.started ? "Ask a follow-up question\u2026" : "Ask about this claim\u2026";
  highlightCited(ctrl);
  if (added) list.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// Marks the evidence cited by the latest answer so the adjuster can find it in the evidence panel.
function highlightCited(ctrl) {
  const latest = [...ctrl.turns].reverse().find((t) => t.status === "completed" && t.answer);
  const cited = new Set(latest ? citedDocumentIds(latest.answer, index) : []);
  document.querySelectorAll("#evidence [data-open-doc]").forEach((el) => {
    el.classList.toggle("cited", cited.has(el.dataset.openDoc));
  });
}

async function send(text) {
  const prompt = String(text ?? "").trim();
  if (!prompt || !controller || controller.busy) return;
  $("message").value = "";
  await controller.send(prompt);
  $("message").focus();
}

// -- evidence viewer ----------------------------------------------------------------------------

function openViewer({ kicker, title, meta, url, body }) {
  $("viewer-kicker").textContent = kicker;
  $("viewer-title").textContent = title;
  $("viewer-meta").textContent = meta;
  $("viewer-open").href = url;
  $("viewer-body").replaceChildren(body);
  const dialog = $("viewer");
  if (!dialog.open) dialog.showModal();
}

function pdfFrame(url, title) {
  const frame = document.createElement("iframe");
  frame.src = url;
  frame.title = title;
  frame.className = "pdf-frame";
  return frame;
}

function openDocument(documentId, page) {
  const item = index.docs.get(documentId);
  if (!item) return;
  const tz = workspace?.summary?.lossTimeZone;
  const received = formatTimestamp(item.receivedAt, tz);
  const meta = [item.documentId, item.pageCount ? `${item.pageCount} pages` : null, item.source,
    received ? `Received ${received}` : null].filter(Boolean).join(" \u00b7 ");
  if (item.kind === "photo") {
    viewerPhotos = (workspace.evidence ?? []).filter((e) => e.kind === "photo");
    viewerPosition = viewerPhotos.findIndex((p) => p.documentId === documentId);
    const img = document.createElement("img");
    img.src = item.url;
    img.alt = item.title;
    img.className = "photo-large";
    openViewer({ kicker: item.documentType, title: item.title, meta, url: item.url, body: img });
    $("viewer-nav").hidden = viewerPhotos.length < 2;
    $("viewer-position").textContent = `Photograph ${viewerPosition + 1} of ${viewerPhotos.length}`;
    return;
  }
  viewerPhotos = [];
  $("viewer-nav").hidden = true;
  const anchor = page ? `#page=${Number(page)}` : "";
  openViewer({ kicker: item.documentType, title: item.title, meta: page ? `${meta} \u00b7 Page ${page}` : meta,
    url: item.url, body: pdfFrame(item.url + anchor, item.title) });
}

function openGuidance(guidanceId) {
  const item = index.guidance.find((g) => g.guidanceId === guidanceId);
  if (!item) return;
  viewerPhotos = [];
  $("viewer-nav").hidden = true;
  openViewer({ kicker: "Company guidance", title: item.title, meta: "Contoso Insurance internal guidance", url: item.url,
    body: pdfFrame(item.url, item.title) });
}

function stepPhoto(delta) {
  if (!viewerPhotos.length) return;
  const next = (viewerPosition + delta + viewerPhotos.length) % viewerPhotos.length;
  openDocument(viewerPhotos[next].documentId);
}

// -- page ---------------------------------------------------------------------------------------

function showLoadError(message) {
  const box = $("load-error");
  box.innerHTML = errorView({ message });
  box.hidden = false;
  $("claim-header").innerHTML = '<div class="claim-title"><h1>Claim unavailable</h1></div>';
}

function onClick(event) {
  const target = event.target.closest("button, a");
  if (!target) return;
  if (target.dataset.docs) {
    const [first] = target.dataset.docs.split(" ");
    openDocument(first, target.dataset.page);
    return;
  }
  if (target.dataset.openDoc) return openDocument(target.dataset.openDoc);
  if (target.dataset.guidance) return openGuidance(target.dataset.guidance);
  if (target.dataset.openGuidance) return openGuidance(target.dataset.openGuidance);
  if (target.hasAttribute("data-prompt")) return send(target.textContent);
  switch (target.dataset.action) {
    case "reset":
      return controller?.reset().then(() => $("message").focus());
    case "retry":
      return controller?.retry();
    case "about":
      return $("about").showModal();
    case "close-about":
      return $("about").close();
    case "close-viewer":
      return $("viewer").close();
    case "prev-photo":
      return stepPhoto(-1);
    case "next-photo":
      return stepPhoto(1);
    default:
  }
}

function onKey(event) {
  if (event.target.id === "message" && event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    send(event.target.value);
  }
  if ($("viewer").open && viewerPhotos.length && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
    stepPhoto(event.key === "ArrowRight" ? 1 : -1);
  }
}

async function start() {
  document.addEventListener("click", onClick);
  document.addEventListener("keydown", onKey);
  $("composer").addEventListener("submit", (event) => {
    event.preventDefault();
    send($("message").value);
  });
  $("viewer").addEventListener("close", () => $("viewer-body").replaceChildren());
  $("hero-prompt").textContent = HERO_PROMPT;

  let about;
  try {
    about = await api.about();
    $("about-text").textContent = about.about;
    $("about-facts").innerHTML = [["Application", about.application], ["Foundry agent", about.agentName],
      ["Agent version", about.agentVersion ?? "Latest"]]
      .filter(([, v]) => v).map(([k, v]) => `<div class="fact"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");
  } catch (err) {
    showLoadError(err instanceof ApiError ? err.message : "The Claims Review service could not be reached.");
    return;
  }

  const claimId = requestedClaim(about.defaultClaimId);
  try {
    workspace = await api.claim(claimId);
  } catch (err) {
    showLoadError(err?.status === 404 ? `Claim ${claimId} was not found.` : err.message);
    return;
  }
  index = buildSourceIndex(workspace);
  document.title = `Claim ${workspace.claimId} \u00b7 Contoso Claims Review`;
  $("claim-header").innerHTML = claimHeader(workspace);
  $("summary").innerHTML = summaryPanel(workspace);
  $("evidence").innerHTML = evidencePanel(workspace);
  $("policy").innerHTML = policyPanel(workspace);
  $("workspace").setAttribute("aria-busy", "false");

  controller = new ReviewController({ api, claimId: workspace.claimId, onChange: renderConversation });
  renderConversation(controller);
}

start();
