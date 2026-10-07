import logging

from sqlalchemy import inspect, text

from app.database import engine

logger = logging.getLogger(__name__)


def ensure_schema() -> None:
    """Lightweight SQLite migrations for dev (no Alembic)."""
    inspector = inspect(engine)
    if "documents" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("documents")}
    if "embedding_model" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE documents ADD COLUMN embedding_model VARCHAR(128)"))
        logger.info("Added documents.embedding_model column")
