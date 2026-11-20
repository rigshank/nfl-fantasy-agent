from types import SimpleNamespace
from fantasy_agent.models import Player
from fantasy_agent.lineup_cards import starting_cards, comparison_cards, evidence_rows


def test_comparisons_preserve_zero_and_do_not_infer_locked_gains():
    player = Player(player_id='1',name='<Player>',positions=['QB'])
    slot = SimpleNamespace(index=0,slot='SUPER_FLEX',current_id='1',recommended_id='1',
        current_estimate=0,estimate=0,objective=5,locked=True,opponent=None,kickoff=None,reason='<Reason>')
    report = SimpleNamespace(slots=[slot])
    html = comparison_cards(report,{'1':player})
    assert 'Locked / unverified' in html and 'Slot difference' in html
    assert '+0.00' not in html and '>0.00<' in html
    assert 'Strategy score: 5.00' in html and '&lt;Reason&gt;' in html
    assert '<Player>' not in html and '&lt;Player&gt;' in html
    slot.locked = False
    assert '+0.00' in comparison_cards(report,{'1':player})
    slot.recommended_id = None
    assert 'Unfilled slot' in starting_cards(report,{'1':player})
    slot.recommended_id = 'missing'
    assert 'Player details unavailable' in starting_cards(report,{'1':player})


def test_evidence_search_keeps_nested_values_and_unknowns():
    rows = evidence_rows({'weekly':{'12':0},'missing':None,'available':False})
    assert ('weekly / 12',0) in rows and ('missing',None) in rows and ('available',False) in rows
    assert evidence_rows({'weekly':{'12':0},'missing':None},'weekly') == [('weekly / 12',0)]
