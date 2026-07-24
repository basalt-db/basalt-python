<p align="center">
  <img src="https://raw.githubusercontent.com/basalt-db/basalt/main/docs/basalt-icon.png" alt="Basalt" width="96" height="96">
</p>

# basalt-client — Python client for Basalt

A dependency-free (standard-library-only) Python client for
[Basalt](https://github.com/basalt-db/basalt). It talks to a running
`basalt` server over its HTTP/JSON API and exposes a **DB-API 2.0-style**
interface plus a convenience `query()` that returns dicts.

```bash
pip install basalt-client
```

Start a server first (from the repo): `cd v2 && ./server mydata 8090`.

## DB-API 2.0 style

```python
import basalt

con = basalt.connect("http://127.0.0.1:8090", database="mydb")
cur = con.cursor()
cur.execute("SELECT id, name FROM users WHERE tier > ? ORDER BY id", [1])
for row in cur.fetchall():          # tuples, positional
    print(row)
print(cur.description)              # [(name, type_code, ...), ...]
```

Parameters use `qmark` style (`?`). Basalt has no server-side prepared
statements yet, so params are formatted **client-side** with SQL-standard
quoting — only *values* are substituted, never identifiers.

## Convenience: dicts in one call

```python
rows = con.query("SELECT tier, COUNT(*) AS n FROM users GROUP BY tier")
# -> [{'tier': 1, 'n': 10}, {'tier': 2, 'n': 7}]

con.execute("INSERT INTO users (id, name) VALUES (?, ?)", [42, "O'Brien"])
```

## Admin / introspection

```python
con.databases()          # ['mydb', ...]
con.schema()             # [{'name': 'users', 'nrows': 17, 'columns': [...]}, ...]
con._client.create_database("scratch")
con._client.drop_database("scratch")
```

## Works with pandas

```python
import pandas as pd, basalt
con = basalt.connect("http://127.0.0.1:8090", database="mydb")
df = pd.DataFrame(con.query("SELECT * FROM users"))
```

## Notes & limitations

- `commit()` is a no-op and `rollback()` raises — Basalt has **no transactions
  yet** (single-writer, group-commit durability). See the
  [roadmap](https://github.com/basalt-db/basalt/blob/main/ROADMAP.md).
- Errors from the engine raise `basalt.DatabaseError`; connection problems raise
  `basalt.OperationalError` (both subclass `basalt.Error`).
- A full **SQLAlchemy dialect** is a roadmap item and depends on the engine
  gaining transactions + the PostgreSQL wire protocol; this client is the
  building block for it.

MIT. Part of the [Basalt](https://github.com/basalt-db/basalt) project.
