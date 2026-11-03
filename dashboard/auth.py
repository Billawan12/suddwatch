"""
auth.py — SuddWatch dashboard accounts (dashboard/auth.db)

Tables (created automatically):
  users            — active accounts (email, name, role, pw_hash, active)
  access_requests  — requests from the "Request Access" form
                     (status: pending → approved / rejected)

Passwords are stored as salted PBKDF2-SHA256 hashes:
    pbkdf2$<iterations>$<salt hex>$<hash hex>
Older databases stored plain SHA-256 hex digests; those still verify and
are upgraded to PBKDF2 the next time that user signs in.

The three demonstration accounts from the README are created when the
users table is empty, so a fresh checkout can be signed into.
"""
import hashlib
import hmac
import os
import sqlite3
from pathlib import Path
from typing import Optional

AUTH_DB = Path(__file__).parent / "auth.db"
ITERATIONS = 200_000

DEMO_ACCOUNTS = [
    ("admin@suddwatch.org", "System Administrator", "Admin", "admin123"),
    ("coord@ocha.org", "OCHA Coordinator", "User", "ocha2025"),
    ("analyst@reach.org", "REACH Analyst", "User", "reach2025"),
]


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2$"):
        try:
            _, iters, salt_hex, hash_hex = stored.split("$")
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                         bytes.fromhex(salt_hex), int(iters))
            return hmac.compare_digest(digest.hex(), hash_hex)
        except ValueError:
            return False
    # Legacy unsalted SHA-256
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(), stored)


def _conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or AUTH_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_auth(db_path: Optional[Path] = None) -> None:
    conn = _conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    UNIQUE NOT NULL,
            name        TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'User',
            pw_hash     TEXT    NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS access_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            org         TEXT NOT NULL,
            email       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'User',
            pw_hash     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT DEFAULT (datetime('now'))
        );
    """)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO users (email, name, role, pw_hash) VALUES (?,?,?,?)",
            [(e, n, r, hash_password(p)) for e, n, r, p in DEMO_ACCOUNTS])
    conn.commit()
    conn.close()


def authenticate(email: str, password: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Return {email, name, role} for valid active credentials, else None."""
    init_auth(db_path)
    email = (email or "").strip().lower()
    conn = _conn(db_path)
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ? AND active = 1",
                           (email,)).fetchone()
        if not row or not verify_password(password or "", row["pw_hash"]):
            return None
        if not row["pw_hash"].startswith("pbkdf2$"):
            conn.execute("UPDATE users SET pw_hash = ? WHERE id = ?",
                         (hash_password(password), row["id"]))
            conn.commit()
        return {"email": row["email"], "name": row["name"], "role": row["role"]}
    finally:
        conn.close()


def submit_request(name: str, org: str, email: str, password: str,
                   db_path: Optional[Path] = None) -> str:
    """Store an access request. Returns 'ok', 'exists' or 'pending'."""
    init_auth(db_path)
    email = email.strip().lower()
    conn = _conn(db_path)
    try:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            return "exists"
        if conn.execute("SELECT 1 FROM access_requests WHERE email = ? AND status = 'pending'",
                        (email,)).fetchone():
            return "pending"
        conn.execute(
            "INSERT INTO access_requests (name, org, email, pw_hash) VALUES (?,?,?,?)",
            (name.strip(), org.strip(), email, hash_password(password)))
        conn.commit()
        return "ok"
    finally:
        conn.close()


def list_users(db_path: Optional[Path] = None) -> list:
    init_auth(db_path)
    conn = _conn(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT email, name, role, active, created_at FROM users ORDER BY role, email")]
    finally:
        conn.close()


def list_requests(status: str = "pending", db_path: Optional[Path] = None) -> list:
    init_auth(db_path)
    conn = _conn(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, name, org, email, role, status, submitted_at FROM access_requests "
            "WHERE status = ? ORDER BY submitted_at", (status,))]
    finally:
        conn.close()


def decide_request(request_id: int, approve: bool, db_path: Optional[Path] = None) -> bool:
    """Approve (creates the user) or reject a pending request."""
    init_auth(db_path)
    conn = _conn(db_path)
    try:
        req = conn.execute("SELECT * FROM access_requests WHERE id = ? AND status = 'pending'",
                           (request_id,)).fetchone()
        if not req:
            return False
        if approve:
            conn.execute(
                "INSERT OR IGNORE INTO users (email, name, role, pw_hash) VALUES (?,?,?,?)",
                (req["email"], f"{req['name']} ({req['org']})", req["role"], req["pw_hash"]))
        conn.execute("UPDATE access_requests SET status = ? WHERE id = ?",
                     ("approved" if approve else "rejected", request_id))
        conn.commit()
        return True
    finally:
        conn.close()
