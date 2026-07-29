"""Create the database schema (Req 14, 15).

MVP bootstrap via SQLAlchemy `create_all`. For production, an Alembic migration can be
generated from the same `tables.Base` metadata.

`create_all` only ever CREATEs — it will not add a column to a table that already exists.
Until Alembic is wired up, additive columns are applied here as idempotent
`ADD COLUMN IF NOT EXISTS` statements so an already-deployed database picks them up when
this job re-runs. Additive and nullable only: anything that rewrites or drops data belongs
in a real migration, not here.

Usage:
    DATABASE_URL=postgresql+psycopg://... uv run python -m scripts.init_db
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import get_engine
from app.db.tables import Base

# (table, column, type) — kept in sync with app/db/tables.py.
_ADDITIVE_COLUMNS = [
    ("cleaned_items", "author", "TEXT"),
    ("cleaned_items", "retrieved_at", "TIMESTAMPTZ"),
]


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for table, column, coltype in _ADDITIVE_COLUMNS:
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}")
            )
    print("Schema created (cleaned_items + council_snapshots + predictions + prompt_overrides + indexes).")
    print(f"Additive columns ensured: {', '.join(f'{t}.{c}' for t, c, _ in _ADDITIVE_COLUMNS)}.")


if __name__ == "__main__":
    main()
