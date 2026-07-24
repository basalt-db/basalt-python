"""Smoke test for the Python client against a running Basalt server.

Usage:
    ./server /tmp/basalt_pysmoke 8099 &
    python clients/python/tests/smoke.py http://127.0.0.1:8099
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import basalt

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
DB = "pysmoke"
passed = 0
def ok(name):
    global passed; passed += 1; print("  ✓", name)

con = basalt.connect(URL)
# fresh database
try:
    con._client.drop_database(DB)
except Exception:
    pass
con._client.create_database(DB)
con = basalt.connect(URL, database=DB)

con.execute("CREATE TABLE users (id BIGINT PRIMARY KEY, name VARCHAR, tier INT)")
ok("CREATE TABLE")

# parameterized insert (client-side binding) incl. apostrophe
con.execute("INSERT INTO users (id, name, tier) VALUES (?, ?, ?)", [1, "O'Brien", 2])
con.execute("INSERT INTO users VALUES (2, 'alice', 1), (3, 'bob', 2)")
ok("INSERT (bound params + apostrophe)")

cur = con.cursor()
cur.execute("SELECT id, name FROM users ORDER BY id")
rows = cur.fetchall()
assert rows[0] == (1, "O'Brien"), rows
ok("fetchall() tuples + '' round-trip")

assert cur.description[0][0] == "id" and cur.description[1][0] == "name"
ok("cursor.description")

d = con.query("SELECT tier, COUNT(*) AS n FROM users GROUP BY tier ORDER BY tier")
assert {r["tier"]: r["n"] for r in d} == {1: 1, 2: 2}, d
ok("query() -> dicts + GROUP BY")

# error surfaces as DatabaseError
try:
    con.execute("SELECT * FROM nope")
    raise AssertionError("expected error")
except basalt.DatabaseError:
    ok("DatabaseError on bad SQL")

# schema()
names = {t["name"] for t in con.schema()}
assert "users" in names, names
ok("schema()")

con._client.drop_database(DB)
print(f"\n{passed} checks passed")
