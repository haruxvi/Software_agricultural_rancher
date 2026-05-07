from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://user:password@localhost:5432/agrovista"

    sh_client_id: str = ""
    sh_client_secret: str = ""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""

    environment: str = "development"
    log_level: str = "INFO"

    cors_origins: list[str] = ["http://localhost:8000"]
    allowed_hosts: list[str] = ["*"]

    @field_validator("cors_origins", "allowed_hosts", mode="before")
    @classmethod
    def _parse_comma_list(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v  # type: ignore[return-value]


settings = Settings()
