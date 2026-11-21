from types import SimpleNamespace
from datetime import timedelta
from unittest.mock import Mock, patch
import pytest
from google.genai import types
from fantasy_agent.agent import AgentTools, Analyst
from fantasy_agent.integrations.gemini import Gemini, minute_retry
from fantasy_agent.integrations.research import ProviderUnavailable
from tests.fixture_stats import trade_demo
from tests.test_providers import gemini_client
from fantasy_agent.models import utcnow
from fantasy_agent.service import compact_context


def model_response(parts):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model",parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(total_token_count=100,prompt_token_count=60,candidates_token_count=20,thoughts_token_count=20))


def test_manual_loop_preserves_signatures_ids_and_parallel_results(config,store):
    client=gemini_client()
    first=model_response([types.Part(function_call=types.FunctionCall(name="get_league",args={},id="one"),thought_signature=b"signed"),
                          types.Part(function_call=types.FunctionCall(name="team_needs",args={},id="two"))])
    client.models.generate_content.side_effect=[first,model_response([types.Part(text="Evidence-based action plan")])]
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[]
    dispatcher.call.return_value={"result":{"observed":True}}
    answer=Gemini(config,store,client).run_agent({},"Help my team",[],dispatcher)
    assert answer=="Evidence-based action plan" and dispatcher.call.call_count==2
    sent=client.models.generate_content.call_args.kwargs
    assert sent["contents"][1] is first.candidates[0].content
    assert sent["contents"][1].parts[0].thought_signature==b"signed"
    assert [p.function_response.id for p in sent["contents"][2].parts]==["one","two"]
    assert sent["contents"][2].role=="user"
    assert sent["config"].max_output_tokens is None
    assert sent["config"].automatic_function_calling.disable
    assert store.usage()[0]["requests"]==2


def test_repeated_tool_batch_stops_no_progress(config,store):
    client=gemini_client();client.models.generate_content.return_value=model_response([types.Part(function_call=types.FunctionCall(name="get_league",args={}))])
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[];dispatcher.call.return_value={"result":{}}
    with pytest.raises(ProviderUnavailable,match="repeated"):
        Gemini(config,store,client).run_agent({},"Help",[],dispatcher)
    assert dispatcher.call.call_count==1


def test_transient_model_failure_retries_same_model_and_records_requests(config,store):
    client=gemini_client()
    class Busy(Exception):code=503
    client.models.generate_content.side_effect=[Busy("high demand"),model_response([types.Part(text="Answer")])]
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[]
    with patch("fantasy_agent.integrations.gemini.time.sleep"):
        assert Gemini(config,store,client).run_agent({},"Question",[],dispatcher)=="Answer"
    assert store.usage()[0]["requests"]==2
    assert {c.kwargs["model"] for c in client.models.generate_content.call_args_list}=={"gemini-4-hydrogen"}


def test_persistently_unavailable_model_falls_back_before_any_tools(config,store):
    client=gemini_client()
    class Busy(Exception):code=503
    client.models.generate_content.side_effect=[Busy("high demand")]*3+[model_response([types.Part(text="Answer")])]
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[]
    with patch("fantasy_agent.integrations.gemini.time.sleep"):
        answer=Gemini(config,store,client).run_agent({},"Question",[],dispatcher)
    assert "HTTP 503" in answer and "fallback gemini-3.8-flash" in answer
    assert client.models.generate_content.call_args.kwargs["model"]=="gemini-3.8-flash"


def test_agent_quota_does_not_retry_or_switch_models(config,store):
    client=gemini_client()
    class Quota(Exception):code=429
    client.models.generate_content.side_effect=Quota("quota exhausted")
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[]
    with pytest.raises(ProviderUnavailable,match="quota exhausted"):
        Gemini(config,store,client).run_agent({},"Question",[],dispatcher)
    assert client.models.generate_content.call_count==1


def test_only_provider_advised_minute_reset_can_retry():
    error=SimpleNamespace(code=429,details={"error":{"details":[
        {"violations":[{"quotaId":"GenerateContentInputTokensPerModelPerMinute-FreeTier","quotaValue":"250000"}]},
        {"retryDelay":"54s"}]}})
    assert minute_retry(error,100000)==55
    assert minute_retry(error,250001) is None
    error.details["error"]["details"][0]["violations"][0]["quotaId"]="GenerateRequestsPerDay"
    assert minute_retry(error,100) is None


