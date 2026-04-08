# Database Optimization Guide

Practical techniques for PostgreSQL performance, reliability, and scalability.

---

## 1. Indexing Strategy

### When to Add an Index

- Column appears in `WHERE`, `JOIN ON`, `ORDER BY`, or `GROUP BY`
- Column has high cardinality (many distinct values)
- Query runs frequently AND full table scans show up in `EXPLAIN`

### Index Types

| Type | Best for |
|------|---------|
| B-tree (default) | Equality (`=`) and range (`<`, `>`, `BETWEEN`) |
| Hash | Equality only; slightly faster than B-tree for pure lookups |
| GIN | Full-text search, JSONB containment (`@>`), array operators |
| GiST | Geometric types, IP ranges, full-text with ranking |
| BRIN | Monotonically increasing columns on very large tables (timestamps) |
| Partial | Add `WHERE` clause to index a subset of rows |

### Composite Index Rules

- Column order matters: put the most selective column first for range queries;
  put equality columns first for multi-column equality.
- A composite index on `(a, b, c)` serves queries on `a`, `(a, b)`, and `(a, b, c)`
  but NOT on `(b)` or `(c)` alone.
- Covering indexes (`INCLUDE (col)`) avoid heap fetches for index-only scans.

```sql
-- Partial index: only index active users
CREATE INDEX idx_users_email_active ON users (email) WHERE deleted_at IS NULL;

-- Covering index for a hot query path
CREATE INDEX idx_orders_user ON orders (user_id, created_at DESC)
INCLUDE (status, total_cents);
```

---

## 2. Query Optimization

### Reading EXPLAIN ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT ...;
```

Key nodes to watch:
- **Seq Scan** on large tables → missing index
- **Hash Join** vs **Nested Loop** → NL is fast when outer set is small
- **Sort** on disk (`Sort Method: external merge`) → increase `work_mem`
- **Rows** estimate vs actual → stale statistics; run `ANALYZE`

### Common Anti-patterns

```sql
-- Bad: function on indexed column disables index
SELECT * FROM orders WHERE DATE(created_at) = '2024-01-01';
-- Good:
SELECT * FROM orders WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02';

-- Bad: LIKE with leading wildcard
SELECT * FROM products WHERE name LIKE '%widget%';
-- Good: full-text search
SELECT * FROM products WHERE to_tsvector('english', name) @@ to_tsquery('widget');

-- Bad: SELECT * (fetches unused columns, prevents index-only scans)
SELECT * FROM users WHERE email = $1;
-- Good:
SELECT id, email, role FROM users WHERE email = $1;

-- Bad: N+1 (one query per row in the outer loop)
-- Good: JOIN or DataLoader / batch load
```

### CTEs vs Subqueries

PostgreSQL 12+ inlines CTEs by default. Use `MATERIALIZED` to force a fence:

```sql
-- Force materialization (barrier for complex plans)
WITH expensive AS MATERIALIZED (
  SELECT ... FROM large_table WHERE ...
)
SELECT * FROM expensive JOIN ...;
```

---

## 3. Connection Pooling

Use **PgBouncer** (transaction mode) in front of PostgreSQL.

| Pool mode | When to use |
|-----------|------------|
| Session | Persistent connections; use when SET/advisory locks needed |
| Transaction | Recommended for most web apps; reuses connections efficiently |
| Statement | Highest throughput; no multi-statement transactions |

Application pool settings (node-postgres example):
```javascript
const pool = new Pool({
  max: 10,                   // workers × 2 is a good starting point
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 2_000,
});
```

Rule of thumb: `max_connections` in postgres.conf = (number of CPU cores × 4) + spare for admin.

---

## 4. Schema Design

### Data Types

| Instead of | Use |
|-----------|-----|
| `VARCHAR(255)` | `TEXT` (same storage, no limit overhead) |
| `FLOAT` for money | `NUMERIC(19,4)` or store cents as `BIGINT` |
| `CHAR(n)` | `TEXT` |
| `TIMESTAMP` | `TIMESTAMPTZ` (stores UTC, displays in session TZ) |
| Integer surrogate keys | `UUID` for distributed systems; `BIGSERIAL` for single-node |

### Normalization vs. Denormalization

- Normalize to 3NF for OLTP workloads.
- Denormalize (materialized views, pre-computed columns) only after profiling.
- Use `JSONB` for genuinely schema-less data; avoid it as a workaround for poor design.

### Soft Deletes

```sql
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMPTZ;
CREATE INDEX idx_users_active ON users (id) WHERE deleted_at IS NULL;
```

---

## 5. Maintenance

### Autovacuum Tuning

For high-write tables, lower the thresholds:
```sql
ALTER TABLE orders SET (
  autovacuum_vacuum_scale_factor  = 0.01,   -- vacuum when 1% of rows are dead
  autovacuum_analyze_scale_factor = 0.005
);
```

### Bloat Monitoring

```sql
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total,
       n_dead_tup, n_live_tup,
       ROUND(100 * n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS dead_pct
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

Use `pg_repack` for zero-downtime table rewrites when bloat is severe.

---

## 6. Read Replicas & Partitioning

### Read Replicas

- Route `SELECT` queries to replicas via PgBouncer or application logic.
- Be aware of replication lag; never read your own writes from a replica.
- Use `synchronous_commit = remote_apply` for zero-lag critical reads.

### Table Partitioning

Partition by range (time-series), list (status/region), or hash (even distribution):

```sql
CREATE TABLE events (
    id          BIGSERIAL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload     JSONB
) PARTITION BY RANGE (occurred_at);

CREATE TABLE events_2024_q1 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');
```

Use `pg_partman` to automate partition creation and retention.

---

## 7. Observability Checklist

- [ ] `pg_stat_statements` enabled; review top 20 queries weekly
- [ ] Autovacuum activity tracked (`pg_stat_user_tables.last_autovacuum`)
- [ ] Replication lag monitored (`pg_stat_replication.replay_lag`)
- [ ] Connection count alerted (`pg_stat_activity` vs `max_connections`)
- [ ] Lock waits alerted (`pg_locks` with `granted = false`)
- [ ] Slow query log enabled (`log_min_duration_statement = 1000`)
- [ ] Table bloat monitored monthly
