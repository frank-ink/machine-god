// SQLite persistence + operations. Every state change is written to the events table.
import { Database } from "bun:sqlite";
import { mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import * as M from "./model.ts";
import type { Interest, Rng } from "./model.ts";

export function dataDir(): string {
  if (process.env.MG_DATA_DIR) return process.env.MG_DATA_DIR;
  if (process.platform === "darwin") return join(homedir(), "Library", "Application Support", "machine-god");
  if (process.platform === "win32") return join(process.env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "machine-god");
  return join(process.env.XDG_DATA_HOME || join(homedir(), ".local", "share"), "machine-god");
}

export function open(path = join(dataDir(), "interest.db")): Database {
  if (path !== ":memory:") mkdirSync(dirname(path), { recursive: true });
  const db = new Database(path);
  db.run(`CREATE TABLE IF NOT EXISTS interests(key TEXT PRIMARY KEY, topic TEXT, w REAL, n REAL, b REAL,
    visits INTEGER, last_visit INTEGER, origin TEXT, status TEXT, ts INTEGER)`);
  db.run(`CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT, topic TEXT, delta TEXT)`);
  return db;
}

const r3 = (x: number) => Math.round(x * 1000) / 1000;
const mv = (a: number, b: number) => [r3(a), r3(b)];

export class Store {
  constructor(public db: Database, public now: () => number = Date.now) {}

  private log(kind: string, topic: string, delta: object = {}) {
    this.db.run("INSERT INTO events(ts,kind,topic,delta) VALUES(?,?,?,?)", [this.now(), kind, topic, JSON.stringify(delta)]);
  }
  private save(i: Interest) {
    this.db.run(`INSERT OR REPLACE INTO interests VALUES(?,?,?,?,?,?,?,?,?,?)`,
      [i.key, i.topic, i.w, i.n, i.b, i.visits, i.last_visit, i.origin, i.status, i.ts]);
  }
  private get(key: string): Interest | undefined {
    return this.db.query("SELECT * FROM interests WHERE key=?").get(key) as Interest | undefined;
  }

  /** Load all interests, applying time decay (persisted). Logs only dormancy transitions. */
  all(): Interest[] {
    const now = this.now();
    const rows = this.db.query("SELECT * FROM interests").all() as Interest[];
    return rows.map((r) => {
      if (now <= r.ts) return r;
      const d = M.decay(r, now);
      this.save(d);
      if (r.status === "active" && d.status === "dormant") this.log("dormant", d.topic, { reason: "decay", w: mv(r.w, d.w) });
      return d;
    });
  }
  sorted(): Interest[] { return this.all().sort((a, b) => M.score(b) - M.score(a)); }

  seed(topics: string[]) {
    this.all();
    for (const t of topics) {
      const ex = this.get(M.normKey(t));
      if (!t.trim()) continue;
      if (!ex) {
        const i = M.newInterest(t, "seed", this.now(), M.C.SEED_W, M.C.SEED_N);
        this.save(i); this.log("seed", i.topic, { w: i.w, n: i.n });
      } else if (ex.status === "dormant" || ex.w < M.C.SEED_W) {
        const i = { ...ex, w: Math.max(ex.w, M.C.SEED_W), status: "active" as const };
        this.save(i); this.log(ex.status === "dormant" ? "revive" : "seed", i.topic, { w: mv(ex.w, i.w) });
      }
    }
    this.capped();
  }

  private capped() {
    const all = this.db.query("SELECT * FROM interests").all() as Interest[];
    for (const k of M.overCap(all)) {
      const i = this.get(k)!;
      this.save({ ...i, status: "dormant" });
      this.log("dormant", i.topic, { reason: "cap" });
    }
  }

  pick(rng: Rng): M.Choice | null { return M.choose(this.all(), rng); }

  /** Apply reward to a topic (creates it with origin `user` if new and origin given). */
  private reward(topic: string, r: number, kind: string, newOrigin?: "user"): Interest | null {
    this.all();
    let i = this.get(M.normKey(topic)) ?? null;
    if (!i) {
      if (!newOrigin) return null;
      i = M.newInterest(topic, newOrigin, this.now(), 0, 1);
    }
    const u = M.applyReward(i, r, this.now());
    this.save(u);
    this.log(kind, u.topic, { reward: r3(r), w: mv(i.w, u.w), n: mv(i.n, u.n), b: mv(i.b, u.b), visits: u.visits });
    if (i.status === "dormant" && u.status === "active") this.log("revive", u.topic, { w: u.w });
    if (i.status === "active" && u.status === "dormant") this.log("dormant", u.topic, { reason: "reward" });
    return u;
  }

  round(topic: string, r: number, subtopics: string[]) {
    const u = this.reward(topic, r, "round");
    const added: string[] = [];
    for (const s of subtopics) {
      const d = M.discovered(s, r, this.now());
      if (!d.key) continue;
      if (this.get(d.key)) { this.log("rediscover", d.topic, { from: topic }); continue; }
      this.save(d); added.push(d.topic);
      this.log("discover", d.topic, { from: topic, w: r3(d.w), n: 1 });
    }
    this.capped();
    return { updated: u, added };
  }

  feedback(topic: string, liked: boolean) {
    const u = this.reward(topic, liked ? 1 : 0, liked ? "like" : "dislike", "user");
    this.capped();
    return u;
  }

  history(n = 30) {
    return (this.db.query("SELECT * FROM events ORDER BY id DESC LIMIT ?").all(n) as any[]).reverse();
  }
  reset() { this.db.run("DELETE FROM interests"); this.db.run("DELETE FROM events"); }
}