def test_named_comparison_bootstraps_evidence_without_model_roundtrip(config,store):
    s,d=trade_demo()
    client=Mock();client.load.return_value=d;client.csv.return_value=(d.schedule,d.sources[0])
    tools=AgentTools(config,store,Mock(),s,1,data_client=client)
    names=[s.players[pid].name for pid in ("demo-1","demo-8","demo-24")]
    evidence=tools.bootstrap("Should I trade "+" and ".join(names)+"? Newer pick included.")
    result=evidence["compare_players"]["result"]
    assert set(result["matches"])==set(names)
    assert result["ambiguous_queries"]==[]
    assert len(result["evidence"]["result"]["players"])==3
    assert {r["tool"] for r in tools.records}>={"get_league","compare_players","player_evidence"}
    assert "context_scope" in evidence["get_league"]["result"]
    # Expanding the initial focused context must not trip the duplicate guard.
    assert not tools.call("get_league",{})["cached_this_turn"]


def test_batched_lookup_keeps_ambiguity_and_does_not_expand_missing_names(config,store):
    s,d=trade_demo();tools=AgentTools(config,store,Mock(),s,1)
    missing=tools.call("compare_players",{"queries":["No Such Player"]})["result"]
    assert missing["unresolved_queries"]==["No Such Player"] and missing["evidence"] is None
    with patch.object(tools,"evidence",return_value={}):
        result=tools.call("compare_players",{"queries":["Demo"]})["result"]
    assert result["ambiguous_queries"]==["Demo"]
    assert len(result["matches"]["Demo"])==len(s.players)


def test_tool_round_limit_forces_final_answer_and_retains_evidence(config,store):
    config.gemini_tool_rounds=1
    client=gemini_client()
    client.models.generate_content.side_effect=[
        model_response([types.Part(function_call=types.FunctionCall(name="get_league",args={}))]),
        model_response([types.Part(text="Advice with missing evidence disclosed")])]
    dispatcher=Mock();dispatcher.declarations.return_value=[]
    dispatcher.call.return_value={"result":{"observed":True}}
    answer=Gemini(config,store,client).run_agent({},"Question",[],dispatcher)
    assert "Advice" in answer and client.models.generate_content.call_count==2
    assert client.models.generate_content.call_args.kwargs["config"].tools is None
    assert dispatcher.call.call_count==1
    assert "observed" in str(client.models.generate_content.call_args.kwargs["contents"])


def test_seeded_named_question_can_finish_in_one_generation(config,store):
    s,d=trade_demo();service=Mock();service.load.return_value=s
    client=gemini_client();client.models.generate_content.return_value=model_response([types.Part(text="Conditional recommendation")])
    data_client=Mock();data_client.load.return_value=d;data_client.csv.return_value=(d.schedule,d.sources[0])
    with patch("fantasy_agent.agent.NFLVerse",return_value=data_client):
        _,message=Analyst(config,store,service,Gemini(config,store,client)).run(
            s,1,"Compare "+s.players["demo-1"].name+" and "+s.players["demo-8"].name,[])
    assert client.models.generate_content.call_count==1
    assert {r["tool"] for r in message["tools"]}>={"get_league","player_evidence"}
    prompt=client.models.generate_content.call_args.kwargs["contents"][0].parts[0].text
    assert "initial_evidence" in prompt and "dynasty" in prompt


def test_model_summaries_keep_every_candidate_and_full_ui_evidence(config,store):
    s,d=trade_demo();tools=AgentTools(config,store,Mock(),s,1)
    signals=[{"player_id":str(i),"score":i,"label":"growth","confidence":"low","recent_games":3,"prior_games":3,
              "changes":[{"metric":"targets","prior":2,"recent":4,"change":1}],"limitations":["uncertain"]} for i in range(150)]
    raw={"breakouts":signals,"pickups":[],"players":{}}
    with patch.object(tools,"_execute",return_value=raw):
        sent=tools.call("waivers_and_breakouts",{})
    assert len(sent["result"]["breakouts"])==150
    assert tools.records[0]["result"]==raw
    columns=sent["result"]["breakout_columns"];last=sent["result"]["breakouts"][-1]
    assert [last[columns.index("targets_"+t)] for t in ("prior","recent","change")]==[2,4,1]


def test_tool_dispatch_validation_real_ownership_and_web_opt_out(config,store):
    s,d=trade_demo();tools=AgentTools(config,store,Mock(),s,1,False)
    assert "error" in tools.call("delete_everything",{})
    assert "error" in tools.call("search_news",{"query":"role"})
    assert "error" in tools.call("get_league",{"league_id":"foreign"})
    free=tools.call("get_free_agents",{"position":"RB"})["result"]
    all_owned={p for r in s.rosters for p in r.players+r.reserve+r.taxi}
    assert not {row[0] for row in free["players"]}&all_owned
    found=tools.call("find_players",{"query":s.players["demo-1"].name})["result"]
    assert next(row for row in found["players"] if row[0]=="demo-1")[found["player_columns"].index("owner_roster_id")]==1


