import pytest
from fantasy_agent.config import Config
from fantasy_agent.storage import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.sqlite3")


@pytest.fixture
def config(tmp_path):
    return Config(cache_path=tmp_path / "test.sqlite3", gemini_api_key="test-key",
                  tavily_api_key="test-key")
