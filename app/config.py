from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    environment: str = 'development'
    database_url: str = 'sqlite:///./stockroom.db'
    allowed_origins: list[str] = ['http://127.0.0.1:8000', 'http://localhost:8000']
    allowed_hosts: list[str] = ['127.0.0.1', 'localhost', 'testserver']
    secure_cookies: bool = False
    session_hours: int = 8
    action_token_minutes: int = 30
    auth_limit: int = 15
    api_limit: int = 300
    rate_window_seconds: int = 60
    railway_environment: str | None = None
    railway_public_domain: str | None = None

    @model_validator(mode='after')
    def production_safety(self):
        if self.environment not in {'development', 'test', 'production'}:
            raise ValueError('Invalid environment')
        if self.environment == 'production':
            if self.railway_environment:
                if self.railway_public_domain:
                    self.allowed_hosts = [self.railway_public_domain]
                    self.allowed_origins = [f'https://{self.railway_public_domain}']
                else:
                    self.allowed_hosts = ['*.up.railway.app']
                    self.allowed_origins = []
            if not self.secure_cookies or not self.database_url.startswith('postgresql'):
                raise ValueError('Production requires PostgreSQL and secure cookies')
            if '*' in self.allowed_hosts or not self.allowed_hosts:
                raise ValueError('Production requires explicit allowed hosts')
            if any(not o.startswith('https://') for o in self.allowed_origins):
                raise ValueError('Production CORS origins must use HTTPS')
        return self


@lru_cache
def get_settings():
    return Settings()