def test_identical_tools_cached_and_errors_redacted(config,store):
    s,d=trade_demo();tools=AgentTools(config,store,Mock(),s,1)
    with patch.object(tools,"_execute",return_value=compact_context(s,1)) as execute:
        tools.call("get_league",{});second=tools.call("get_league",{})
        assert execute.call_count==1 and second["cached_this_turn"]
    with patch.object(tools,"_execute",side_effect=ValueError("bad test-key")):
        result=tools.call("team_needs",{})
        assert "test-key" not in result["error"]


def test_long_running_turn_refreshes_expired_ownership_before_next_analysis(config,store):
    s,d=trade_demo();fresh=s.model_copy(deep=True)
    s.refreshed_at=utcnow()-timedelta(minutes=10)
    service=Mock();service.load.return_value=fresh
    tools=AgentTools(config,store,service,s,1)
    result=tools.call("get_free_agents",{"position":"RB"})
    assert "error" not in result
    service.load.assert_called_once_with(s.league_id,force=True)
    assert result["result"]["ownership_at"]==fresh.refreshed_at.isoformat()


def test_followups_refresh_before_tool_reasoning_and_preserve_messages(config,store):
    s,d=trade_demo();service=Mock();service.load.return_value=s
    model=Mock();model.run_agent.return_value="specific action"
    analyst=Analyst(config,store,service,model)
    prior=[{"role":"assistant","content":"prior evidence"}]
    fresh,message=analyst.run(s,1,"Why that player?",prior)
    assert service.load.call_count==2
    assert all(c.kwargs=={"force":True} and c.args==(s.league_id,) for c in service.load.call_args_list)
    assert model.run_agent.call_args.args[2] is prior
    assert message["refreshed_at"]==s.refreshed_at.isoformat()


def test_changed_ownership_during_reasoning_prevents_stale_recommendation(config,store):
    s,d=trade_demo();changed=s.model_copy(deep=True);changed.rosters[0].players.remove('demo-0')
    service=Mock();service.load.side_effect=[s,changed]
    model=Mock();model.run_agent.return_value="Old advice"
    with pytest.raises(ValueError,match="League changed"):
        Analyst(config,store,service,model).run(s,1,"What should I do?",[])


def test_catalog_status_change_invalidates_advice_and_unknown_team_is_rejected(config,store):
    s,d=trade_demo();changed=s.model_copy(deep=True);changed.players['demo-0'].injury_status='Out'
    service=Mock();service.load.side_effect=[s,changed]
    model=Mock();model.run_agent.return_value="Old advice"
    with pytest.raises(ValueError,match="League changed"):
        Analyst(config,store,service,model).run(s,1,"Who should I start?",[])
    service.load.side_effect=None;service.load.return_value=s;model.reset_mock()
    with pytest.raises(ValueError,match="no longer exists"):
        Analyst(config,store,service,model).run(s,999,"Who should I start?",[])
    model.run_agent.assert_not_called()


def test_shared_waivers_and_lineup_tools(config,store):
    s,d=trade_demo();s.league_status="in_season";s.league_type="redraft"
    client=Mock();client.load.return_value=d;client.csv.return_value=(d.schedule,d.sources[0])
    tools=AgentTools(config,store,Mock(),s,1,data_client=client)
    result=tools.call("waivers_and_breakouts",{"strategy":"win_now","position":"RB"})
    assert "error" not in result,result
    result=tools.call("optimize_lineup",{"week":s.week+1})
    assert "error" not in result,result
    assert result["result"]["week"]==s.week+1


def test_mid_tool_overload_restarts_without_signatures_and_keeps_evidence(config,store):
    client=gemini_client()
    class Busy(Exception):code=503
    signed=model_response([types.Part(function_call=types.FunctionCall(name="get_league",args={},id="signed-call"),thought_signature=b"signature")])
    client.models.generate_content.side_effect=[signed]+[Busy("high demand")]*3+[model_response([types.Part(text="Recovered answer")])]
    dispatcher=Mock();dispatcher.declarations.return_value=[];dispatcher.records=[]
    dispatcher.call.return_value={"result":{"league_format":"dynasty"}}
    with patch("fantasy_agent.integrations.gemini.time.sleep"):
        answer=Gemini(config,store,client).run_agent({},"Analyze",[],dispatcher)
    assert "Recovered answer" in answer
    sent=client.models.generate_content.call_args.kwargs
    assert sent['model']=='gemini-3.8-flash'
    assert 'dynasty' in str(sent['contents'])
    assert all(not p.thought_signature and not p.function_call and not p.function_response for c in sent['contents'] for p in c.parts)
    assert dispatcher.call.call_count==1
