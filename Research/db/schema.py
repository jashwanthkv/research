import sqlite3
import os

DB_PATH = "db/knowledge.db"

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)

def insert_paper_chunks(paper_id: str, chunks: list[dict]):
    """
    chunks = [
        { "chunk_index": 0, "section": "methodology", "content": "..." }
    ]
    """

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM paper_chunks WHERE paper_id = ?",
        (paper_id,)
    )

    for c in chunks:
        cur.execute("""
            INSERT INTO paper_chunks
            (chunk_id, paper_id, chunk_index, section, content)
            VALUES (?, ?, ?, ?, ?)
        """, (
            f"{paper_id}_{c['chunk_index']}",
            paper_id,
            c["chunk_index"],
            c.get("section"),
            c["content"]
        ))

    conn.commit()
    conn.close()

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # -------------------------
    # PAPERS TABLE
    # -------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS papers (
        paper_id        TEXT PRIMARY KEY,
        title           TEXT NOT NULL,
        abstract        TEXT,
        published_date  TEXT,
        url             TEXT,
        stored_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # -------------------------
    # PAPER CHUNKS TABLE
    # -------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_chunks (
        chunk_id     TEXT PRIMARY KEY,
        paper_id     TEXT NOT NULL,
        chunk_index  INTEGER NOT NULL,
        section      TEXT,
        content      TEXT NOT NULL,

        FOREIGN KEY (paper_id)
            REFERENCES papers(paper_id)
            ON DELETE CASCADE
    );
    """)

    # -------------------------
    # INDEXES
    # -------------------------
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_paper_chunks_paper_id
    ON paper_chunks(paper_id);
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_papers_published_date
    ON papers(published_date);
    """)

    conn.commit()
    conn.close()
    print("✅ SQLite schema initialized successfully")

if __name__ == "__main__":
    init_db()
