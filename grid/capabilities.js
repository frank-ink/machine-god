// Capability registry and routing: which connected AI should take a request. Deterministic: keywords in, ranked list out. No model decides.
// Defaults ship in capabilities.json; <config dir>/capabilities.json overrides them per AI (merged, yours wins).
//
// Honest limit: other vendors' connectors, plugins and skills (ChatGPT connectors, Claude MCP servers and skills, Gemini extensions) only run
// INSIDE that vendor's product. Machine God cannot borrow them; it delegates the whole task to the AI that has them.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
export const CAPABILITIES = ["web_search", "images", "code_exec", "long_context", "local_private", "connectors"];
export const TASKS = ["web_search", "images", "code_exec", "long_context", "private", "connectors", "code", "general"];
const TASK_CAP = { web_search: "web_search", images: "images", code_exec: "code_exec", long_context: "long_context", private: "local_private", connectors: "connectors" };

export const capabilitiesOverrideFile = (configDir) => path.join(configDir, "capabilities.json");

function readJson(file) {
  try {
    const j = JSON.parse(fs.readFileSync(file, "utf8"));
    return j && typeof j === "object" ? j : {};
  } catch {
    return {};
  }
}

/** -> { priority: [ids], ais: { id: { label, capabilities, skills, notes } } } (defaults merged with the user's file) */
export function loadCapabilities(configDir) {
  const base = readJson(path.join(here, "capabilities.json"));
  const mine = configDir ? readJson(capabilitiesOverrideFile(configDir)) : {};
  const ais = {};
  for (const id of new Set([...Object.keys(base.ais || {}), ...Object.keys(mine.ais || {})])) {
    const b = base.ais?.[id] || {};
    const m = mine.ais?.[id] || {};
    ais[id] = {
      label: m.label || b.label || id,
      capabilities: { ...Object.fromEntries(CAPABILITIES.map((c) => [c, false])), ...(b.capabilities || {}), ...(m.capabilities || {}) },
      skills: { general: 1, code: 1, writing: 1, reasoning: 1, ...(b.skills || {}), ...(m.skills || {}) },
      notes: m.notes || b.notes || "",
    };
  }
  const priority = Array.isArray(mine.priority) ? mine.priority : Array.isArray(base.priority) ? base.priority : [];
  return { priority, ais };
}

// ---------- classification (keywords, English and German) ----------
const RULES = [
  ["images", /\b(draw|paint|sketch|illustrat\w*|render|logo|icon|wallpaper|generate (?:an? )?(?:image|picture|photo)|create (?:an? )?(?:image|picture|photo)|image of|picture of|zeichne|male mir|erzeuge ein bild|erstelle ein bild|bild von)\b/i],
  ["web_search", /\b(latest|news|today|tonight|this week|right now|currently|current (?:price|version|weather|status)|search the web|google it|look up online|browse|stock price|weather|exchange rate|who won|release date|aktuell\w*|heute|neueste\w*|nachrichten|wetter|suche im (?:web|internet)|recherchiere)\b|https?:\/\/\S+/i],
  ["code_exec", /\b(run (?:this|the|my) (?:code|script|program)|execute (?:this|the|my)|plot|chart|graph this|analy[sz]e (?:this )?(?:csv|spreadsheet|excel|data ?set)|crunch|simulate|benchmark|f(?:ü|ue)hre (?:das|den|diesen) (?:code|skript|script) aus|diagramm)\b/i],
  ["private", /\b(private|confidential|offline|on[- ]device|keep (?:this )?(?:local|on my machine)|do not send|don't send|not leave|vertraulich|geheim\w*|nur lokal|lokal ausf(?:ü|ue)hren)\b/i],
  ["connectors", /\b(my (?:e-?mails?|inbox|calendar|drive|docs?|notion|slack|repos?|issues|pull requests?|files)|gmail|google drive|calendar|notion|slack|jira|github (?:repo|issue)|meine (?:mails?|e-?mails?|termine|dateien|repos?)|mein kalender)\b/i],
  ["code", /```|\b(bug|stack ?trace|traceback|compile\w*|refactor\w*|function|regex|sql query|unit test|typescript|javascript|python|rust|golang|java|c\+\+|segfault|implement\w*|funktion|programmier\w*)\b/i],
];
export const LONG_CHARS = 24_000;

/** -> { tasks: [...], hint, reasons } ; tasks always contains at least "general" or "code". hint: auto | <task> | ai:<id> | <ai id> */
export function classify(prompt, hint = "auto", knownIds = []) {
  const text = String(prompt || "");
  const h = String(hint || "auto").trim().toLowerCase();
  const reasons = [];
  let force = null;
  const tasks = new Set();
  if (h.startsWith("ai:") || knownIds.includes(h)) {
    force = h.replace(/^ai:/, "");
    reasons.push(`you chose ${force}`);
  } else if (TASKS.includes(h) && h !== "general") {
    tasks.add(h);
    reasons.push(`hint: ${h}`);
  } else if (h !== "auto" && h !== "general" && h !== "") {
    reasons.push(`unknown hint "${h.slice(0, 30)}" ignored`);
  }
  if (!force) {
    for (const [task, re] of RULES) {
      const m = re.exec(text);
      if (m) {
        tasks.add(task);
        reasons.push(`${task}: "${m[0].slice(0, 30)}"`);
      }
    }
    if (text.length > LONG_CHARS) {
      tasks.add("long_context");
      reasons.push(`long_context: ${text.length} chars`);
    }
    if (!tasks.size) tasks.add("general");
  }
  return { tasks: [...tasks], force, reasons };
}

/**
 * Rank connected AIs for a classified request. -> [{ id, score, missing: [capabilities it lacks], why }] best first. Empty list = nobody qualifies (private task, no local model).
 * opts: { exclude: [ids], connected: [ids] }
 */
export function rank(caps, connected, cls, { exclude = [] } = {}) {
  let ids = connected.filter((id) => !exclude.includes(id));
  if (cls.force) {
    return connected.includes(cls.force) ? [{ id: cls.force, score: 1000, missing: [], why: "chosen explicitly" }] : [];
  }
  if (cls.tasks.includes("private")) ids = ids.filter((id) => caps.ais[id]?.capabilities.local_private);
  const n = caps.priority.length;
  const out = ids.map((id) => {
    const a = caps.ais[id] || { capabilities: {}, skills: {} };
    let score = 0;
    const missing = [];
    const why = [];
    for (const t of cls.tasks) {
      const cap = TASK_CAP[t];
      if (cap) {
        if (a.capabilities[cap]) {
          score += 10;
          why.push(`has ${cap}`);
        } else {
          score -= 10;
          missing.push(cap);
        }
      } else score += a.skills?.[t] ?? a.skills?.general ?? 0;
    }
    score += a.skills?.general ?? 0;
    const idx = caps.priority.indexOf(id);
    score += (idx < 0 ? 0 : n - idx) * 0.1;
    return { id, score: Math.round(score * 100) / 100, missing, why: why.join(", ") || "general quality and priority" };
  });
  return out.sort((a, b) => b.score - a.score || a.id.localeCompare(b.id));
}

/** One-liner for status output. */
export const describeCaps = (a) => CAPABILITIES.filter((c) => a.capabilities[c]).join(", ") || "text only";
