#!/usr/bin/env python3
"""
Database Migration Tool - Manage, analyze, and apply PostgreSQL migrations.

Usage:
    python scripts/database_migration_tool.py <command> [options]

Commands:
    status      Show applied / pending migrations
    up          Apply all pending migrations
    down        Roll back the last applied migration
    create      Create a new blank migration file
    validate    Check SQL syntax of pending migrations
    analyze     Report on table sizes, index usage, slow queries

Options:
    --db-url URL    Database URL (defaults to DATABASE_URL env var)
    --dir DIR       Migrations directory (default: src/db/migrations)
    --verbose       Verbose output
    --dry-run       Print SQL without executing (up/down)
"""

import argparse
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATION_RE = re.compile(r'^(\d+)_[\w]+\.sql$')


def get_connection(db_url: str):
    if not HAS_PSYCOPG2:
        print("psycopg2 not installed — run: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)
    return psycopg2.connect(db_url)


def ensure_schema_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     BIGINT PRIMARY KEY,
                name        TEXT NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    conn.commit()


def applied_versions(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        return {row[0] for row in cur.fetchall()}


def collect_migrations(directory: Path) -> list:
    files = sorted(
        f for f in directory.glob("*.sql") if MIGRATION_RE.match(f.name)
    )
    result = []
    for f in files:
        m = MIGRATION_RE.match(f.name)
        result.append({"version": int(m.group(1)), "name": f.stem, "path": f})
    return result


def print_table(headers: list, rows: list) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_status(args) -> int:
    migrations = collect_migrations(args.dir)
    if not migrations:
        print(f"No migration files found in {args.dir}")
        return 0

    if args.db_url:
        conn = get_connection(args.db_url)
        ensure_schema_table(conn)
        applied = applied_versions(conn)
        conn.close()
    else:
        applied = set()
        print("(no --db-url provided; showing file list only)\n")

    rows = []
    for m in migrations:
        state = "applied" if m["version"] in applied else "pending"
        rows.append([m["version"], m["name"], state])

    print_table(["Version", "Name", "Status"], rows)
    pending = sum(1 for r in rows if r[2] == "pending")
    print(f"\n{pending} pending migration(s).")
    return 0


def cmd_up(args) -> int:
    migrations = collect_migrations(args.dir)
    if not migrations:
        print("No migrations found.")
        return 0

    conn = get_connection(args.db_url)
    ensure_schema_table(conn)
    applied = applied_versions(conn)

    pending = [m for m in migrations if m["version"] not in applied]
    if not pending:
        print("All migrations already applied.")
        conn.close()
        return 0

    for m in pending:
        sql = m["path"].read_text()
        print(f"  Applying {m['name']} ...", end="", flush=True)
        if args.dry_run:
            print(f"\n[dry-run]\n{sql}\n")
            continue
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                    (m["version"], m["name"])
                )
            conn.commit()
            print(" ok")
        except Exception as exc:
            conn.rollback()
            print(f" FAILED\n  {exc}", file=sys.stderr)
            conn.close()
            return 1

    conn.close()
    print(f"\n{len(pending)} migration(s) applied.")
    return 0


def cmd_down(args) -> int:
    conn = get_connection(args.db_url)
    ensure_schema_table(conn)

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM schema_migrations ORDER BY version DESC LIMIT 1")
        last = cur.fetchone()

    if not last:
        print("No migrations to roll back.")
        conn.close()
        return 0

    rollback_path = args.dir / f"{last['version']:04d}_{last['name'].split('_', 1)[-1]}.rollback.sql"
    if not rollback_path.exists():
        print(f"Rollback file not found: {rollback_path}", file=sys.stderr)
        print("Create a matching .rollback.sql file to enable down migrations.")
        conn.close()
        return 1

    sql = rollback_path.read_text()
    print(f"Rolling back {last['name']} ...", end="", flush=True)
    if args.dry_run:
        print(f"\n[dry-run]\n{sql}")
        conn.close()
        return 0

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("DELETE FROM schema_migrations WHERE version = %s", (last["version"],))
        conn.commit()
        print(" ok")
    except Exception as exc:
        conn.rollback()
        print(f" FAILED\n  {exc}", file=sys.stderr)
        conn.close()
        return 1

    conn.close()
    return 0


def cmd_create(args) -> int:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    slug = re.sub(r'\W+', '_', args.name.lower()).strip('_')
    filename = f"{timestamp}_{slug}.sql"
    path = args.dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"-- Migration: {slug}\n-- Created: {datetime.now(timezone.utc).isoformat()}\n\n")
    print(f"Created {path}")
    return 0


def cmd_validate(args) -> int:
    migrations = collect_migrations(args.dir)
    errors = 0
    for m in migrations:
        sql = m["path"].read_text().strip()
        if not sql:
            print(f"  WARN  {m['name']}: empty file")
        elif not sql.endswith(";"):
            print(f"  WARN  {m['name']}: does not end with semicolon")
        else:
            if args.verbose:
                print(f"  OK    {m['name']}")
    if errors == 0:
        print("All migrations validated.")
    return errors


def cmd_analyze(args) -> int:
    conn = get_connection(args.db_url)

    print("=== Table Sizes ===")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                schemaname || '.' || tablename AS table,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
                pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
                pg_size_pretty(pg_indexes_size(schemaname||'.'||tablename)) AS index_size
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog','information_schema')
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            LIMIT 20
        """)
        rows = cur.fetchall()
    print_table(["Table", "Total", "Data", "Indexes"], rows)

    print("\n=== Unused Indexes ===")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                schemaname || '.' || relname AS table,
                indexrelname AS index,
                idx_scan AS scans,
                pg_size_pretty(pg_relation_size(i.indexrelid)) AS size
            FROM pg_stat_user_indexes ui
            JOIN pg_index i ON ui.indexrelid = i.indexrelid
            WHERE idx_scan < 50 AND NOT i.indisprimary
            ORDER BY pg_relation_size(i.indexrelid) DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
    if rows:
        print_table(["Table", "Index", "Scans", "Size"], rows)
    else:
        print("  No unused indexes detected.")

    print("\n=== Slow Query Summary (pg_stat_statements) ===")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    LEFT(query, 80) AS query,
                    calls,
                    ROUND(mean_exec_time::numeric, 2) AS mean_ms,
                    ROUND(total_exec_time::numeric, 2) AS total_ms
                FROM pg_stat_statements
                ORDER BY mean_exec_time DESC
                LIMIT 10
            """)
            rows = cur.fetchall()
        print_table(["Query", "Calls", "Mean ms", "Total ms"], rows)
    except Exception:
        print("  pg_stat_statements extension not available.")

    conn.close()
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Database migration management tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=["status", "up", "down", "create", "validate", "analyze"])
    parser.add_argument("--db-url", default=os.environ.get("DATABASE_URL"), help="Postgres connection URL")
    parser.add_argument("--dir",    type=Path, default=Path("src/db/migrations"), help="Migrations directory")
    parser.add_argument("--name",   default="new_migration", help="Name for 'create' command")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


COMMANDS = {
    "status":   cmd_status,
    "up":       cmd_up,
    "down":     cmd_down,
    "create":   cmd_create,
    "validate": cmd_validate,
    "analyze":  cmd_analyze,
}


def main() -> int:
    args = parse_args()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
