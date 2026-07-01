# Migrations

Argus tracks schema changes as numbered, immutable SQL files applied in
order and recorded in a `schema_migrations` table. No new dependency was
added for this (no Alembic) — `service.py`'s `run_migrations()` just walks
this directory and executes anything not yet recorded, using the same
psycopg2 connection pool the rest of the app uses.

## Rules

1. **Never edit a migration that has already been committed and might have
   run somewhere** (your machine, a teammate's, prod). If a table needs to
   change, write a new migration — `0002_add_x.sql`, `0003_alter_y.sql`, etc.
2. **Filenames are the version key.** They're sorted and applied
   lexicographically, so always zero-pad: `0002_`, not `2_`.
3. **Each file should be one coherent change** (add a column, add a table,
   backfill a value) — not a grab-bag of unrelated edits.
4. **Migrations run automatically on startup** via `init_db()` →
   `run_migrations()`. There is no separate "migrate" command to remember.
5. `schema_postgres.sql` in the parent folder is kept only as a
   human-readable snapshot of "what the schema looks like today" — the
   database itself is built exclusively from the files in this folder.

## Writing a new migration

```sql
-- src/database/migrations/0002_add_alert_notes.sql
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS analyst_notes TEXT;
```

Use `IF NOT EXISTS` / `IF EXISTS` guards where Postgres supports them, so a
migration is safe to re-run if `schema_migrations` and the real schema ever
drift out of sync (e.g. someone ran the old `CREATE TABLE IF NOT EXISTS`
schema file by hand before this system existed — `0001_baseline.sql` is
written to be a no-op against that state).

## Checking what's applied

```sql
SELECT * FROM schema_migrations ORDER BY version;
```
