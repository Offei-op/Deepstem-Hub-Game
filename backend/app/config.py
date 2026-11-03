from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator, Field
from typing import Literal
from urllib.parse import urlparse


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./data/studio.db'
    app_origin: str = 'http://localhost:5173'
    preview_origin: str = 'http://127.0.0.1:8001'
    session_secret: str = 'local-only-change-this-secret-before-an-event-12345'
    preview_secret: str = 'local-preview-secret-change-before-an-event-12345'
    admin_password_hash: str = ''
    cookie_secure: bool = False
    environment: Literal['development', 'production', 'test'] = 'development'
    session_hours: int = Field(default=6, ge=1, le=24)
    primary_ai_provider: str = 'mock'
    fallback_ai_provider: str = ''
    openai_api_key: str = ''
    openai_model: str = ''
    gemini_api_key: str = ''
    gemini_model: str = ''
    # USD per million tokens. Empty configuration disables the paid provider.
    openai_input_price: float | None = None
    openai_output_price: float | None = None
    gemini_input_price: float | None = None
    gemini_output_price: float | None = None
    provider_timeout_seconds: int = Field(default=90, ge=1, le=180)
    safe_retries: int = 1
    max_html_bytes: int = Field(default=180_000, ge=1000, le=250_000)
    max_prompt_chars: int = Field(default=3000, ge=100, le=3000)
    reference_image_token_reserve: int = Field(default=6000, ge=3000, le=50000)
    preview_token_seconds: int = Field(default=900, ge=60, le=3600)
    provider_config_path: str = './data-private/providers.json'
    local_organizer_token_hash: str = ''
    local_organizer_token_expires: int = 0
    frontend_dir: str = ''

    @field_validator('openai_input_price', 'openai_output_price', 'gemini_input_price', 'gemini_output_price', mode='before')
    @classmethod
    def blank_prices(cls, value):
        return None if value == '' else value

    @model_validator(mode='after')
    def valid(self):
        app, preview = urlparse(self.app_origin), urlparse(self.preview_origin)
        if any(u.scheme not in {'http', 'https'} or not u.hostname or u.path or u.query or u.fragment or u.username
               for u in [app, preview]):
            raise ValueError('Origins must be absolute HTTP(S) origins without paths, credentials or trailing slashes')
        if (app.scheme, app.netloc) == (preview.scheme, preview.netloc):
            raise ValueError('Preview must have a separate origin')
        if not 0 <= self.safe_retries <= 2:
            raise ValueError('SAFE_RETRIES must be 0–2')
        if self.environment == 'production':
            if not self.cookie_secure or app.scheme != 'https' or preview.scheme != 'https':
                raise ValueError('Production requires HTTPS origins and COOKIE_SECURE=true')
            if app.hostname == preview.hostname:
                raise ValueError('Production preview needs a separate cookieless hostname')
            if any('local-' in x or len(x) < 32 for x in [self.session_secret, self.preview_secret]):
                raise ValueError('Set independent random production secrets of at least 32 characters')
            if not self.admin_password_hash:
                raise ValueError('ADMIN_PASSWORD_HASH is required')
            if not self.admin_password_hash.startswith('$argon2id$') or self.session_secret == self.preview_secret:
                raise ValueError('Use an Argon2id admin hash and independent session/preview secrets')
            if self.primary_ai_provider == 'mock':
                raise ValueError('Mock provider cannot be enabled in production')
        return self


@lru_cache
def get_settings():
    return Settings()
