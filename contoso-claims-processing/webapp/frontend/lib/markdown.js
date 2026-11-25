// Safe Markdown rendering for agent answers.
//
// The renderer escapes all text first and only then adds a fixed set of tags (headings, paragraphs,
// lists, tables, block quotes, code, emphasis). It never emits raw HTML from the answer, links,
// images, attributes or inline styles, so agent text cannot inject markup or scripts. An optional
// `decorate(html)` hook receives already-escaped inline HTML (used to turn known evidence citations
// into buttons).

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

const LIST_ITEM = /^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const FENCE = /^\s*(```|~~~)/;
const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

export function renderInline(text, decorate) {
  return String(text ?? "")
    .split(/(`[^`\n]+`)/)
    .map((part) => {
      if (/^`[^`\n]+`$/.test(part)) return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
      let html = escapeHtml(part);
      html = html.replace(/!?\[([^\]\n]+)\]\([^)\s]*\)/g, "$1"); // links and images render as their text only
      html = html.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/__(?=\S)([\s\S]*?\S)__/g, "<strong>$1</strong>");
      html = html.replace(/(^|[^*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\w])/g, "$1<em>$2</em>");
      html = html.replace(/(^|[^_\w])_(?=[^\s_])([^_\n]*?[^\s_])_(?![_\w])/g, "$1<em>$2</em>");
      return decorate ? decorate(html) : html;
    })
    .join("");
}

function splitRow(line) {
  let row = line.trim();
  if (row.startsWith("|")) row = row.slice(1);
  if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
  return row.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, "|").trim());
}

function renderTable(lines, inline) {
  const header = splitRow(lines[0]);
  const body = lines.slice(2).map(splitRow);
  const head = header.map((cell) => `<th>${inline(cell)}</th>`).join("");
  const rows = body
    .map((cells) => `<tr>${header.map((_, i) => `<td>${inline(cells[i] ?? "")}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="md-table"><table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderList(lines, inline) {
  let html = "";
  const stack = []; // { indent, tag }
  for (const line of lines) {
    const match = line.match(LIST_ITEM);
    if (!match) {
      html += " " + inline(line.trim());
      continue;
    }
    const indent = match[1].replace(/\t/g, "    ").length;
    const tag = /\d/.test(match[2]) ? "ol" : "ul";
    const start = tag === "ol" ? parseInt(match[2], 10) : 1;
    const open = () => `<${tag}${tag === "ol" && start !== 1 ? ` start="${start}"` : ""}><li>`;
    const top = stack[stack.length - 1];
    if (!top || indent > top.indent) {
      html += open();
      stack.push({ indent, tag });
    } else {
      while (stack.length > 1 && indent < stack[stack.length - 1].indent) {
        html += `</li></${stack.pop().tag}>`;
      }
      const current = stack[stack.length - 1];
      if (current.tag !== tag) {
        html += `</li></${stack.pop().tag}>` + open();
        stack.push({ indent, tag });
      } else {
        html += "</li><li>";
      }
    }
    html += inline(match[3]);
  }
  while (stack.length) html += `</li></${stack.pop().tag}>`;
  return html;
}

export function renderMarkdown(markdown, options = {}) {
  const inline = (text) => renderInline(text, options.decorate);
  const headingOffset = options.headingOffset ?? 2;
  const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) out.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) {
      flush();
      continue;
    }
    if (FENCE.test(line)) {
      flush();
      const fence = line.trim().slice(0, 3);
      const code = [];
      for (i += 1; i < lines.length && !lines[i].trim().startsWith(fence); i += 1) code.push(lines[i]);
      out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      flush();
      const level = Math.min(6, heading[1].length + headingOffset);
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (RULE.test(line)) {
      flush();
      out.push("<hr>");
      continue;
    }
    if (TABLE_ROW.test(line) && i + 1 < lines.length && TABLE_DIVIDER.test(lines[i + 1])) {
      flush();
      const block = [line, lines[i + 1]];
      for (i += 2; i < lines.length && TABLE_ROW.test(lines[i]); i += 1) block.push(lines[i]);
      i -= 1;
      out.push(renderTable(block, inline));
      continue;
    }
    if (/^\s*>/.test(line)) {
      flush();
      const block = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i += 1) block.push(lines[i].replace(/^\s*>\s?/, ""));
      i -= 1;
      out.push(`<blockquote>${renderMarkdown(block.join("\n"), options)}</blockquote>`);
      continue;
    }
    if (LIST_ITEM.test(line)) {
      flush();
      const block = [];
      for (; i < lines.length; i += 1) {
        const current = lines[i];
        if (!current.trim()) {
          // A blank line continues the list only when another item follows.
          let next = i + 1;
          while (next < lines.length && !lines[next].trim()) next += 1;
          if (next < lines.length && LIST_ITEM.test(lines[next])) {
            i = next - 1;
            continue;
          }
          break;
        }
        if (LIST_ITEM.test(current) || /^\s+\S/.test(current)) block.push(current);
        else break;
      }
      i -= 1;
      out.push(renderList(block, inline));
      continue;
    }
    paragraph.push(line.trim());
  }
  flush();
  return out.join("\n");
}

// Split an answer into sections at its top-level headings. Text before the first heading becomes a
// section with a null heading. An answer without headings is one section.
export function splitSections(markdown) {
  const lines = String(markdown ?? "").replace(/\r\n?/g, "\n").split("\n");
  let inFence = false;
  const levels = [];
  lines.forEach((line) => {
    if (FENCE.test(line)) inFence = !inFence;
    const match = !inFence && line.match(/^(#{1,3})\s+\S/);
    if (match) levels.push(match[1].length);
  });
  if (!levels.length) return [{ heading: null, body: String(markdown ?? "").trim() }];
  const level = Math.min(...levels);
  const sections = [];
  let current = { heading: null, body: [] };
  inFence = false;
  for (const line of lines) {
    if (FENCE.test(line)) inFence = !inFence;
    const match = !inFence && line.match(HEADING);
    if (match && match[1].length === level) {
      sections.push(current);
      current = { heading: match[2].trim(), body: [] };
    } else {
      current.body.push(line);
    }
  }
  sections.push(current);
  return sections
    .map((s) => ({ heading: s.heading, body: s.body.join("\n").trim() }))
    .filter((s) => s.heading !== null || s.body);
}

// Plain text of a Markdown fragment (for short quotations of the agent's own words).
export function plainText(markdown) {
  return String(markdown ?? "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!?\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1$2")
    .replace(/^\s*(#{1,6}|>|[-*+]|\d{1,3}[.)])\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}
