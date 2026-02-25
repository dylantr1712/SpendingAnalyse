from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://app:app@db:5432/spending"


settings = Settings()
