"""
Configuration Settings

Centralized configuration management using environment variables.
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    environment: str = Field(default="dev", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Onspring Configuration
    onspring_api_url: str = Field(
        default="https://api.onspring.com/v2",
        alias="ONSPRING_API_URL"
    )
    onspring_api_key_secret: str = Field(
        ...,
        alias="ONSPRING_API_KEY_SECRET",
        description="AWS Secrets Manager secret name for Onspring API key"
    )

    # ARRMS Configuration
    arrms_api_url: str = Field(
        ...,
        alias="ARRMS_API_URL",
        description="ARRMS API base URL"
    )
    arrms_api_key_secret: str = Field(
        ...,
        alias="ARRMS_API_KEY_SECRET",
        description="AWS Secrets Manager secret name for ARRMS API key"
    )

    # AWS Configuration
    aws_region: Optional[str] = Field(
        default=None,
        alias="AWS_REGION"
    )

    # Operational Settings
    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retry attempts for failed requests"
    )
    batch_size: int = Field(
        default=100,
        description="Default batch size for bulk operations"
    )

    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def get_settings() -> Settings:
    """
    Get application settings instance.

    Returns:
        Settings instance with values loaded from environment
    """
    return Settings()
