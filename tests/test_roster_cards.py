from fantasy_agent.models import Player
from fantasy_agent.roster_cards import player_card


def test_card_preserves_metadata_and_escapes_external_text():
    p=Player(player_id="4046",name='<script>player</script>',positions=['QB'],team='KC',injury_status='Questionable')
    card=player_card(p,'SUPER_FLEX')
    assert '<script>' not in card and '&lt;script&gt;' in card
    assert all(text in card for text in ['4046','KC','QB','Questionable','SUPER_FLEX'])
    assert 'https://sleepercdn.com/content/nfl/players/thumb/4046.jpg' in card


def test_unknown_photo_and_status_have_honest_fallbacks():
    card=player_card(Player(player_id="unknown\"id",name='New Player'))
    assert 'sleepercdn.com' not in card
    assert 'NP' in card and 'NFL team unassigned' in card
    assert 'no catalog designation' in card and 'healthy' not in card.lower()
