import sqlite3
from pathlib import Path

db = Path("game_agent_data/games/my_game/agent.db")
conn = sqlite3.connect(db)
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables:", [t[0] for t in tables])

for t in tables:
    print(f"\nTable: {t[0]}")
    c.execute(f"PRAGMA table_info({t[0]})")
    for r in c.fetchall():
        print(f"  {r[1]} ({r[2]})")

conn.close()
