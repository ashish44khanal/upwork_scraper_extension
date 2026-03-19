import sys
import os
from pathlib import Path

# Add the project root to the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables from .env file (scraper_api/.env)
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from fastapi import FastAPI
from src.api.v1.api import api_router
from src.core.config import settings
import asyncio
import logging
import sys

# Configure basic logging for visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger("scraper_api")

from contextlib import asynccontextmanager
from src.services.redis_stream_reader import RedisStreamReader
from src.core.database import init_db
from src.models import job_card # Ensure models are loaded for init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Note: Database initialization is handled by extraction_service migrations
    # to maintain a single source of truth in the shared database.
    # logger.info("Initializing database...")
    # await init_db()
    
    # Start the Redis Stream Reader in the background
    logger.info("Starting Redis Stream Reader...")
    reader = RedisStreamReader()
    task = asyncio.create_task(reader.run())
    yield
    # Cleanup (optional, depend on how run() is implemented)
    # task.cancel()

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

app.include_router(api_router, prefix=settings.API_V1_STR)


def main():
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
