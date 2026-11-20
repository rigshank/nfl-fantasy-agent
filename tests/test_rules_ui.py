from fantasy_agent.rules_ui import leaves,fields_html,scoring_html,matches,category


def test_nested_settings_preserve_zero_false_and_escape_markup():
    rows=list(leaves({'waiver':{'budget':0,'enabled':False},'note':'<script>x</script>'}))
    assert ('waiver / budget',0) in rows and ('waiver / enabled',False) in rows
    html=fields_html(rows)
    assert '<script>' not in html and '&lt;script&gt;' in html and '>No<' in html and '>0<' in html


def test_scoring_search_keeps_raw_ids_and_negative_values():
    assert category('bonus_rec_te')=='Bonuses & position premiums'
    assert matches('passing','pass_yd','Passing yards')
    html=scoring_html([('pass_int',-2),('pass_yd',.04)])
    assert 'pass_int' in html and '-2 pts' in html and '+0.04 pts' in html
