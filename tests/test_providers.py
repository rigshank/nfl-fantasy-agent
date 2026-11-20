from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from pydantic import SecretStr
from fantasy_agent.integrations.gemini import Gemini
from fantasy_agent.integrations.research import ProviderUnavailable, Research


def gemini_client():
    client = Mock()
    client.models.get.return_value = SimpleNamespace(supported_actions=["generateContent"],input_token_limit=1048576,output_token_limit=65536)
    client.models.count_tokens.return_value = SimpleNamespace(total_tokens=500)
    client.models.generate_content.return_value = SimpleNamespace(text="Evidence-based answer",usage_metadata=SimpleNamespace(
        total_token_count=100,prompt_token_count=50,candidates_token_count=30,thoughts_token_count=20))
    return client


def usage_client(account=None):
    client=Mock()
    response=Mock()
    response.json.return_value={"account":account or {"current_plan":"Researcher","plan_usage":5,"plan_limit":1000,"paygo_limit":None},"key":{"usage":5,"limit":None}}
    client.get.return_value=response
    return client


def test_quality_reasoning_has_no_custom_token_or_context_budget(config,store):
    client=gemini_client()
    answer=Gemini(config,store,client).answer({"roster":"facts"},"Analyze thoroughly",[{"role":"user","content":"x"*10000}])
    kwargs=client.models.generate_content.call_args.kwargs
    assert answer == "Evidence-based answer"
    assert kwargs["model"] == "gemini-4-hydrogen"
    assert kwargs["config"].max_output_tokens is None
    assert kwargs["config"].thinking_config.thinking_budget is None
    assert kwargs["config"].thinking_config.thinking_level.value == "HIGH"
    assert "x"*10000 in kwargs["contents"]
    assert store.usage()[0]["tokens"] == 100


def test_injury_and_quantile_instructions_distinguish_missing_evidence(config,store):
    client=gemini_client()
    Gemini(config,store,client).answer({"injury_status":None},"Is this player healthy?",[])
    instruction=client.models.generate_content.call_args.kwargs["config"].system_instruction
    assert "not medical clearance" in instruction
    assert "Absence of an injury report" in instruction
    assert "historical game-score quantiles" in instruction


def test_actual_provider_context_limit_is_respected(config,store):
    client=gemini_client()
    client.models.count_tokens.return_value.total_tokens=1048577
    with pytest.raises(ProviderUnavailable,match="actual context limit"):
        Gemini(config,store,client).answer({},"question",[])
    client.models.generate_content.assert_not_called()


def test_verified_free_fallback_and_no_paid_model_request(config,store):
    client=gemini_client()
    config.gemini_model="gemini-4-carbon"
    answer=Gemini(config,store,client).answer({},"question",[])
    assert "fallback gemini-4-hydrogen" in answer
    assert all(call.kwargs["model"] != "gemini-4-carbon" for call in client.models.get.call_args_list)


def test_unavailable_current_model_uses_verified_fallback(config,store):
    client=gemini_client()
    class Missing(Exception):code=404
    metadata=client.models.get.return_value
    client.models.get.side_effect=[Missing("not available"),metadata]
    answer=Gemini(config,store,client).answer({},"question",[])
    assert "fallback gemini-3.8-flash" in answer
    assert client.models.generate_content.call_args.kwargs["model"] == "gemini-3.8-flash"


def test_generation_not_found_also_uses_accessible_free_fallback(config,store):
    client=gemini_client()
    class Missing(Exception):code=404
    response=client.models.generate_content.return_value
    client.models.generate_content.side_effect=[Missing("generation endpoint unavailable"),response]
    answer=Gemini(config,store,client).answer({},"question",[])
    assert "fallback gemini-3.8-flash" in answer
    assert client.models.generate_content.call_count==2


def test_plain_explanation_uses_verified_fallback_when_model_is_busy(config,store):
    client=gemini_client()
    class Busy(Exception):code=503
    response=client.models.generate_content.return_value
    client.models.generate_content.side_effect=[Busy("high demand"),response]
    answer=Gemini(config,store,client).answer({},"question",[])
    assert "HTTP 503" in answer and "fallback gemini-3.8-flash" in answer
    assert client.models.generate_content.call_args.kwargs["model"]=="gemini-3.8-flash"


def test_provider_quota_failure_is_shown_without_quota_hopping(config,store):
    client=gemini_client()
    class Quota(Exception):code=429
    client.models.generate_content.side_effect=Quota("actual free-tier quota exhausted")
    with pytest.raises(ProviderUnavailable,match="actual free-tier quota"):
        Gemini(config,store,client).answer({},"question",[])
    assert client.models.generate_content.call_count == 1


def test_missing_key_error_and_secret_redaction(config,store):
    client=gemini_client()
    client.models.generate_content.side_effect=RuntimeError("bad test-key")
    with pytest.raises(ProviderUnavailable) as exc:
        Gemini(config,store,client).answer({},"question",[])
    assert "test-key" not in str(exc.value)
    config.gemini_api_key=SecretStr("")
    with pytest.raises(ProviderUnavailable,match="missing"):
        Gemini(config,store,client).answer({},"question",[])


def test_identical_gemini_evidence_is_cached(config,store):
    client=gemini_client();analyst=Gemini(config,store,client)
    analyst.answer({"as_of":"first"},"question",[])
    analyst.answer({"as_of":"first"},"question",[])
    analyst.answer({"as_of":"second"},"question",[])
    assert client.models.generate_content.call_count==2


def test_tavily_real_quota_check_cache_and_non_whitelisted_sources(config,store):
    search=Mock()
    search.search.return_value={"results":[{"title":"Team reporter","url":"https://www.bengals.com/news/report","content":"observed role","published_date":"2026-11-19"},
                                           {"title":"bad","url":"javascript:alert(1)"}]}
    quota=usage_client()
    research=Research(config,store,search,quota)
    result=research.search("Player role")
    research.search("Player role")
    assert len(result.sources)==1 and result.sources[0].published_at=="2026-11-19"
    assert search.search.call_count==1 and quota.get.call_count==1
    assert search.search.call_args.kwargs["search_depth"]=="basic"
    assert search.search.call_args.kwargs["include_domains_mode"]=="prefer"


@pytest.mark.parametrize("account,error",[
    ({"current_plan":"Researcher","plan_usage":1000,"plan_limit":1000},"exhausted"),
    ({"current_plan":"Bootstrap","plan_usage":0,"plan_limit":4000},"free Researcher"),
    ({"current_plan":"Researcher","plan_usage":0,"plan_limit":1000,"paygo_limit":50},"pay-as-you-go"),
])
def test_tavily_stops_at_actual_quota_or_paid_account(config,store,account,error):
    search=Mock()
    with pytest.raises(ProviderUnavailable,match=error):
        Research(config,store,search,usage_client(account)).search("news")
    search.search.assert_not_called()


def test_research_many_deduplicates_queries(config,store):
    search=Mock();search.search.return_value={"results":[]}
    Research(config,store,search,usage_client()).search_many(["role","role","injury"])
    assert search.search.call_count==2
