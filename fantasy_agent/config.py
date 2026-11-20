from pathlib import Path
from typing import Mapping
import os

from dotenv import dotenv_values
from pydantic import BaseModel, Field, SecretStr


class Config(BaseModel):
    gemini_api_key: SecretStr = SecretStr("")
    tavily_api_key: SecretStr = SecretStr("")
    gemini_model: str = "auto"
    gemini_thinking_level: str = "high"
    league_cache_seconds: int = Field(300, ge=10, le=3600)
    cache_path: Path = Path(".cache/fantasy.sqlite3")
    sleeper_username: str = ""
    sleeper_league_id: str = ""
    stats_cache_seconds: int = Field(21600, ge=300, le=86400)
    trade_min_team_coverage: float = Field(.8, ge=.5, le=1)
    dynasty_max_age_days: int = Field(30, ge=1, le=60)

    @classmethod
    def load(cls, secrets: Mapping | None = None):
        # Read afresh on reruns without mutating process environment. Real process
        # variables and deployment secrets take precedence over the local file.
        values = {**dotenv_values(), **os.environ}
        if secrets:
            values.update(dict(secrets))
        return cls(**{key: values[key.upper()] for key in cls.model_fields if key.upper() in values})
