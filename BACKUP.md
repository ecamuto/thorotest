# Backup & Restore

Two things hold all ThoroTest state:

1. **The database** — everything except file attachments.
2. **The `uploads/` directory** — attachment files (evidence, imports). The
   database stores only their paths, so DB and uploads must be backed up (and
   restored) together.

Always take a backup before upgrading ThoroTest. Schema upgrades run
automatically on boot (Alembic), but a backup is your rollback path.

---

## SQLite (default)

The database is a single file (`testhub.db` by default; WAL mode also writes
`testhub.db-wal` / `testhub.db-shm` sidecars).

**Backup (safe while the app is running):**

```bash
sqlite3 testhub.db ".backup 'backup/testhub-$(date +%F).db'"
cp -r uploads "backup/uploads-$(date +%F)"
```

`.backup` produces a consistent snapshot even mid-write — prefer it over
copying the file directly. If you must copy files instead, stop the app first
and include the `-wal`/`-shm` files.

**Restore:**

```bash
# stop the app first
cp backup/testhub-2026-07-02.db testhub.db
rm -f testhub.db-wal testhub.db-shm
rm -rf uploads && cp -r backup/uploads-2026-07-02 uploads
# start the app — it migrates the schema forward automatically if needed
```

### Docker (SQLite)

`docker-compose.sqlite.yml` bind-mounts both `./testhub.db` and `./uploads`
from the host, so the procedure above runs on the host unchanged.

---

## PostgreSQL

**Backup:**

```bash
pg_dump -Fc -h localhost -U thorotest thorotest > "backup/thorotest-$(date +%F).dump"
cp -r uploads "backup/uploads-$(date +%F)"
```

**Restore:**

```bash
# stop the app first
pg_restore --clean --if-exists -h localhost -U thorotest -d thorotest backup/thorotest-2026-07-02.dump
rm -rf uploads && cp -r backup/uploads-2026-07-02 uploads
```

### Docker (Postgres)

```bash
# backup
docker compose exec db pg_dump -Fc -U thorotest thorotest > "backup/thorotest-$(date +%F).dump"
docker compose cp app:/app/uploads "backup/uploads-$(date +%F)"

# restore
docker compose stop app
cat backup/thorotest-2026-07-02.dump | docker compose exec -T db pg_restore --clean --if-exists -U thorotest -d thorotest
docker compose cp "backup/uploads-2026-07-02" app:/app/uploads
docker compose start app
```

Attachments live in the `uploads_data` named volume (mounted at
`/app/uploads` in the app container).

---

## MySQL / MariaDB

```bash
# backup
mysqldump --single-transaction -u thorotest -p thorotest > "backup/thorotest-$(date +%F).sql"
cp -r uploads "backup/uploads-$(date +%F)"

# restore (stop the app first)
mysql -u thorotest -p thorotest < backup/thorotest-2026-07-02.sql
rm -rf uploads && cp -r backup/uploads-2026-07-02 uploads
```

---

## Scheduling

Run the backup commands from cron (or your scheduler of choice) and ship the
output somewhere off the host. A nightly example:

```cron
0 3 * * * cd /opt/thorotest && sqlite3 testhub.db ".backup '/backups/testhub-$(date +\%F).db'" && cp -r uploads "/backups/uploads-$(date +\%F)"
```

Test the restore path at least once before you rely on it.
