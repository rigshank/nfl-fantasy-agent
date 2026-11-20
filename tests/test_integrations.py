from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
import pytest

from tests.fixture_roster import demo_snapshot
from fantasy_agent.models import Snapshot
from fantasy_agent.integrations.gemini import Gemini
from fantasy_agent.integrations.research import ProviderUnavailable, Research
from fantasy_agent.integrations.sleeper import DataUnavailable, Sleeper
from fantasy_agent.service import LeagueService, compact_context
from fantasy_agent.storage import BudgetExceeded


def fixture_api(request):
    path = request.url.path.replace("/v1", "")
    responses = {
        "/state/nfl": {"season": "2026", "week": 9, "display_week": 9},
        "/league/123456": {"name": "Fixture league", "season": "2026", "sport": "nfl",
                            "settings": {"type": 2}, "scoring_settings": {"rec": 1},
                            "roster_positions": ["QB", "BN"]},
        "/league/123456/users": [{"user_id": "user", "display_name": "Manager"}],
        "/league/123456/rosters": [{"roster_id": 1, "owner_id": "user", "players": ["CHI", "missing"],
                                    "starters": ["missing"], "reserve": ["reserve-only"]}],
        "/players/nfl": {"CHI": {"full_name": "Chicago Bears", "position": "DEF"}},
        "/league/123456/matchups/9": [], "/league/123456/transactions/9": [],
        "/league/123456/traded_picks": [], "/league/123456/drafts": [],
    }
    return httpx.Response(200, json=responses[path])


def test_refresh_core_catalog_cache_and_unknown_ids(config, store):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return fixture_api(request)
    client = Sleeper(store, httpx.Client(transport=httpx.MockTransport(handler)))
    service = LeagueService(config, store, client)
    first = service.load("123456", force=True)
    second = service.load("123456", force=True)
    assert second.refreshed_at >= first.refreshed_at
    assert calls.count("/v1/players/nfl") == 1
    assert calls.count("/v1/league/123456/rosters") == 2
    assert first.players["missing"].known is False
    assert first.players["reserve-only"].known is False
    assert first.league_type == "dynasty" and first.rosters[0].manager == "Manager"


def test_optional_failure_is_flagged_and_failed_core_preserves_cache(config, store):
    broken = set()
    def handler(request):
        if request.url.path in broken:
            return httpx.Response(404, json={})
        return fixture_api(request)
    client = Sleeper(store, httpx.Client(transport=httpx.MockTransport(handler)))
    service = LeagueService(config, store, client)
    broken.add("/v1/league/123456/traded_picks")
    first = service.load("123456", force=True)
    assert any("traded_picks unavailable" in w for w in first.warnings)
    broken.add("/v1/league/123456/rosters")
    with pytest.raises(DataUnavailable):
        service.load("123456", force=True)
    assert Snapshot.model_validate(store.get("snapshot:123456")[0]).refreshed_at == first.refreshed_at


def test_transient_http_retry_is_bounded(store, monkeypatch):
    monkeypatch.setattr("fantasy_agent.integrations.sleeper.time.sleep", lambda _: None)
    statuses = iter([429, 503, 200])
    client = Sleeper(store, httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(next(statuses), json={"ok": True}, headers={"Retry-After": "0"}))))
    assert client.get("/state/nfl")[0] == {"ok": True}
    assert store.usage()[0]["requests"] == 3


def test_context_only_includes_named_free_players():
    context = compact_context(demo_snapshot(), 1, "Research Demo QB 17")
    assert context["named_free_agents_included"] == 1
    assert "demo-16" in context["players"]
    assert "demo-17" not in context["players"]


def test_sleeper_actual_http_error_is_preserved(store):
    client=Sleeper(store,httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(404))))
    with pytest.raises(DataUnavailable,match="HTTP 404"):
        client.get("/league/123456")
