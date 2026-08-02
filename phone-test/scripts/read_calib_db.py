import sqlite3
import json

db_path = 'D:/Users/59520/IDEProjects/xxinde/phone-test/backend/test.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 列出所有表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}\n")

# calibrations表
if 'calibrations' in tables:
    cur.execute("PRAGMA table_info(calibrations)")
    cols = cur.fetchall()
    col_names = [c[1] for c in cols]
    print(f"calibrations列: {col_names}")
    
    cur.execute("SELECT * FROM calibrations")
    rows = cur.fetchall()
    print(f"\n=== calibrations ({len(rows)}行) ===")
    for row in rows:
        print(f"\n--- Row ---")
        for name, val in zip(col_names, row):
            if name in ('pixel_points', 'mech_points') and val:
                try:
                    parsed = json.loads(val)
                    print(f"  {name}: {json.dumps(parsed, indent=2)}")
                except:
                    print(f"  {name}: {val}")
            else:
                print(f"  {name}: {val}")

# devices表
if 'devices' in tables:
    cur.execute("PRAGMA table_info(devices)")
    cols = cur.fetchall()
    col_names = [c[1] for c in cols]
    print(f"\ndevices列: {col_names}")
    
    cur.execute("SELECT * FROM devices")
    rows = cur.fetchall()
    print(f"\n=== devices ({len(rows)}行) ===")
    for row in rows:
        print(dict(zip(col_names, row)))

conn.close()
