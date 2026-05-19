import sqlite3

conn = sqlite3.connect('jobjockey.db')
c = conn.cursor()

new_cols = ['state', 'college', 'edu_domain', 'duration', 'extra_data']

existing = [r[1] for r in c.execute('PRAGMA table_info(candidates)').fetchall()]
print("Existing columns:", existing)

for col in new_cols:
    if col not in existing:
        c.execute(f'ALTER TABLE candidates ADD COLUMN {col} TEXT DEFAULT ""')
        conn.commit()
        print(f"Added: {col}")
    else:
        print(f"Already exists: {col}")

conn.close()
print("Done!")