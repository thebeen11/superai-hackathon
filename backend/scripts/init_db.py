"""Create the database schema (Req 14, 15).

MVP bootstrap via SQLAlchemy `create_all`. For production, an Alembic migration can be
generated from the same `tables.Base` metadata.

Usage:
    DATABASE_URL=postgresql+psycopg://... uv run python -m scripts.init_db
"""
from __future__ import annotations

from app.db.session import get_engine
from app.db.tables import Base


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Schema created (cleaned_items + council_snapshots + predictions + prompt_overrides + indexes).")


if __name__ == "__main__":
    main()
