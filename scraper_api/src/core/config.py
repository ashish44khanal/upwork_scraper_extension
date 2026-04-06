from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Scraper API"
    API_V1_STR: str = "/api/v1"
    # Upwork: scraper reads UPWORK_USERNAME, UPWORK_PASSWORD from env for login each run
    UPWORK_USERNAME: Optional[str] = None
    UPWORK_PASSWORD: Optional[str] = None
    
    # Browser settings
    CHROME_REMOTE_HOST: Optional[str] = None
    CHROME_REMOTE_PORT: Optional[int] = None

    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_STREAM_NAME: str = "upwork_jobs_stream"
    REDIS_JOBS_STREAM_NAME: str = "upwork_jobs_stream"  # Standard name
    REDIS_GROUP_NAME: str = "scraper_group"
    REDIS_CONSUMER_NAME: str = "scraper_consumer_1"
    
    # Postgres settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "upwork_db"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # New extraction stream for downstream processing (published per card)
    EXTRACTION_STREAM_NAME: str = "upwork_job_extraction_stream"
    REDIS_EXTRACTION_STREAM_NAME: str = "upwork_job_extraction_stream" # Standard name
    
    # Default search pages
    DEFAULT_SCRAPE_PAGES: int = 1
    
    # Storage settings
    STORAGE_DIR: str = "storage"

    # Redis Stream Reliability Settings
    REDIS_MAX_RETRIES: int = 5
    REDIS_DLQ_STREAM_NAME: str = "upwork_failed_tasks_stream"
    REDIS_STREAM_MAXLEN: int = 10000
    REDIS_CLAIM_IDLE_TIME_MS: int = 900000  # 15 minutes

    # API Key for extraction logic
    GEMINI_API_KEY: Optional[str] = None
    
    # Port configuration
    PORT: int = 8000

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
