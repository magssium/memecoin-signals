import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "signals.db")


def get_conn():
    if not os.path.exists(os.path.dirname(DB_PATH)): os.makedirs(os.path.dirname(DB_PATH))
    
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL,
            token TEXT NOT NULL,
            chain TEXT NOT NULL,
            address TEXT,
            score REAL,
            reason TEXT,
            details TEXT
        )
    """)
    return conn


def save_signals(signals):
    conn = get_conn()
    rows = [
        (
            s.timestamp.isoformat(),
            s.source,
            s.token,
            s.chain,
            (s.details.get("baseToken") or {}).get("address"),
            s.score,
            s.reason,
            json.dumps(s.details),
        )
        for s in signals
    ]
    conn.executemany(
        "INSERT INTO signals (timestamp, source, token, chain, address, score, reason, details) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return len(rows)


def recent_counts(hours=24, limit=20):
    """Tokens that keep showing up across scans."""
    conn = get_conn()
    cur = conn.execute(
        """
        SELECT token, chain, COUNT(*) AS appearances, ROUND(AVG(score), 1) AS avg_score
        FROM signals
        WHERE timestamp > datetime('now', ?)
        GROUP BY token, chain
        ORDER BY appearances DESC, avg_score DESC
        LIMIT ?
        """,
        (f"-{hours} hours", limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows