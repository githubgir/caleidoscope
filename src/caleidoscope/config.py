"""Configuration management for Caleidoscope."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a single data source."""

    name: str
    entity: str | None = None
    enabled: bool = True
    urls: list[str] = Field(default_factory=list)
    category_default: str | None = None


class Config(BaseModel):
    """Main application configuration."""

    db_path: str = "data/caleidoscope.db"
    sources: list[SourceConfig] = Field(default_factory=list)
    digest_dir: str = "digests"
    anthropic_api_key: str | None = None
    rate_limit_seconds: float = 2.0


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file and merge with environment variables.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Config object with merged settings from file and environment
    """
    # Load YAML config
    config_data: dict[str, Any] = {}
    config_file = Path(config_path)

    if config_file.exists():
        with open(config_file) as f:
            config_data = yaml.safe_load(f) or {}

    # Override with environment variables
    if "CALEIDOSCOPE_DB" in os.environ:
        config_data["db_path"] = os.environ["CALEIDOSCOPE_DB"]

    if "ANTHROPIC_API_KEY" in os.environ:
        config_data["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]

    return Config(**config_data)
