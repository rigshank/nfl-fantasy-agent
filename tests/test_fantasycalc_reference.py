from types import SimpleNamespace
from fantasy_agent.fantasycalc_ui import review_settings,offer_text
from tests.fixture_stats import trade_demo


def test_reference_preserves_league_settings_without_silent_approximation():
    s,_=trade_demo();s.league_type='dynasty';s.roster_positions+=['SUPER_FLEX'];s.scoring.update(rec=1.5,bonus_rec_te=.75)
    settings=review_settings(s)
    assert settings['Reception points']==1.5 and settings['TE reception bonus']==.75
    assert settings['Superflex slots']==1 and settings['Teams']==len(s.rosters)


def test_offer_separates_required_drops_from_package_and_claims_no_verdict():
    s,_=trade_demo();s.league_type='dynasty'
    t=SimpleNamespace(my_roster_id=1,opponent_id=2,send=['demo-2'],receive=['demo-9'],my_drops=['demo-24'],opponent_drops=[])
    text=offer_text(s,t)
    assert s.players['demo-2'].name in text and s.players['demo-9'].name in text
    assert 'NOT part of the offered package' in text
    assert 'No FantasyCalc values or fairness verdict have been retrieved' in text
