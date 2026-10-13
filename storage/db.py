import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "signals.db")


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            symbol TEXT,
            first_seen TEXT,
            last_seen TEXT,
            times_seen INTEGER DEFAULT 1,
            last_score REAL,
            best_score REAL,
            last_reason TEXT,
            PRIMARY KEY (chain, address)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security (
            chain TEXT NOT NULL,
            address TEXT NOT NULL,
            checked_at TEXT NOT NULL,
            data TEXT,
            PRIMARY KEY (chain, address)
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


def known_tokens():
    """Set of (chain, address) already in the database"""
    conn = get_conn()
    rows = conn.execute("SELECT chain, address FROM tokens").fetchall()
    conn.close()
    return {(c, a.lower()) for c, a in rows}


def upsert_tokens(signals):
    """Insert new tokens, update existing ones. Expects one signal per token."""
    conn = get_conn()
    for s in signals:
        address = s.details["baseToken"]["address"].lower()
        now = s.timestamp.isoformat()
        conn.execute(
            """
            INSERT INTO tokens (chain, address, symbol, first_seen, last_seen,
                                times_seen, last_score, best_score, last_reason)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(chain, address) DO UPDATE SET
                symbol = excluded.symbol,
                last_seen = excluded.last_seen,
                times_seen = times_seen + 1,
                last_score = excluded.last_score,
                best_score = MAX(best_score, excluded.last_score),
                last_reason = excluded.last_reason
            """,
            (s.chain, address, s.token, now, now, s.score, s.score, s.reason),
        )
    conn.commit()
    conn.close()


def get_cached_security(chain, address, max_age_hours=12):
    conn = get_conn()
    row = conn.execute(
        "SELECT data FROM security WHERE chain=? AND address=? "
        "AND checked_at > datetime('now', ?)",
        (chain, address.lower(), f"-{max_age_hours} hours"),
    ).fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None


def save_security(chain, address, data):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO security (chain, address, checked_at, data) "
        "VALUES (?, ?, datetime('now'), ?)",
        (chain, address.lower(), json.dumps(data)),
    )
    conn.commit()
    conn.close()    
