import { describe, expect, test } from "bun:test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import * as M from "./model.ts";
import { parseResult, dry, research, fuse, BACKENDS } from "./research.ts";
import { writeFileSync } from "node:fs";
import { Store, open } from "./store.ts";
import { runRounds } from "./cli.ts";

const DAY = 86_400_000;
const mk = (o: Partial<M.Interest> = {}): M.Interest => ({ ...M.newInterest("Foo", "seed", 0, 0.5, 0.5), ...o });
let clock = 1_000_000;
const store = () => { clock = 1_000_000; return new Store(open(":memory:"), () => clock); };

describe("decay", () => {
  test("w with T=14d, b with T=2d", () => {
    const d = M.decay(mk({ w: 0.8, b: 0.6 }), 14 * DAY);
    expect(d.w).toBeCloseTo(0.8 * Math.exp(-1), 6);
    expect(M.decay(mk({ b: 0.6 }), 2 * DAY).b).toBeCloseTo(0.6 * Math.exp(-1), 6);
  });
  test("w < 0.05 -> dormant, kept", () => {
    const d = M.decay(mk({ w: 0.5 }), 40 * DAY);
    expect(d.w).toBeLessThan(0.05);
    expect(d.status).toBe("dormant");
  });
  test("zero dt is identity; no double decay on reload", () => {
    const s = store(); s.seed(["a"]);
    clock += 7 * DAY;
    const w1 = s.all()[0].w; const w2 = s.all()[0].w;
    expect(w1).toBeCloseTo(0.5 * Math.exp(-0.5), 6);
    expect(w2).toBe(w1);
  });
});

describe("choice", () => {
  const items = [mk({ key: "a", topic: "a", w: 0.8 }), mk({ key: "b", topic: "b", w: 0.5 }), mk({ key: "c", topic: "c", w: 0.2 })];
  test("1000 picks follow softmax (eps=0)", () => {
    const rng = M.mulberry32(42), cnt: Record<string, number> = { a: 0, b: 0, c: 0 };
    for (let k = 0; k < 1000; k++) cnt[M.choose(items, rng, 0)!.item.key]++;
    const p = M.softmax(items.map(M.score));
    expect(p[0]).toBeGreaterThan(0.6); // sanity: top topic dominates
    expect(Math.abs(cnt.a / 1000 - p[0])).toBeLessThan(0.05);
    expect(Math.abs(cnt.c / 1000 - p[2])).toBeLessThan(0.05);
  });
  test("exploration picks unvisited discovered ~eps of the time", () => {
    const d = mk({ key: "d", topic: "d", w: 0.15, n: 1, origin: "discovered" });
    const rng = M.mulberry32(7); let hit = 0, explored = 0;
    for (let k = 0; k < 1000; k++) { const c = M.choose([...items, d], rng)!; if (c.item.key === "d") hit++; if (c.explored) explored++; }
    expect(explored / 1000).toBeGreaterThan(0.11);
    expect(explored / 1000).toBeLessThan(0.19);
    expect(hit).toBeGreaterThanOrEqual(explored);
  });
  test("no active -> null; dormant never picked", () => {
    expect(M.choose([mk({ status: "dormant" })], Math.random)).toBeNull();
  });
});

describe("update rule", () => {
  test("w, b, n, visits", () => {
    const u = M.applyReward(mk({ w: 0.5, n: 1, b: 0.2 }), 1, 99);
    expect(u.w).toBeCloseTo(0.5 + 0.3 * 0.5, 9);
    expect(u.b).toBeCloseTo(0.2 + 0.35 * 0.8, 9);
    expect(u.n).toBeCloseTo(0.6, 9);
    expect(u.visits).toBe(1); expect(u.last_visit).toBe(99);
  });
});

describe("discovery", () => {
  test("new interest w=0.15+0.2r n=1, dedupe by normalized key", () => {
    const s = store(); s.seed(["Rust"]);
    const r = s.round("Rust", 0.5, ["  Borrow  Checker ", "borrow checker", "RUST"]);
    expect(r.added).toEqual(["Borrow Checker"]);
    const d = s.all().find((i) => i.key === "borrow checker")!;
    expect(d.w).toBeCloseTo(0.25, 9); expect(d.n).toBe(1); expect(d.origin).toBe("discovered");
    expect(s.all().length).toBe(2);
  });
  test("cap 40 active: lowest score -> dormant (kept)", () => {
    const s = store(); s.seed(["seed"]);
    s.round("seed", 1, Array.from({ length: 50 }, (_, k) => `topic ${k}`));
    const all = s.all();
    expect(all.length).toBe(51);
    expect(all.filter((i) => i.status === "active").length).toBe(40);
    expect(s.history(200).some((e) => e.kind === "dormant" && e.delta.includes("cap"))).toBe(true);
  });
});

describe("dormant / revive / feedback", () => {
  test("decay -> dormant, like revives", () => {
    const s = store(); s.seed(["a", "b"]);
    clock += 40 * DAY;
    expect(s.all().every((i) => i.status === "dormant")).toBe(true);
    expect(s.pick(Math.random)).toBeNull();
    s.feedback("a", true);
    const a = s.all().find((i) => i.key === "a")!;
    expect(a.status).toBe("active");
    expect(s.history(50).some((e) => e.kind === "revive")).toBe(true);
  });
  test("like r=1 / dislike r=0; new topic origin user", () => {
    const s = store(); s.seed(["a"]);
    s.feedback("a", true); expect(s.all()[0].w).toBeCloseTo(0.65, 9);
    s.feedback("a", false); expect(s.all()[0].w).toBeCloseTo(0.455, 9);
    s.feedback("Brand New", true);
    const n = s.all().find((i) => i.key === "brand new")!;
    expect(n.origin).toBe("user"); expect(n.w).toBeCloseTo(0.3, 9);
  });
  test("every change is logged", () => {
    const s = store(); s.seed(["a"]); s.round("a", 0.4, ["x"]); s.feedback("a", false);
    expect(s.history(50).map((e) => e.kind)).toEqual(["seed", "round", "discover", "dislike"]);
  });
});

describe("parse", () => {
  test("good block", () => {
    const r = parseResult('note text\n```json\n{"reward":0.8,"subtopics":["a","b","c","d"]}\n```');
    expect(r.reward).toBe(0.8); expect(r.subtopics).toEqual(["a", "b", "c"]); expect(r.note).toBe("note text");
  });
  test("malformed -> 0.3, none", () => {
    for (const t of ["no json", '{"reward":', '{"reward":"x"}', ""]) {
      const r = parseResult(t); expect(r.reward).toBe(0.3); expect(r.subtopics).toEqual([]);
    }
  });
  test("reward clamped, dry deterministic", () => {
    expect(parseResult('{"reward":7}').reward).toBe(1);
    expect(dry("x")).toEqual(dry("x"));
  });
});

describe("end to end (dry, 20 rounds)", () => {
  test("interests shift", async () => {
    const s = store();
    const seeds = ["quantum biology", "medieval cartography", "bread chemistry"];
    s.seed(seeds);
    const before = s.sorted().map((i) => i.key);
    const lines: string[] = [];
    const dir = mkdtempSync(join(tmpdir(), "mg-int-"));
    expect(await runRounds(s, "dry", 20, M.mulberry32(1), dir, (l) => lines.push(l))).toBe(0);
    const after = s.sorted();
    const discoveredActive = after.filter((i) => i.origin === "discovered" && i.status === "active");
    expect(discoveredActive.length).toBeGreaterThan(0);
    expect(after[0].key !== before[0] || discoveredActive.length > 0).toBe(true);
    expect(s.history(500).filter((e) => e.kind === "round").length).toBe(20);
    console.log(lines.join("\n"));
  });
  test("no seeds -> says how to seed, invents nothing", async () => {
    const s = store(); const out: string[] = [];
    expect(await runRounds(s, "dry", 3, Math.random, tmpdir(), (l) => out.push(l))).toBe(1);
    expect(out[0]).toContain("seed"); expect(s.all().length).toBe(0);
  });
});

describe("fusion backends (mock HTTP servers, no real keys)", () => {
  const answer = (reward: number, sub: string) => `A short note.\n{"reward": ${reward}, "subtopics": ["${sub}", "shared"]}`;
  const servers: any[] = [];
  const mock = (fn: (req: Request) => Response) => { const s = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch: fn }); servers.push(s); return `http://127.0.0.1:${s.port}`; };
  const setup = (connected: string[]) => {
    const d = mkdtempSync(join(tmpdir(), "mg-int-fu-"));
    writeFileSync(join(d, "ais.json"), JSON.stringify({ version: 1, connected: Object.fromEntries(connected.map((c) => [c, {}])) }));
    writeFileSync(join(d, "keys.json"), JSON.stringify({ gemini: { key: "MOCKKEY-not-a-real-key-123" } }));
    return d;
  };
  const env = (d: string, extra: Record<string, string>) => { for (const k of Object.keys(extra)) process.env[k] = extra[k]; process.env.MG_CONFIG_DIR = d; process.env.MG_DATA_DIR = d; };
  test("backends list", () => expect(BACKENDS).toEqual(["claude", "chatgpt", "gemini", "ollama", "fusion", "dry"]));
  test("gemini backend uses the stored key in a header, not the URL", async () => {
    let seen: any = null;
    const gem = mock((req) => { seen = { url: req.url, key: req.headers.get("x-goog-api-key") }; return Response.json({ candidates: [{ content: { parts: [{ text: answer(0.9, "g-sub") }] } }] }); });
    env(setup(["gemini"]), { MG_FUSION_BASE_GEMINI: gem });
    const r = await research("deep sea", "gemini");
    expect(r.reward).toBe(0.9); expect(r.subtopics).toEqual(["g-sub", "shared"]);
    expect(seen.key).toBe("MOCKKEY-not-a-real-key-123"); expect(seen.url).not.toContain("MOCKKEY");
  });
  test("ollama backend talks to the local server only", async () => {
    const ol = mock((req) => req.url.endsWith("/api/tags") ? Response.json({ models: [{ name: "m1" }] }) : Response.json({ message: { content: answer(0.4, "o-sub") } }));
    env(setup([]), { MG_OLLAMA_URL: ol, MG_LMSTUDIO_URL: "http://127.0.0.1:1" });
    const r = await research("jazz", "ollama");
    expect(r.reward).toBe(0.4); expect(r.subtopics[0]).toBe("o-sub");
  });
  test("fusion merges all connected AIs: mean reward, labelled notes, distinct subtopics; one failure is tolerated", async () => {
    const gem = mock(() => Response.json({ candidates: [{ content: { parts: [{ text: answer(0.8, "g-sub") }] } }] }));
    const ol = mock((req) => req.url.endsWith("/api/tags") ? Response.json({ models: [{ name: "m1" }] }) : Response.json({ message: { content: answer(0.4, "o-sub") } }));
    env(setup(["gemini", "local", "grok"]), { MG_FUSION_BASE_GEMINI: gem, MG_OLLAMA_URL: ol, MG_LMSTUDIO_URL: "http://127.0.0.1:1" }); // grok has no key -> fails
    const r = await fuse("p");
    expect(r.reward).toBeCloseTo(0.6, 9);
    expect(r.note).toContain("## gemini"); expect(r.note).toContain("## local");
    expect(r.subtopics).toEqual(["g-sub", "shared", "o-sub"]);
  });
  test("fusion with nothing connected says so", async () => {
    env(setup([]), {});
    await expect(research("x", "fusion")).rejects.toThrow(/no AIs connected/);
  });
  test("cleanup", () => { for (const s of servers) s.stop(true); });
});
