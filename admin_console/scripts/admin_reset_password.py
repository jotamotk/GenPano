"""Reset or seed an Admin console account.

Usage:
    python scripts/admin_reset_password.py frank@genpano.com
    python scripts/admin_reset_password.py frank@genpano.com 'Strong-Password-123!'
"""

from __future__ import annotations

import os
import secrets
import string
import sys
import uuid
from datetime import datetime
from urllib.parse import unquote, urlparse

import bcrypt
import psycopg2


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://genpano:genpano2026@localhost:5432/genpano",
)


def parse_database_url(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise SystemExit(f"Unsupported DATABASE_URL scheme: {parsed.scheme!r}")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise SystemExit("DATABASE_URL must include host and database name")
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "dbname": unquote(parsed.path.lstrip("/")),
    }


def connect():
    return psycopg2.connect(**parse_database_url(DATABASE_URL))


def ensure_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'super_admin',
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                force_password_change_at TIMESTAMP,
                last_password_at TIMESTAMP,
                last_login_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_login_attempts (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                ip_address VARCHAR(45),
                success BOOLEAN NOT NULL,
                failure_code VARCHAR(32),
                user_agent VARCHAR(512),
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "Gp-" + "".join(secrets.choice(alphabet) for _ in range(20))


def hash_password(plaintext: str) -> str:
    payload = plaintext.encode("utf-8")
    if len(payload) > 72:
        raise SystemExit("Password is longer than bcrypt's 72-byte limit")
    cost = int(os.getenv("ADMIN_BCRYPT_COST", "12"))
    return bcrypt.hashpw(payload, bcrypt.gensalt(rounds=cost)).decode("ascii")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python scripts/admin_reset_password.py <email> [new-password]", file=sys.stderr)
        return 2

    email = argv[1].strip().lower()
    password = argv[2] if len(argv) >= 3 else generate_password()
    digest = hash_password(password)
    now = datetime.utcnow()

    conn = connect()
    try:
        ensure_tables(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM admin_users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE admin_users
                    SET password_hash = %s,
                        role = 'super_admin',
                        status = 'active',
                        force_password_change_at = NULL,
                        last_password_at = %s,
                        updated_at = NOW()
                    WHERE email = %s
                    """,
                    (digest, now, email),
                )
                action = "reset"
            else:
                cur.execute(
                    """
                    INSERT INTO admin_users
                        (id, email, password_hash, role, status,
                         force_password_change_at, last_password_at, created_at)
                    VALUES (%s, %s, %s, 'super_admin', 'active', NULL, %s, NOW())
                    """,
                    (str(uuid.uuid4()), email, digest, now),
                )
                action = "created"
        conn.commit()
    finally:
        conn.close()

    print(f"Admin user {action}: {email}")
    print(f"Temporary password: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
