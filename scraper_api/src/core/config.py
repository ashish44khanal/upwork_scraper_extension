from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Scraper API"
    API_V1_STR: str = "/api/v1"
    # Upwork: scraper reads UPWORK_USERNAME, UPWORK_PASSWORD from env for login each run

    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_STREAM_NAME: str = "upwork_jobs_stream"
    REDIS_GROUP_NAME: str = "scraper_group"
    REDIS_CONSUMER_NAME: str = "scraper_consumer_1"
    
    # Postgres settings
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "upwork_scraper_db"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    # New extraction stream for downstream processing (published per card)
    EXTRACTION_STREAM_NAME: str = "upwork_job_extraction_stream"
    
    # Default search pages
    DEFAULT_SCRAPE_PAGES: int = 1
    
    # Storage settings
    STORAGE_DIR: str = "storage"

    model_config = SettingsConfigDict(case_sensitive=True)


settings = Settings()
