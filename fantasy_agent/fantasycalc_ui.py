"""Manual companion to FantasyCalc; no proprietary values or calculator clone."""
import streamlit as st

CALCULATOR='https://fantasycalc.com/trade-calculator'
TERMS='https://fantasycalc.com/terms-of-usage'


def review_settings(snapshot):
    qb=snapshot.roster_positions.count('QB')
    sf=snapshot.roster_positions.count('SUPER_FLEX')
    return {'Format':'Dynasty' if snapshot.league_type=='dynasty' else snapshot.league_type.title(),
            'Teams':len(snapshot.rosters),'QB slots':qb,'Superflex slots':sf,
            'Reception points':snapshot.scoring.get('rec',0),
            'TE reception bonus':snapshot.scoring.get('bonus_rec_te',0)}


def offer_text(snapshot,trade):
    managers={r.roster_id:r.manager for r in snapshot.rosters}
    def names(ids):return ', '.join(snapshot.players[p].name for p in ids) or 'None'
    settings=review_settings(snapshot)
    lines=['FantasyCalc manual dynasty review',*['%s: %s'%(k,v) for k,v in settings.items()],
        '',managers.get(trade.my_roster_id,'Your team')+' sends: '+names(trade.send),
        managers.get(trade.opponent_id,'Opponent')+' sends: '+names(trade.receive)]
    if trade.my_drops or trade.opponent_drops:
        lines.extend(['','Separate roster moves, NOT part of the offered package:',
            'Your required drops: '+names(trade.my_drops),'Opponent required drops: '+names(trade.opponent_drops)])
    lines.extend(['','Enter the same players and matching supported settings on FantasyCalc.',
        'No FantasyCalc values or fairness verdict have been retrieved.'])
    return '\n'.join(lines)


def render_reference(snapshot,trade=None):
    with st.expander('Consult FantasyCalc dynasty calculator',expanded=trade is not None):
        st.caption('Use the same calculator your league uses as an additional market check. Open the official site and select Dynasty; match its supported settings to the values below.')
        st.link_button('Open official FantasyCalc calculator ↗' if trade is None else 'Open calculator for this offer ↗',CALCULATOR)
        if trade is None:
            a,b,c=st.columns(3)
            settings=review_settings(snapshot)
            a.metric('League size',settings['Teams'])
            b.metric('QB / superflex slots',f"{settings['QB slots']} / {settings['Superflex slots']}")
            c.metric('Reception points',settings['Reception points'])
            st.caption(f"TE reception bonus: {settings['TE reception bonus']}. Verify how the external calculator handles your custom bonuses, flex slots and scoring. No approximation is silently applied.")
            st.write('Choose a ranked trade below to get a copyable offer with both sides and the league settings.')
        else:
            st.caption('Use the copy button on this offer, then enter its players in FantasyCalc. Required drops are listed separately from traded assets.')
            st.code(offer_text(snapshot,trade),language=None,wrap_lines=True)
        st.caption('Manual review only: the app has not queried a FantasyCalc fairness score or copied its values. Python lineup gains and existing market heuristics remain independent. Calculator balance does not predict manager acceptance.')
        with st.expander('Why this opens the official calculator'):
            st.write('FantasyCalc limits use of its data in substitute trade calculators. Automated value-based integration here would require permission from FantasyCalc; this companion sends no league data automatically.')
            st.link_button('FantasyCalc data-use terms' if trade is None else 'FantasyCalc automated valuation terms',TERMS)
