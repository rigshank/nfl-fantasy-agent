from concurrent.futures import ThreadPoolExecutor
import time
import pytest
from fantasy_agent.storage import BudgetExceeded


def test_cache_ttl_and_stale_access(store):
    store.put("x", {"a": 1}, -1)
    assert store.get("x") is None
    assert store.get("x", stale=True)[0] == {"a": 1}


def test_atomic_reservations_cannot_overrun_budget(store):
    def attempt(_):
        try:
            store.reserve("test", [(0, 3)])
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(attempt, range(12))) == 3


def test_usage_records_actual_tokens_without_reservations(store):
    event = store.record_request("gemini")
    store.record_tokens(event, 20, 10, 5, 5)
    assert store.usage()[0]["tokens"] == 20
    assert store.usage()[0]["requests"] == 1
