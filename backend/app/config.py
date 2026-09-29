from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://raceday:raceday@localhost:5432/raceday"

    # Strava — https://www.strava.com/settings/api
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_webhook_verify_token: str = ""
    strava_webhook_subscription_id: int | None = None

    openai_api_key: str = ""

    # Fernet key for Strava tokens at rest
    token_encryption_key: str
    session_secret: str
    session_expire_days: int = 30

    # Public origin; used for the OAuth redirect and post-login redirects
    app_base_url: str = "http://localhost:5173"

    model_config = {
        "env_file": ("../.env", ".env"),
        "env_file_encoding": "utf-8",
        "env_ignore_empty": True,
        "extra": "ignore",
    }

    @property
    def secure_cookies(self) -> bool:
        return self.app_base_url.startswith("https://")


settings = Settings()
