"""Example retrievers: retrieve(conn, query, k) -> list of doc ids (best first). Stdlib only."""
import re

_WORD = re.compile(r"\w+", re.UNICODE)
_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
SQL = "SELECT rowid FROM mem_fts WHERE mem_fts MATCH ? ORDER BY bm25(mem_fts), rowid LIMIT ?"


def words(query):
    return _WORD.findall(query)


def match_expr(ws):
    """Each word in double quotes, OR-joined (embedded quotes cannot occur: \\w+ only)."""
    return " OR ".join('"%s"' % w for w in ws)


def fts_bm25_or(conn, query, k):
    ws = words(query)
    return [r[0] for r in conn.execute(SQL, (match_expr(ws), k))] if ws else []


def fts_bm25_or_folded(conn, query, k):
    """Match union of raw query words and folded words (deduplicated, FTS5 OR query)."""
    raw_ws = words(query)
    folded_ws = words(query.lower().translate(_FOLD))
    # Union, deduplicated preserving order (raw first, then folded)
    seen = set()
    combined = []
    for w in raw_ws + folded_ws:
        if w not in seen:
            seen.add(w)
            combined.append(w)
    return [r[0] for r in conn.execute(SQL, (match_expr(combined), k))] if combined else []


def newest_first(conn, query, k):
    """Deliberately weak baseline (ignores the query): highest rowids first. Used as a floor in trials/tests."""
    return [r[0] for r in conn.execute("SELECT rowid FROM mem_fts ORDER BY rowid DESC LIMIT ?", (k,))]
