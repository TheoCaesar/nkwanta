# Migrations

Every change to the database schema is a numbered file in `versions/`. They run in
order, and the database records which have been applied, so the schema can be rebuilt
from nothing with one command.

```bash
alembic upgrade head        # apply everything outstanding
alembic current             # what is applied right now
alembic history             # every migration, in order
alembic downgrade -1        # undo the most recent one
```

After adding or changing a model in `app/models.py`:

```bash
alembic revision --autogenerate -m "add reports table"
```

**Always read the generated file before running it.** Autogenerate is a good assistant
and a poor author — it regularly misses index changes and occasionally proposes
dropping something it simply did not recognise.

`DATABASE_URL` must be set in the environment or in `.env`. It is never written into
`alembic.ini`, so no credential is committed.
