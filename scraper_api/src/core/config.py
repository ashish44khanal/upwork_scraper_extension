from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Scraper API"
    API_V1_STR: str = "/api/v1"
    # Upwork: scraper reads UPWORK_USERNAME, UPWORK_PASSWORD from env for login each run

    model_config = SettingsConfigDict(case_sensitive=True)


settings = Settings()
