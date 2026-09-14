"""Settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "tree-of-life-backend"
    app_env: str = "development"
    debug: bool = True

    database_url: str = "postgresql+psycopg2://tol:tol@localhost:5432/tree_of_life"

    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    gbif_user: str = ""
    gbif_password: str = ""
    iucn_api_token: str = ""
    opentree_api_base: str = "https://api.opentreeoflife.org/v3"

    data_dir: str = "./data"
    col_dataset_version: str = ""
    gbif_dataset_version: str = ""
    opentree_synthesis_version: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
