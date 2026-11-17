import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from codecompass.product.service import Conflict
from tests.product.test_learning import perform

def test_same_revision_race_and_payload_identity(service,monkeypatch):
    uid=service.profile()['user_id'];s=perform(service,service.create(uid,'P02_window_fix'),'skip_baseline');s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    from codecompass.product.service import update_evidence
    barrier=threading.Barrier(2)
    def simultaneous(*args,**kwargs):
        result=update_evidence(*args,**kwargs);barrier.wait(timeout=10);return result
    monkeypatch.setattr('codecompass.product.service.update_evidence',simultaneous)
    def answer(rid):
        try:return perform(service,s,'check',{'choice':1},rid)
        except Conflict as e:return e
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(answer,['race-a','race-b']))
    assert sum(isinstance(r,Conflict) for r in results)==1
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==1
    winner=next(r for r in results if isinstance(r,dict))
    rid='race-a' if isinstance(results[0],dict) else 'race-b'
    assert perform(service,s,'check',{'choice':1},rid)==winner
    with pytest.raises(Conflict):perform(service,s,'check',{'choice':0},rid)
    with service.store.connect() as db:
        assert db.execute('SELECT count(*) FROM product_answers WHERE session_id=?',(s['session_id'],)).fetchone()[0]==1
        row=db.execute('SELECT value_json FROM product_answers WHERE session_id=?',(s['session_id'],)).fetchone()[0]
        for key in ('evidence_id','item_id','concept_id','project','source_mode','timestamp','correct'):assert key in row

def test_read_help_skip_and_repeated_course_never_duplicate(service):
    uid=service.profile()['user_id'];s=perform(service,service.create(uid,'P02_window_fix'),'skip_baseline')
    assert not service.store.evidence.read(uid,simulated=True)['records']
    unit=s['state']['remaining'][0];s=perform(service,s,'read',{'unit_id':unit})
    assert not service.store.evidence.read(uid,simulated=True)['records']
    s=perform(service,s,'check',{'choice':1});s=perform(service,s,'archive')
    s=service.create(uid,'P02_window_fix')
    assert s['phase']=='learning' and s['state']['baseline_done']
    s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    s=perform(service,s,'check',{'choice':1})
    assert not s['state']['feedback']['independent']
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==1

def test_stale_search_does_not_overwrite_a_newer_session(service,monkeypatch):
    uid=service.profile()['user_id'];s=perform(service,service.create(uid,'P02_window_fix'),'skip_baseline')
    unit=s['state']['remaining'][0];s=perform(service,s,'read',{'unit_id':unit})
    from codecompass.product.service import remaining
    def race(*args):
        result=remaining(*args)
        service.assistant.ask(s['session_id'],unit,'带我读这段代码','concurrent-help','offline')
        return result
    monkeypatch.setattr('codecompass.product.service.remaining',race)
    out=perform(service,s,'check',{'choice':1},'answer')
    assert out['state']['plan_pending'] and unit in out['state']['assisted_units']
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==1
    assert len(service.assistant.history(s['session_id'])['messages'])==1
    monkeypatch.setattr('codecompass.product.service.remaining',remaining)
    out=perform(service,out,'retry_plan');assert not out['state']['plan_pending']
    assert unit in out['state']['assisted_units']
