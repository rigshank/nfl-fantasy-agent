from types import SimpleNamespace

from fantasy_agent.models import Player
from fantasy_agent.waiver_cards import fmt, pickup_cards, signal_cards, usage_cards, weekly_cards


def test_pickup_cards_keep_unknown_values_zero_gains_and_drop_identity():
    snapshot = SimpleNamespace(players={
        '1': Player(player_id='1', name='<Player>', positions=['RB'], team='SEA'),
        '2': Player(player_id='2', name='Actual drop', positions=['WR']),
    })
    pickup = SimpleNamespace(player_id='1', drop_id='2', kind='Depth', confidence='low',
        next_week_gain=0, ros_gain=2.5, bench_change=-1, dynasty_change=None,
        breakout_score=4, reasons=['<Evidence>'], risks=['Uncertain role'], faab={})
    html = pickup_cards(snapshot, [pickup], offset=6)
    assert '#07' in html and 'Actual drop' in html and '+0.00' in html
    assert 'Dynasty index Δ: —' in html and 'Not established' in html
    assert '<Player>' not in html and '&lt;Player&gt;' in html and '&lt;Evidence&gt;' in html
    pickup.drop_id = None
    assert 'no drop needed' in pickup_cards(snapshot, [pickup])


def test_opportunity_evidence_uses_percentage_points_and_preserves_missing_games():
    signal = SimpleNamespace(player_id='1', score=22, confidence='low', label='New role',
        prior_games=2, recent_games=3, reasons=[], limitations=['Limited sample'], changes=[
            SimpleNamespace(metric='snap_share', prior=.4, recent=.55, change=.15),
            SimpleNamespace(metric='opportunities', prior=None, recent=8, change=None),
        ])
    html = usage_cards(signal)
    assert '40.0%' in html and '55.0%' in html and '+15.0 pp' in html
    assert 'Change: —' in html and 'PRIOR · 2 GAMES' in html
    snapshot = SimpleNamespace(players={'1': Player(player_id='1', name='Player')})
    assert '+15.0 pp' in signal_cards(snapshot, [signal])
    weekly = weekly_cards([{'week': 3, 'fantasy_points': 0, 'snap_share': None, 'targets': 0}])
    assert 'Week 3' in weekly and '0.00 pts' in weekly and '>—<' in weekly
    assert 'Week 2' not in weekly
    assert fmt(float('nan')) == '—'
