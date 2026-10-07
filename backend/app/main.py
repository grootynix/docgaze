import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.db_migrate import ensure_schema
from app.logging_config import setup_logging
from app.routers import chat, documents

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    from app.services.observability import get_langfuse

    lf = get_langfuse()
    logger.info(
        "DocGaze started llm_provider=%s openai=%s langfuse=%s",
        settings.llm_provider,
        "enabled" if settings.openai_api_key else "disabled",
        "enabled" if lf is not None else "disabled",
    )
    yield


app = FastAPI(title="DocGaze API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health")
async def health():
    from app.schemas import HealthOut
    from app.services.llm import check_llm_health

    db_ok = True
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    llm_ok, provider, openai_ok, openai_error, ollama_ok, ollama_error = await check_llm_health()
    status = "ok" if db_ok and llm_ok else "degraded"
    return HealthOut(
        status=status,
        database=db_ok,
        llm_provider=provider,
        openai=openai_ok,
        openai_error=openai_error,
        ollama=ollama_ok,
        ollama_error=ollama_error,
    )
