from fantasy_agent.models import Roster
from fantasy_agent.standings_ui import ordered_teams, standings_html, total
from tests.fixture_roster import demo_snapshot


def test_standings_preserve_decimals_shared_ranks_and_filtered_rank():
    snapshot = demo_snapshot()
    snapshot.rosters = [Roster(roster_id=i, manager=name, settings={
        'wins': wins, 'losses': 1, 'ties': 1, 'fpts': pf, 'fpts_decimal': 25,
        'fpts_against': 90, 'fpts_against_decimal': 50,
    }) for i, name, wins, pf in [(1, 'Leader', 5, 100), (2, 'Equal', 5, 100), (3, 'Third', 4, 99)]]
    assert total(snapshot.rosters[0].settings, 'fpts') == 100.25
    assert [r.roster_id for r in ordered_teams(snapshot)] == [1, 2, 3]
    html = standings_html(snapshot, 1)
    assert html.count('ff-standing-rank">01') == 2
    assert '+9.75' in html and '78.6%' in html and 'YOUR TEAM' in html
    assert 'ff-standing-rank">03' in standings_html(snapshot, query='third')


def test_standings_escape_names_and_keep_unknown_scores_missing():
    snapshot = demo_snapshot()
    snapshot.rosters = [Roster(roster_id=1, manager='<script>bad</script>', settings={'wins': 0, 'fpts': 0}),
                        Roster(roster_id=2, manager='Unknown', settings={})]
    html = standings_html(snapshot)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert '>0.00<' in html and '>—<' in html
    assert total({'fpts': None}, 'fpts') is None
    assert total({'fpts': float('nan')}, 'fpts') is None
