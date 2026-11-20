from unittest.mock import Mock,patch
from types import SimpleNamespace
import pytest
from fantasy_agent.agent import AgentTools
from fantasy_agent.faab import waiver_budget,bid_guidance
from fantasy_agent.session import clear_analysis
from fantasy_agent.evaluation import evaluate_players
from fantasy_agent.models import ResearchResult
from fantasy_agent.integrations.research import ProviderUnavailable
from fantasy_agent.lineup_service import LineupService
from tests.fixture_stats import trade_demo


def test_faab_requires_rules_and_budget_and_never_exceeds_remaining():
    s,d=trade_demo();r=s.rosters[0]
    s.settings.update(waiver_type=0,waiver_budget=100);r.settings['waiver_budget_used']=70
    assert waiver_budget(s,1)['remaining'] is None
    s.settings['waiver_type']=2
    pickup=SimpleNamespace(ros_gain=100,confidence='medium')
    guide=bid_guidance(s,1,pickup,5)
    assert guide['remaining']==30 and 0<=guide['range'][0]<=guide['range'][1]<=30
    s.settings['waiver_bid_min']=31
    assert bid_guidance(s,1,pickup,5)['range'] is None
    s.settings['waiver_bid_min']=0;r.settings['waiver_budget_used']=100
    assert bid_guidance(s,1,pickup,5)['range']==[0,0]
    r.settings.pop('waiver_budget_used')
    assert bid_guidance(s,1,pickup,5)['range'] is None
    r.settings.update(waiver_budget_used=0,waiver_adjusted=11)
    assert bid_guidance(s,1,pickup,5)['range'] is None


def test_team_change_clears_dependent_answers_and_protections_only():
    state={'waiver_run':1,'waiver_answers':2,'waiver_protected_players':['old'],
           'breakout_identity':('old',1),'messages':[1],'queued_question':'old',
           'analysis_options':{'gemini_model':'auto'},'snapshot':'current'}
    clear_analysis(state,team_changed=True)
    assert state=={'messages':[],'analysis_options':{'gemini_model':'auto'},'snapshot':'current'}


def test_broad_strategy_reuses_data_and_evaluations_without_skipping_analyses(config,store):
    s,d=trade_demo();s.league_type='redraft';s.league_status='in_season'
    client=Mock();client.load.return_value=d;client.csv.return_value=(d.schedule,d.sources[0])
    tools=AgentTools(config,store,Mock(),s,1,data_client=client)
    with patch('fantasy_agent.agent.evaluate_players',wraps=evaluate_players) as evaluate:
        result=tools.call('team_strategy',{})
    assert 'error' not in result,result
    assert set(result['result'])=={'get_league','team_needs','waivers_and_breakouts','optimize_lineup','find_trades'}
    assert not any('error' in entry for entry in result['result'].values()),result
    assert client.load.call_count==1 and evaluate.call_count==1
    assert len(tools.records)==6


def test_generated_source_urls_must_be_retrieved(config,store):
    s,d=trade_demo();tools=AgentTools(config,store,Mock(),s,1)
    source=ResearchResult(title='Report',url='https://www.nfl.com/news/report',excerpt='Evidence')
    tools.sources[source.url]=source
    tools.validate_sources('A [report](https://www.nfl.com/news/report#details).')
    with pytest.raises(ProviderUnavailable,match='unchecked answer'):
        tools.validate_sources('A [made-up report](https://www.nfl.com/news/made-up).')


def test_explicit_exclusions_cannot_move_locked_starters(config,store):
    s,d=trade_demo();s.league_status='in_season'
    service=LineupService(config,store)
    future=service.analyze(s,d,1,s.week+1,excluded=['demo-2'])
    assert 'demo-2' not in {r.recommended_id for r in future.slots}
    assert future.slots[2].current_estimate>0
    current=service.analyze(s,d,1,excluded=['demo-2'])
    assert current.slots[2].locked and current.slots[2].recommended_id=='demo-2'
    with pytest.raises(ValueError,match='selected team'):
        service.analyze(s,d,1,s.week+1,excluded=['demo-8'])


def test_ai_exclusion_requires_retrieved_source(config,store):
    s,d=trade_demo();s.league_status='in_season'
    client=Mock();client.load.return_value=d;client.csv.return_value=(d.schedule,d.sources[0])
    tools=AgentTools(config,store,Mock(),s,1,data_client=client)
    args={'week':s.week+1,'exclude_players':['demo-2'],'exclusion_sources':{'demo-2':'https://www.nfl.com/news/report'}}
    assert 'error' in tools.call('optimize_lineup',args)
    source=ResearchResult(title='Report',url=args['exclusion_sources']['demo-2'],excerpt='Explicit report')
    tools.sources[source.url]=source
    result=tools.call('optimize_lineup',args)
    assert 'error' not in result,result
    assert 'demo-2' not in {r['recommended_id'] for r in result['result']['slots']}
