#!/usr/bin/env python3
"""H1 falsification: replay the CURRENT f3_probe set (from the live laptop DB) against historical unified.db snapshots.
Read-only. Per snapshot: hit@1, hit@5, MRR@5, dead probe words (match nothing in that snapshot's mem_fts)."""
import sqlite3, sys, os, json
LIVE = os.path.expanduser('~/.local/share/agentzero/unified.db')
probes = sqlite3.connect(f'file:{LIVE}?mode=ro', uri=True).execute('select probe_id,query,expect_source,expect_key from f3_probe order by probe_id').fetchall()
for path in sys.argv[1:]:
    try:
        c = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=30)
        have = {r[0] for r in c.execute("select name from sqlite_master")}
        if not {'mem_fts', 'mem_doc'} <= have:
            print(json.dumps({'snap': path, 'skip': 'no mem_fts/mem_doc'})); continue
        h1 = h5 = rr = dead = probes_dead = nodoc = 0
        for pid, q, src, key in probes:
            d = c.execute('select doc_id from mem_doc where source_id=? and source_key=?', (src, key)).fetchone()
            pd = 0
            for w in q.split():
                if c.execute('select count(*) from (select 1 from mem_fts where mem_fts match ? limit 1)', ('"%s"' % w.replace('"', ''),)).fetchone()[0] == 0:
                    dead += 1; pd = 1
            probes_dead += pd
            if not d: nodoc += 1; continue
            ids = [r[0] for r in c.execute('select rowid from mem_fts where mem_fts match ? order by bm25(mem_fts) limit 5', (' OR '.join('"%s"' % w.replace('"', '') for w in q.split()),))]
            if d[0] in ids:
                p = ids.index(d[0]); h5 += 1; rr += 1 / (p + 1); h1 += p == 0
        n = len(probes); ndocs = c.execute('select count(*) from mem_doc').fetchone()[0]
        print(json.dumps({'snap': path, 'mtime': os.path.getmtime(path), 'mem_doc': ndocs, 'nodoc': nodoc, 'hit1': round(h1/n, 3), 'hit5': round(h5/n, 3), 'mrr5': round(rr/n, 4), 'dead_words': dead, 'probes_with_dead': probes_dead}))
    except Exception as e:
        print(json.dumps({'snap': path, 'err': str(e)[:120]}))
