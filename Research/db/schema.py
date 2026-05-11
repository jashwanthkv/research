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


def insert_paper_tables(paper_id: str, tables: list[dict]):
    """
    Store extracted tables for a paper.
    tables = [
        { "page": 3, "table_index": 0, "markdown": "| col1 | col2 |\\n..." }
    ]
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM paper_tables WHERE paper_id = ?", (paper_id,))

    for t in tables:
        cur.execute("""
            INSERT INTO paper_tables
            (table_id, paper_id, page_num, table_index, markdown)
            VALUES (?, ?, ?, ?, ?)
        """, (
            f"{paper_id}_tbl_{t.get('page', 0)}_{t.get('table_index', 0)}",
            paper_id,
            t.get("page"),
            t.get("table_index", 0),
            t["markdown"]
        ))

    conn.commit()
    conn.close()


def get_paper_tables(paper_id: str) -> list[dict]:
    """Retrieve all extracted tables for a given paper."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT page_num, table_index, markdown
        FROM paper_tables
        WHERE paper_id = ?
        ORDER BY page_num, table_index
    """, (paper_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {"page": r[0], "table_index": r[1], "markdown": r[2]}
        for r in rows
    ]


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
    # PAPER TABLES TABLE
    # -------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS paper_tables (
        table_id    TEXT PRIMARY KEY,
        paper_id    TEXT NOT NULL,
        page_num    INTEGER,
        table_index INTEGER,
        markdown    TEXT NOT NULL,

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

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_paper_tables_paper_id
    ON paper_tables(paper_id);
    """)

    conn.commit()
    conn.close()
    print("[OK] SQLite schema initialized successfully")

if __name__ == "__main__":
    init_db()
