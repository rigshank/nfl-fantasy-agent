from fantasy_agent.matchup_cards import scoreboard,avatar,points,team_records
from fantasy_agent.normalization import roster_from_raw
from tests.fixture_stats import trade_demo


def test_avatar_uses_owner_or_custom_image_and_rejects_external_markup():
    r=roster_from_raw({'roster_id':1,'owner_id':'u'},{'u':{'avatar':'photo-id','metadata':{'team_name':'<Team>'}}})
    assert 'sleepercdn.com/avatars/thumbs/photo-id' in avatar(r)
    assert '<Team>' not in avatar(r)
    r.avatar='https://bad.example/x';assert 'bad.example' not in avatar(r)


def test_zero_custom_scores_and_missing_pairings_are_preserved():
    s,_=trade_demo();s.matchups=[{'roster_id':1,'matchup_id':7,'points':30,'custom_points':0},{'roster_id':2,'matchup_id':7,'points':10},{'roster_id':3,'matchup_id':None,'points':None}]
    html=scoreboard(s)
    assert '0.00' in html and '10.00' in html and 'Commissioner score' in html
    assert 'Snapshot lead: 10.00' in html
    assert 'Opponent pairing unavailable' in html and '—' in html
    assert points({'points':0})==0
    assert 'Points for' in team_records(s)
