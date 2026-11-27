#!/usr/bin/env python3
"""RETRIEVAL_FORENSICS_V1: classify every miss of the 200 f3 known-item probes. Read-only on unified.db.
Classes: MISSING_DOCUMENT (expected source row has no mem_doc), MISSING_INDEX_ENTRY (doc not in mem_fts),
NOT_CANONICAL (expected doc is a dup, canonical is another id), RANK_DISPLACEMENT (found at rank 6..50),
DUPLICATE_COMPETITION (a doc ranked above shares canon_id or identical subject with target), NOT_RETRIEVED (>50 or no match).
Writes per-probe JSONL + summary JSON next to this file."""
import sqlite3, json, time, os, collections, sys
DB = os.path.expanduser('~/.local/share/agentzero/unified.db')
OUT = os.path.dirname(os.path.abspath(__file__))
c = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=30)
probes = c.execute('select probe_id, query, expect_source, expect_key from f3_probe order by probe_id').fetchall()
rows, cls = [], collections.Counter()
h1 = h5 = rr5 = rr10 = 0.0
for pid, q, src, key in probes:
    terms = ' OR '.join('"%s"' % w.replace('"', '') for w in q.split())
    t0 = time.perf_counter()
    ids = [r[0] for r in c.execute('select rowid from mem_fts where mem_fts match ? order by bm25(mem_fts) limit 50', (terms,))]
    ms = (time.perf_counter() - t0) * 1000
    d = c.execute('select doc_id, canon_id from mem_doc where source_id=? and source_key=?', (src, key)).fetchone()
    rank = 0; klass = 'HIT1'
    if not d:
        klass = 'MISSING_DOCUMENT'
    else:
        doc, canon = d
        in_fts = c.execute('select 1 from mem_fts where rowid=?', (doc,)).fetchone() is not None
        if doc in ids:
            rank = ids.index(doc) + 1
        elif canon is not None and canon != doc and canon in ids:
            rank = ids.index(canon) + 1
        if rank == 1:
            klass = 'HIT1'
        elif 1 < rank <= 5:
            klass = 'HIT2_5'
        elif not in_fts and (canon is None or canon == doc):
            klass = 'MISSING_INDEX_ENTRY'
        elif not in_fts:
            klass = 'NOT_CANONICAL'
        elif 5 < rank <= 50:
            klass = 'RANK_DISPLACEMENT'
        else:
            klass = 'NOT_RETRIEVED'
        if klass in ('HIT2_5', 'RANK_DISPLACEMENT') and canon is not None:
            above = ids[:rank - 1]
            if above:
                qm = ','.join('?' * len(above))
                dup = c.execute(f'select count(*) from mem_doc where doc_id in ({qm}) and canon_id=?', (*above, canon)).fetchone()[0]
                if dup:
                    klass += '+DUPLICATE_COMPETITION'
    if rank == 1: h1 += 1
    if 1 <= rank <= 5: h5 += 1; rr5 += 1 / rank
    if 1 <= rank <= 10: rr10 += 1 / rank
    cls[klass] += 1
    rows.append({'probe_id': pid, 'rank': rank, 'class': klass, 'ms': round(ms, 1)})
n = len(probes)
summ = {'n': n, 'hit_at_1': round(h1 / n, 3), 'hit_at_5': round(h5 / n, 3), 'mrr_at_5': round(rr5 / n, 4), 'mrr_at_10': round(rr10 / n, 4),
        'classes': dict(cls.most_common()), 'ts': time.strftime('%Y-%m-%dT%H:%M:%S'), 'db_mtime': os.path.getmtime(DB)}
with open(os.path.join(OUT, 'forensics_v1_probes.jsonl'), 'w') as f:
    for r in rows: f.write(json.dumps(r) + '\n')
json.dump(summ, open(os.path.join(OUT, 'forensics_v1_summary.json'), 'w'), indent=1)
print(json.dumps(summ))
