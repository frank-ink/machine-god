"""Example retrievers: retrieve(conn, query, k) -> list of doc ids (best first). Stdlib only."""
import re

_WORD = re.compile(r"\w+", re.UNICODE)
_FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
SQL = "SELECT rowid FROM mem_fts WHERE mem_fts MATCH ? ORDER BY bm25(mem_fts) LIMIT ?"


def words(query):
    return _WORD.findall(query)


def match_expr(ws):
    """Each word in double quotes, OR-joined (embedded quotes cannot occur: \\w+ only)."""
    return " OR ".join('"%s"' % w for w in ws)


def fts_bm25_or(conn, query, k):
    ws = words(query)
    return [r[0] for r in conn.execute(SQL, (match_expr(ws), k))] if ws else []


def fts_bm25_or_folded(conn, query, k):
    """Example candidate: lowercase and fold ae/oe/ue/ss before matching."""
    ws = words(query.lower().translate(_FOLD))
    return [r[0] for r in conn.execute(SQL, (match_expr(ws), k))] if ws else []


def newest_first(conn, query, k):
    """Deliberately weak baseline (ignores the query): highest rowids first. Used as a floor in trials/tests."""
    return [r[0] for r in conn.execute("SELECT rowid FROM mem_fts ORDER BY rowid DESC LIMIT ?", (k,))]
