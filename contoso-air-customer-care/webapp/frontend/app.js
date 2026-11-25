// Contoso Air Travel Assistant - browser client.
// This page is a channel: it sends the customer's message to the backend, which relays it to the
// Foundry agent, and renders whatever the agent replies. It contains no customer-service logic.
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    member: $("member"),
    greeting: $("greeting"),
    tripCard: $("trip-card"),
    tripBody: $("trip-body"),
    tripEmpty: $("trip-empty"),
    messages: $("messages"),
    status: $("status"),
    statusText: $("status-text"),
    starters: $("starters"),
    form: $("composer"),
    input: $("input"),
    send: $("send"),
    newChat: $("new-chat"),
  };

  let sessionId = null;
  let busy = false;
  const introHtml = els.messages.innerHTML;
  const tripUnavailableText = els.tripEmpty.textContent;

  // ------------------------------------------------------------------ formatting helpers

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  function formatDate(isoDate) {
    const [y, m, d] = (isoDate || "").split("-").map(Number);
    if (!y || !m || !d) return isoDate || "";
    const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
    return `${DAYS[day]}, ${MONTHS[m - 1]} ${d}, ${y}`;
  }

  function formatTime(isoLocal) {
    const match = /T(\d{2}):(\d{2})/.exec(isoLocal || "");
    if (!match) return "";
    const hours = Number(match[1]);
    const suffix = hours >= 12 ? "PM" : "AM";
    return `${((hours + 11) % 12) + 1}:${match[2]} ${suffix}`;
  }

  function escapeHtml(text) {
    return String(text ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Minimal Markdown for agent replies. Input is HTML-escaped first, so only these tags can appear.
  function inline(text) {
    return escapeHtml(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }

      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      if (heading) {
        const level = Math.min(heading[1].length + 2, 4);
        html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
        i++;
        continue;
      }

      if (/^\s*\|.*\|\s*$/.test(line)) {
        const rows = [];
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
        const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        const isDivider = (row) => cells(row).every((c) => /^:?-{2,}:?$/.test(c));
        const body = rows.filter((r) => !isDivider(r));
        const hasHeader = rows.length > 1 && isDivider(rows[1]);
        let table = "<table>";
        body.forEach((row, idx) => {
          const tag = hasHeader && idx === 0 ? "th" : "td";
          table += "<tr>" + cells(row).map((c) => `<${tag}>${inline(c)}</${tag}>`).join("") + "</tr>";
        });
        html.push(table + "</table>");
        continue;
      }

      const listMatch = /^\s*([-*+]|\d+[.)])\s+/.exec(line);
      if (listMatch) {
        const ordered = /\d/.test(listMatch[1]);
        const pattern = ordered ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
        const items = [];
        while (i < lines.length) {
          const item = pattern.exec(lines[i]);
          if (item) { items.push(item[1]); i++; continue; }
          // Indented continuation or nested bullet: fold into the current item.
          if (items.length && /^\s{2,}\S/.test(lines[i])) {
            items[items.length - 1] += "<br>" + lines[i].trim().replace(/^[-*+]\s+/, "• ");
            i++;
            continue;
          }
          break;
        }
        const tag = ordered ? "ol" : "ul";
        html.push(`<${tag}>` + items.map((t) => `<li>${inline(t).replace(/&lt;br&gt;/g, "<br>")}</li>`).join("") + `</${tag}>`);
        continue;
      }

      const para = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*[-*+]\s|\s*\d+[.)]\s|\s*\|)/.test(lines[i])) {
        para.push(lines[i++]);
      }
      if (!para.length) para.push(lines[i++]);
      html.push(`<p>${para.map(inline).join("<br>")}</p>`);
    }
    return html.join("");
  }

  // ------------------------------------------------------------------ rendering

  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function addMessage(role, text) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    if (role === "user") bubble.textContent = text;
    else bubble.innerHTML = renderMarkdown(text);
    wrapper.appendChild(bubble);
    els.messages.appendChild(wrapper);
    scrollToBottom();
    return bubble;
  }

  function setStatus(text) {
    els.status.hidden = !text;
    els.statusText.textContent = text || "";
    if (text) scrollToBottom();
  }

  function setBusy(value) {
    busy = value;
    els.send.disabled = value;
    els.starters.querySelectorAll("button").forEach((b) => { b.disabled = value; });
  }

  function renderTrip(data) {
    if (data.firstName) {
      els.greeting.textContent = `Welcome back, ${data.firstName}.`;
      els.member.textContent = data.loyaltyTier ? `${data.firstName} · ${data.loyaltyTier} member` : data.firstName;
      els.member.hidden = false;
    }
    const trip = data.trip;
    if (!trip) {
      els.tripCard.hidden = true;
      els.tripEmpty.textContent = data.firstName ? "You have no upcoming trips." : tripUnavailableText;
      els.tripEmpty.hidden = false;
      return;
    }
    const statusClass = (status) => {
      const value = String(status || "").toLowerCase();
      if (value === "cancelled" || value === "diverted") return "status-alert";
      if (value === "delayed") return "status-warn";
      return "status-ok";
    };
    const segments = trip.segments.map((s) => `
      <div class="segment">
        <div class="segment-head">
          <span class="cities">${escapeHtml(s.originCity || s.origin)} &rarr; ${escapeHtml(s.destinationCity || s.destination)}</span>
          ${s.flightStatus ? `<span class="flight-status ${statusClass(s.flightStatus)}">${escapeHtml(s.flightStatus)}</span>` : ""}
        </div>
        <div class="flight-line">Flight ${escapeHtml(s.flightNumber)} · ${escapeHtml(formatDate(s.date))}</div>
        <div class="route">
          <span class="airport">${escapeHtml(s.origin)}<span class="time">${escapeHtml(formatTime(s.scheduledDeparture))}</span></span>
          <span class="arrow" aria-label="to">&#9992;</span>
          <span class="airport">${escapeHtml(s.destination)}<span class="time">${escapeHtml(formatTime(s.scheduledArrival))}</span></span>
        </div>
      </div>`).join("");
    els.tripBody.innerHTML = `${segments}
      <dl class="trip-meta">
        <dt>Confirmation</dt><dd>${escapeHtml(trip.confirmationCode)}</dd>
        <dt>Cabin</dt><dd>${escapeHtml(trip.cabin)}</dd>
        <dt>Travelers</dt><dd>${trip.passengers.map(escapeHtml).join("<br>")}</dd>
      </dl>`;
    els.tripCard.hidden = false;
    els.tripEmpty.hidden = true;
  }

  function renderStarters(heroPrompt, prompts) {
    els.starters.innerHTML = "";
    const all = [heroPrompt, ...(prompts || [])].filter((p, idx, list) => p && list.indexOf(p) === idx);
    all.forEach((prompt, idx) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = prompt;
      if (idx === 0 && prompt === heroPrompt) button.className = "suggested";
      button.addEventListener("click", () => sendMessage(prompt));
      els.starters.appendChild(button);
    });
  }

  function addError(message, reference) {
    const bubble = addMessage("error", message);
    if (reference) {
      const ref = document.createElement("span");
      ref.className = "reference";
      ref.textContent = `Reference: ${reference}`;
      bubble.appendChild(ref);
    }
  }

  // ------------------------------------------------------------------ backend calls

  async function startSession() {
    if (sessionId) {
      fetch(`api/session/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(() => {});
    }
    sessionId = null;
    els.messages.innerHTML = introHtml;
    setStatus("");
    try {
      const response = await fetch("api/session", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      sessionId = data.sessionId;
      renderTrip(data);
      renderStarters(data.heroPrompt, data.starterPrompts);
    } catch (err) {
      els.tripEmpty.hidden = false;
      addError("We couldn't start the Travel Assistant. Please refresh the page to try again.");
    }
  }

  // Parse a server-sent event stream from a fetch() response body.
  async function* readEvents(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        const data = [];
        block.split("\n").forEach((line) => {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        });
        if (data.length) yield { event, data: JSON.parse(data.join("\n")) };
      }
    }
  }

  async function sendMessage(text) {
    const message = (text || "").trim();
    if (!message || busy) return;
    if (!sessionId) await startSession();
    if (!sessionId) return;

    addMessage("user", message);
    els.input.value = "";
    els.starters.innerHTML = "";
    setBusy(true);
    setStatus("Working on it…");

    let bubble = null;
    let streamed = "";
    try {
      const response = await fetch("api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sessionId, message }),
      });
      if (response.status === 404) {
        await startSession();
        addError("Your chat session expired, so we started a new conversation. Please send your message again.");
        return;
      }
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

      for await (const { event, data } of readEvents(response)) {
        if (event === "status") {
          setStatus(data.message);
        } else if (event === "delta") {
          setStatus("");
          streamed += data.text;
          if (!bubble) bubble = addMessage("assistant", "");
          bubble.innerHTML = renderMarkdown(streamed);
          scrollToBottom();
        } else if (event === "done") {
          const finalText = data.text || streamed;
          if (!bubble) bubble = addMessage("assistant", "");
          bubble.innerHTML = renderMarkdown(finalText);
          scrollToBottom();
        } else if (event === "error") {
          setStatus("");
          addError(data.message, data.reference);
        }
      }
    } catch (err) {
      addError("Sorry, something went wrong. Please try again.");
    } finally {
      setStatus("");
      setBusy(false);
      els.input.focus();
    }
  }

  // ------------------------------------------------------------------ wiring

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(els.input.value);
  });
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(els.input.value);
    }
  });
  els.newChat.addEventListener("click", () => { if (!busy) startSession(); });

  startSession();
})();
