from fantasy_agent.conversations import Conversations


def test_chats_survive_new_store_instances_and_preserve_evidence(store):
    chats=Conversations(store,"browser-a","league",1)
    messages=[{"role":"user","content":"Compare my injured players"},
              {"role":"assistant","content":"Dated evidence", "tools":[{"tool":"get_league","result":{"week":11}}]}]
    cid=chats.create(messages)
    restored=Conversations(store,"browser-a","league",1)
    assert restored.messages(cid)==messages
    assert restored.list()[0]["title"]==messages[0]["content"]


def test_history_is_scoped_by_browser_league_and_team(store):
    chats=Conversations(store,"browser-a","league",1)
    cid=chats.create([{"role":"user","content":"Private question"}])
    for browser,league,team in [("browser-b","league",1),("browser-a","other",1),("browser-a","league",2)]:
        other=Conversations(store,browser,league,team)
        assert other.list()==[] and other.messages(cid) is None
        import pytest
        with pytest.raises(ValueError):other.save(cid,[])
    assert chats.messages(cid)[0]["content"]=="Private question"


def test_recent_activity_orders_chats_and_opening_history_does_not_reorder(store):
    chats=Conversations(store,"browser","league",1)
    first=chats.create([{"role":"user","content":"First trade"}])
    second=chats.create([{"role":"user","content":"Second trade"}])
    assert chats.list()[0]["id"]==second
    chats.messages(first)
    assert chats.list()[0]["id"]==second
    chats.save(first,[{"role":"user","content":"First trade"},{"role":"assistant","content":"New answer"}])
    assert chats.list()[0]["id"]==first


def test_new_conversation_keeps_earlier_messages_and_title_is_plain_text(store):
    chats=Conversations(store,"browser","league",1)
    old=chats.create([{"role":"user","content":"  A long\nquestion "+"x"*100}])
    new=chats.create()
    assert chats.messages(new)==[]
    assert len(chats.messages(old))==1
    assert len(chats.list()[0]["title"])<=58
    assert all(chat["id"]!=new for chat in chats.list())
