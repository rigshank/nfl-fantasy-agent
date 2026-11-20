from fantasy_agent.activity_ui import activity_records,activity_summary
from tests.fixture_stats import trade_demo


def test_transaction_search_resolves_players_and_preserves_raw_fields():
    s,_=trade_demo();pid=next(iter(s.players));name=s.players[pid].name
    s.transactions=[{'type':'waiver','status':'failed','roster_ids':[1],'adds':{pid:1},'settings':{'waiver_bid':0}}]
    rows=activity_records(s,'transactions',name)
    assert len(rows)==1 and 'Failed' in rows[0][0]
    assert ('settings / waiver_bid',0) in rows[0][2]
    assert name in str(rows[0][1])
    assert not activity_records(s,'transactions','nonexistent-player')


def test_pick_and_draft_details_keep_ownership_and_zero_values():
    s,_=trade_demo()
    title,summary=activity_summary(s,'traded_picks',{'season':'2027','round':2,'roster_id':1,'owner_id':2,'previous_owner_id':1},0)
    assert '2027' in title and 'Round 2' in title
    assert s.rosters[1].manager in str(summary)
    s.drafts=[{'draft_id':'123','settings':{'pick_timer':0},'status':'pre_draft'}]
    result=activity_records(s,'drafts','123')
    assert result and ('settings / pick_timer',0) in result[0][2]
