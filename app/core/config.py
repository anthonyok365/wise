"""Core configuration management for the Hiring Signal Detection System."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""
    
    host: str = Field(default="localhost", description="PostgreSQL host")
    port: int = Field(default=5432, description="PostgreSQL port")
    user: str = Field(default="hiring_signal", description="PostgreSQL user")
    password: str = Field(default="hiring_signal_pass", description="PostgreSQL password")
    database: str = Field(default="hiring_signal_db", description="Database name")
    
    @property
    def async_url(self) -> str:
        """Get async database URL for asyncpg."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def sync_url(self) -> str:
        """Get sync database URL for migrations."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class RedisSettings(BaseSettings):
    """Redis configuration settings."""
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    db: int = Field(default=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password")
    
    @property
    def url(self) -> str:
        """Get Redis URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class AISettings(BaseSettings):
    """AI service configuration settings."""
    
    provider: str = Field(default="ollama", description="AI provider: ollama, huggingface")
    ollama_url: str = Field(default="http://localhost:11434", description="Ollama API URL")
    ollama_model: str = Field(default="mistral", description="Ollama model name")
    huggingface_token: Optional[str] = Field(default=None, description="HuggingFace API token")
    huggingface_model: str = Field(default="mistralai/Mistral-7B-Instruct-v0.2", description="HuggingFace model")
    request_timeout: int = Field(default=60, description="AI request timeout in seconds")
    
    @property
    def use_ollama(self) -> bool:
        """Check if using Ollama as primary provider."""
        return self.provider == "ollama"


class ScraperSettings(BaseSettings):
    """Web scraper configuration settings."""
    
    timeout: int = Field(default=30000, description="Page load timeout in milliseconds")
    navigation_timeout: int = Field(default=60000, description="Navigation timeout in milliseconds")
    delay_between_requests: float = Field(default=2.0, description="Delay between requests in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retries for failed requests")
    user_agent_rotation: bool = Field(default=True, description="Enable user agent rotation")
    headless: bool = Field(default=True, description="Run browser in headless mode")
    viewport_width: int = Field(default=1920, description="Browser viewport width")
    viewport_height: int = Field(default=1080, description="Browser viewport height")


class SchedulerSettings(BaseSettings):
    """Background job scheduler configuration settings."""
    
    scraper_interval_hours: int = Field(default=6, description="Hours between scraper runs")
    validator_interval_hours: int = Field(default=24, description="Hours between validator runs")
    scoring_interval_hours: int = Field(default=1, description="Hours between scoring updates")
    enabled: bool = Field(default=True, description="Enable background scheduler")


class AppSettings(BaseSettings):
    """Main application configuration settings."""
    
    app_name: str = Field(default="Hiring Signal Detector", description="Application name")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ai: AISettings = Field(default_factory=AISettings)
    scraper: ScraperSettings = Field(default_factory=ScraperSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)


@lru_cache
def get_settings() -> AppSettings:
    """Get cached application settings."""
    return AppSettings()
