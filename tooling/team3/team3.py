#!/usr/bin/env python3
"""team3.py [MAX_ROUNDS] -- external team 3: leader persona 'Gabriel' (mathematician, GRF) + 5 coding agents.
Each round: arXiv digest -> leader reads all teams -> impulse + 5 tasks -> coders -> leader bundles -> out/buendel_latest.md.
Runs until vereinigung/out/v_final/GRIDv1.md exists or MAX_ROUNDS. NVIDIA free only (call() from ../team/team.py)."""
import concurrent.futures as cf, json, os, re, subprocess, sys, time
from pathlib import Path

H = Path(__file__).resolve().parent
K = H.parent
os.environ["TEAM_DIR"] = str(H)
g = {"__file__": str(K / "team" / "team.py"), "__name__": "team_core"}
exec((K / "team" / "team.py").read_text().split("\nHEAD = ")[0], g)
BASE_PRE, call = g["PRE"], g["call"]
CFG = json.loads((H / "team.json").read_text())
LEAD, CODERS = CFG[0], CFG[1:]
persona_txt = lambda: (H / "persona_kopf.md").read_text() + "\n\nPROFIL:\n" + (H / "gabriel_profil.md").read_text()
OUT = H / "out"
log = lambda s: print(f"[{time.strftime('%H:%M:%S')}] {s}", flush=True)


def ask(m, prompt, persona=False):
    g["PRE"] = BASE_PRE + ("\n\n" + persona_txt() if persona else "")
    txt, meta = call(1, m["model"], prompt)
    if not txt and m.get("fallback"):
        txt, meta = call(2, m["fallback"], prompt)
    g["PRE"] = BASE_PRE
    log(meta)
    return txt or ""


def lage():
    parts = []
    for name, d in (("TEAM 1 GRID/kernel", "team"), ("TEAM 2 research", "team2"), ("VEREINIGUNG GRIDv1", "vereinigung")):
        o = K / d / "out"
        for ph in ("v_final", "final", "v_entwurf", "entwurf", "review", "v_review", "zerlegen"):
            fs = sorted((o / ph).glob("*.md")) if (o / ph).exists() else []
            if fs:
                body = "\n".join(f"--- {f.stem} ---\n{f.read_text()[:6000]}" for f in fs)[:16000]
                parts.append(f"=== {name}: newest phase '{ph}' ({len(fs)} files) ===\n{body}")
                break
        else:
            parts.append(f"=== {name}: no output yet ===")
    return "\n\n".join(parts)


def runde(r):
    subprocess.run([sys.executable, "-I", str(H / "arxiv_feed.py")], timeout=300)
    arx = (H / "arxiv" / "latest.md").read_text()[:20000]
    prev = (OUT / "buendel_latest.md").read_text()[:8000] if (OUT / "buendel_latest.md").exists() else "none"
    imp = ask(LEAD, f"RUNDE {r}.\n\nZIEL:\n{(H/'ziel.md').read_text()}\n\nDEIN LETZTES BUENDEL:\n{prev}\n\nARXIV DIGEST:\n{arx}\n\nAKTUELLE LAGE DER TEAMS:\n{lage()}\n\n"
              "AUFGABE: (1) Deine Meinung zu jedem Team (Team 1, Team 2, Vereinigung): was richtig, was falsch, was fehlt - in GRF/ClayCode. "
              "(2) Was aus dem arXiv-Digest relevant ist und warum (GRF-Linse). (3) Genau 5 Auftraege fuer deine Coder, je eine Zeile 'TASK_1: ...' bis 'TASK_5: ...' "
              "(konkret: Code-Skelett Rust/TS/Python, ClayCode-Modul, Beweisskizze, Test). Schreib wie du (Gabriel).", persona=True)
    (OUT / f"r{r}_impuls.md").write_text(imp)
    tasks = re.findall(r"TASK_(\d):\s*(.+)", imp) or [(str(i + 1), "Arbeite den Impuls unten konkret aus.") for i in range(5)]
    def work(i_t):
        i, (n, t) = i_t
        c = CODERS[i % len(CODERS)]
        return c["name"], ask(c, f"Du bist {c['name']} in Team 3 (Leiter: 'Gabriel', Mathematiker, GRF). Denke in GRF, antworte in ClayCode + Code.\n\nLEITER-IMPULS:\n{imp}\n\nDEIN AUFTRAG (TASK_{n}): {t}\n\nLiefere: ClayCode-Block, lauffaehiges Code-Skelett, Test/Akzeptanzkriterium, offene UNKNOWNs. Max 1500 Woerter.")
    with cf.ThreadPoolExecutor(5) as ex:
        res = list(ex.map(work, enumerate(tasks[:5])))
    work_txt = "\n\n".join(f"### {n}\n{t}" for n, t in res)
    (OUT / f"r{r}_coder.md").write_text(work_txt)
    b = ask(LEAD, f"DEIN IMPULS:\n{imp}\n\nERGEBNISSE DEINER CODER:\n{work_txt}\n\nAUFGABE: Buendle fuer die anderen Teams. Abschnitte: '## An Team 1', '## An Team 2', '## An Vereinigung GRIDv1', "
            "'## Gabriels Meinung (Persona)', '## Code/ClayCode-Beitraege' (nur das Beste, geprueft). Kurz, konkret, jede Aussage mit Klasse MEASURED/HYPOTHESIS/UNKNOWN.", persona=True)
    head = f"<!-- Team 3 Buendel Runde {r}, {time.strftime('%Y-%m-%d %H:%M')}; Leiter-Persona 'Gabriel' (GRF als 99% korrekt gesetzt) -> fuer andere Teams Klasse HYPOTHESIS -->\n"
    (OUT / f"r{r}_buendel.md").write_text(head + b)
    (OUT / "buendel_latest.md").write_text(head + b)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    for r in range(start, int(sys.argv[1]) + 1 if len(sys.argv) > 1 else 9):
        t0 = time.time(); log(f"Runde {r} start"); runde(r); log(f"Runde {r} fertig")
        if (K / "vereinigung" / "out" / "v_final" / "GRIDv1.md").exists():
            log("GRIDv1 steht -> letzte Runde gelaufen"); break
        time.sleep(max(0, 1800 - (time.time() - t0)))
