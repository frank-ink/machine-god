// Registers the reflection hooks in the user's Claude Code settings (claude-rs loads user settings, the install archive carries no plugins/).
// Only called by `improve enable` / `improve disable`, i.e. after the user's yes. A backup is written before every change.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { installDir } from "./core.ts";

const EVENTS: [string, string][] = [["PostToolUse", "post"], ["PostToolUseFailure", "post"], ["Stop", "stop"], ["UserPromptSubmit", "prompt"]];
const MARK = /reflect[\\/]hook\.ts"?\s+(post|stop|prompt)\s*$/;

export const settingsFile = (env: Record<string, string | undefined> = process.env) =>
  path.join(env.CLAUDE_CONFIG_DIR || path.join(env.HOME || env.USERPROFILE || os.homedir(), ".claude"), "settings.json");

type Entry = { matcher?: string; hooks: { type: string; command: string; timeout?: number }[] };
const ours = (e: Entry) => (e?.hooks ?? []).some((h) => MARK.test(String(h?.command ?? "")));

function load(file: string): Record<string, any> {
  if (!fs.existsSync(file)) return {};
  const j = JSON.parse(fs.readFileSync(file, "utf8")); // a broken settings.json throws: we never overwrite what we cannot read
  if (!j || typeof j !== "object" || Array.isArray(j)) throw new Error(`${file} is not a JSON object`);
  return j;
}

let seq = 0;
function save(file: string, j: Record<string, any>) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  if (fs.existsSync(file)) fs.copyFileSync(file, `${file}.machine-god-${Date.now()}-${++seq}.bak`); // never overwrite an older backup
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, JSON.stringify(j, null, 2) + "\n");
  fs.renameSync(tmp, file);
}

/** Removes our hook entries; returns how many were removed. Other hooks stay untouched. */
export function removeHooks(file = settingsFile()): number {
  if (!fs.existsSync(file)) return 0;
  const j = load(file);
  let n = 0;
  for (const [ev] of EVENTS) {
    const list: Entry[] = Array.isArray(j.hooks?.[ev]) ? j.hooks[ev] : [];
    const keep = list.filter((e) => !ours(e));
    n += list.length - keep.length;
    if (list.length !== keep.length) { if (keep.length) j.hooks[ev] = keep; else delete j.hooks[ev]; }
  }
  if (n) { if (j.hooks && !Object.keys(j.hooks).length) delete j.hooks; save(file, j); }
  return n;
}

/** Idempotent: replaces older entries of ours (e.g. after a move of the install dir), then adds one per event. */
export function installHooks(file = settingsFile(), bun = process.execPath, root = installDir()): number {
  const j = load(file);
  const hook = path.join(root, "reflect", "hook.ts");
  j.hooks = j.hooks && typeof j.hooks === "object" ? j.hooks : {};
  for (const [ev, mode] of EVENTS) {
    const list: Entry[] = (Array.isArray(j.hooks[ev]) ? j.hooks[ev] : []).filter((e: Entry) => !ours(e));
    const entry: Entry = { hooks: [{ type: "command", command: `"${bun}" "${hook}" ${mode}`, timeout: 5 }] };
    if (ev.startsWith("PostToolUse")) entry.matcher = "*";
    j.hooks[ev] = [...list, entry];
  }
  save(file, j);
  return EVENTS.length;
}
