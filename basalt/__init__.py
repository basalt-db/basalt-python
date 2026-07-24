"""basalt — official Python client for the Basalt database.

Talks to a running ``basalt`` server over its HTTP/JSON API. Dependency-free
(standard library only). Provides both a small DB-API-2.0-style interface and a
convenience ``query()`` that returns a list of dicts.

    import basalt
    con = basalt.connect("http://127.0.0.1:8090", database="mydb")
    cur = con.cursor()
    cur.execute("SELECT id, name FROM users ORDER BY id")
    for row in cur.fetchall():
        print(row)                 # tuples, positional
    print(cur.description)         # [(name, type_code, ...), ...]

    # or, dicts in one call:
    rows = con.query("SELECT * FROM users")   # -> list[dict]

Note: Basalt does not (yet) support prepared statements / bind parameters, so
``execute(sql, params)`` formats params client-side. Identifiers are never taken
from params; only values are substituted, with SQL-standard quoting.
"""
from __future__ import annotations
import json
import urllib.request
import urllib.parse
import urllib.error
import datetime
from typing import Any, Iterable, Sequence

__version__ = "0.1.0"
apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"   # execute("... WHERE id = ?", [1])

__all__ = [
    "connect", "Connection", "Cursor", "Client",
    "Error", "DatabaseError", "ProgrammingError", "OperationalError",
    "escape", "apilevel", "threadsafety", "paramstyle", "__version__",
]


# ---- exceptions (DB-API 2.0 hierarchy) -----------------------------------
class Error(Exception):
    """Base class for all Basalt client errors."""


class DatabaseError(Error):
    """The server reported an error executing a statement."""


class ProgrammingError(DatabaseError):
    """A malformed statement or client misuse."""


class OperationalError(Error):
    """A transport/connection problem talking to the server."""


# ---- value formatting -----------------------------------------------------
def escape(v: Any) -> str:
    """Format a Python value as a SQL literal (values only, never identifiers)."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (datetime.datetime,)):
        return "'" + v.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(v, (datetime.date,)):
        return "'" + v.strftime("%Y-%m-%d") + "'"
    return "'" + str(v).replace("'", "''") + "'"


def _bind(sql: str, params: Sequence[Any] | None) -> str:
    if not params:
        return sql
    out, it = [], iter(params)
    i = 0
    n_placeholders = sql.count("?")
    if n_placeholders != len(params):
        raise ProgrammingError(
            f"parameter count mismatch: {n_placeholders} placeholders, {len(params)} params")
    for ch in sql:
        if ch == "?":
            out.append(escape(next(it)))
        else:
            out.append(ch)
    return "".join(out)


# ---- low-level HTTP client ------------------------------------------------
class Client:
    """Thin wrapper over the server's HTTP API. Returns parsed JSON dicts."""

    def __init__(self, url: str = "http://127.0.0.1:8090", database: str = "", timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.database = database
        self.timeout = timeout

    def _request(self, path: str, body: bytes | None = None) -> Any:
        req = urllib.request.Request(
            self.url + path,
            data=body if body is not None else None,
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OperationalError(f"cannot reach Basalt server at {self.url}: {e}") from e

    def execute(self, sql: str, database: str | None = None) -> dict:
        db = self.database if database is None else database
        r = self._request("/api/query?db=" + urllib.parse.quote(db), sql.encode("utf-8"))
        if isinstance(r, dict) and r.get("error"):
            raise DatabaseError(r["error"])
        return r

    def databases(self) -> list[str]:
        return self._request("/api/databases")

    def schema(self, database: str | None = None) -> list[dict]:
        db = self.database if database is None else database
        return self._request("/api/schema?db=" + urllib.parse.quote(db)).get("tables", [])

    def create_database(self, name: str) -> Any:
        return self._request("/api/create_db?db=" + urllib.parse.quote(name), b"")

    def drop_database(self, name: str) -> Any:
        return self._request("/api/drop_db?db=" + urllib.parse.quote(name), b"")


# ---- DB-API 2.0 style interface ------------------------------------------
class Cursor:
    def __init__(self, connection: "Connection"):
        self.connection = connection
        self.arraysize = 1
        self._rows: list[tuple] = []
        self._idx = 0
        self.description: list[tuple] | None = None
        self.rowcount: int = -1
        self.lastresult: dict | None = None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> "Cursor":
        r = self.connection._client.execute(_bind(sql, params))
        self.lastresult = r
        cols = r.get("columns") or []
        types = r.get("types") or []
        self.description = [(cols[i], types[i] if i < len(types) else None,
                             None, None, None, None, None) for i in range(len(cols))] or None
        self._rows = [tuple(row) for row in (r.get("rows") or [])]
        self._idx = 0
        self.rowcount = r.get("total_rows", len(self._rows))
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]) -> "Cursor":
        for p in seq_of_params:
            self.execute(sql, p)
        return self

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchmany(self, size: int | None = None):
        size = self.arraysize if size is None else size
        out = self._rows[self._idx:self._idx + size]
        self._idx += len(out)
        return out

    def fetchall(self):
        out = self._rows[self._idx:]
        self._idx = len(self._rows)
        return out

    def dicts(self) -> list[dict]:
        """Rows of the last execute() as dicts keyed by column name."""
        cols = [d[0] for d in (self.description or [])]
        return [dict(zip(cols, row)) for row in self._rows]

    def __iter__(self):
        return iter(self.fetchall())

    def close(self):
        self._rows = []


class Connection:
    def __init__(self, url: str = "http://127.0.0.1:8090", database: str = "", timeout: float = 30.0):
        self._client = Client(url, database, timeout)

    # DB-API required (no transactions on the server yet — these are no-ops so
    # code written against DB-API still runs).
    def commit(self):  # noqa: D401
        pass

    def rollback(self):
        raise OperationalError("Basalt does not support transactions yet (no ROLLBACK)")

    def cursor(self) -> Cursor:
        return Cursor(self)

    def close(self):
        pass

    # conveniences
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur.dicts()

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> dict:
        return self._client.execute(_bind(sql, params))

    def databases(self) -> list[str]:
        return self._client.databases()

    def schema(self, database: str | None = None) -> list[dict]:
        return self._client.schema(database)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def connect(url: str = "http://127.0.0.1:8090", database: str = "", timeout: float = 30.0) -> Connection:
    """Connect to a running Basalt server. DB-API 2.0 style entry point."""
    return Connection(url, database, timeout)
