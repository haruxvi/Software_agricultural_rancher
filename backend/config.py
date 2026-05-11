from pydantic import field_validator, model_validator
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

    @model_validator(mode="after")
    def _require_production_secrets(self) -> "Settings":
        if self.environment == "production":
            missing = [
                name
                for name, val in [
                    ("SUPABASE_JWT_SECRET", self.supabase_jwt_secret),
                    ("SUPABASE_URL", self.supabase_url),
                    ("DATABASE_URL", self.database_url),
                ]
                if not val
            ]
            if missing:
                raise ValueError(
                    "Variables de entorno requeridas en producción no configuradas: "
                    + ", ".join(missing)
                )
        return self


settings = Settings()
