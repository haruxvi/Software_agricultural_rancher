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


settings = Settings()
