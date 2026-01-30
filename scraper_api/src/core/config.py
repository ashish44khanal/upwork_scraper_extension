from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Scraper API"
    API_V1_STR: str = "/api/v1"
    # Upwork session (optional; scraper also reads UPWORK_USERNAME, UPWORK_PASSWORD from env)
    UPWORK_COOKIES_PATH: Optional[str] = "cookies.json"
    UPWORK_PROFILE_URL: Optional[str] = "https://www.upwork.com/ab/account-security/"

    model_config = SettingsConfigDict(case_sensitive=True)


settings = Settings()
