import sqlite3, os

# Find the DB file
for db_path in ['app/social.db', 'social.db', 'app/social_app.db']:
    if os.path.exists(db_path):
        break

print(f"Using DB: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Migrate users table
cur.execute("PRAGMA table_info(users)")
cols = [r[1] for r in cur.fetchall()]
print("User columns:", cols)

if "bio" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN bio TEXT DEFAULT ''")
    print("Added bio")
if "avatar_color" not in cols:
    cur.execute("ALTER TABLE users ADD COLUMN avatar_color TEXT DEFAULT '#8b5cf6'")
    print("Added avatar_color")

# Migrate posts table
cur.execute("PRAGMA table_info(posts)")
post_cols = [r[1] for r in cur.fetchall()]
print("Post columns:", post_cols)

if "caption" not in post_cols:
    cur.execute("ALTER TABLE posts ADD COLUMN caption TEXT DEFAULT ''")
    print("Added caption")
if "repost_of" not in post_cols:
    cur.execute("ALTER TABLE posts ADD COLUMN repost_of INTEGER DEFAULT NULL")
    print("Added repost_of")

# Create likes table if not exists
cur.execute("""
CREATE TABLE IF NOT EXISTS likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, post_id)
)
""")
print("Ensured likes table")

# Create comments table if not exists
cur.execute("""
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
print("Ensured comments table")

conn.commit()
conn.close()
print("Migration complete!")
