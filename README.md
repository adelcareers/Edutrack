# EduTrack

Home Education, Evidenced.

## Database (Neon Postgres)

This project supports connecting to a Neon Postgres instance via `DATABASE_URL`.

- Add your connection string to `.env` as `DATABASE_URL=postgresql://user:pass@host:port/dbname`.
- Do NOT commit `.env` — secrets must never be stored in the repository.

To run migrations and verify connectivity:

```bash
# activate venv
source .venv/bin/activate

# run migrations
./.venv/bin/python manage.py migrate

# quick connectivity check
./.venv/bin/python scripts/check_db.py
```

If you prefer sqlite for local development, leave `DATABASE_URL` blank in `.env` and the project will fall back to `db.sqlite3`.
