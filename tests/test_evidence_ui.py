from fantasy_agent.evidence_ui import source_cards, limitation_cards
from fantasy_agent.models import utcnow
from fantasy_agent.trade_models import SourceInfo


def test_sources_escape_text_preserve_dates_and_flag_stale_cache():
    source = SourceInfo(name='<Source>', url='https://example.com/stats?a=1&b=2', retrieved_at=utcnow(),
                        source_updated_at='2026-11-19', stale=True)
    html = source_cards([source])
    assert '&lt;Source&gt;' in html and '<Source>' not in html
    assert 'STALE CACHE' in html and '2026-11-19' in html
    assert 'a=1&amp;b=2' in html
    source.url = 'javascript:alert(1)'
    assert 'href=' not in source_cards([source])
    source.stale = False
    source.source_updated_at = None
    assert 'Not provided' in source_cards([source])


def test_limitations_collapse_long_summaries_without_losing_full_evidence():
    warning = 'Important: ' + ('long caveat ' * 25) + '\n<Additional context>'
    html = limitation_cards([warning])
    assert '<details>' in html and '…</summary>' in html
    assert warning.replace('<', '&lt;').replace('>', '&gt;') in html
