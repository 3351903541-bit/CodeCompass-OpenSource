from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import pytest
from codecompass.product.service import Service,Conflict

def test_three_courses_and_recovery(service):
    u=service.profile()['user_id'];ids=[]
    for i in range(3):
        s=service.create(u,'P02_window_fix');sid=s['session_id'];ids.append(sid)
        assert s['state']['plan_status']=='FEASIBLE'
        assert set(s['state']['remaining'])=={'u_iterable','u_positive_int','u_windowed_iter'}
        paused=service.action(sid,'pause',0,'pause')
        assert service.action(sid,'pause',0,'pause')==paused
        with pytest.raises(Conflict):service.action(sid,'pause',0,'archive')
        with pytest.raises(Conflict):service.action(sid,'stale',0,'resume')
        service.action(sid,'resume',1,'resume')
        service.action(sid,'archive',2,'archive')
    assert len(set(ids))==3
    restored=Service(service.root,service.store.path,'test_fixture')
    assert len(restored.profile(u)['sessions'])==3
    assert restored.store.evidence.read(u,simulated=True)['records']==[]

def test_thirty_minutes_and_css_restart(service):
    u=service.profile()['user_id'];s=service.create(u,'P02_window_fix')
    with patch('codecompass.product.service.now',return_value=(datetime.now(timezone.utc)+timedelta(minutes=31)).isoformat()):
        assert service.get(s['session_id'])==s
    css=service.root/'app/product/style.css';original=css.read_bytes()
    try:
        css.write_bytes(original+b'\n/* recovery probe */\n')
        restored=Service(service.root,service.store.path,'test_fixture')
        assert restored.get(s['session_id'])==s
        assert restored.profile(u)['user_id']==u
    finally:css.write_bytes(original)

def test_only_one_active_and_stale_plan(service):
    u=service.profile()['user_id'];a=service.create(u,'P02_window_fix');b=service.create(u,'P02_window_fix')
    assert service.get(a['session_id'])['status']=='paused'
    service.action(a['session_id'],'resume',1,'resume')
    assert service.get(b['session_id'])['status']=='paused'
    from codecompass.product.service import plan
    def racing(*args,**kw):
        result=plan(*args,**kw)
        service.action(a['session_id'],'race',2,'pause')
        return result
    with patch('codecompass.product.service.plan',side_effect=racing):
        with pytest.raises(Conflict):service.create(u,'P02_window_fix')
    assert len(service.profile(u)['sessions'])==2


def test_short_scope_is_not_fake_completion(service):
    uid=service.profile()['user_id']
    s=service.create(uid,'P02_window_fix','short')
    assert s['state']['plan_status']=='NO_FEASIBLE_FOUND'
    assert s['status']=='active' and s['phase']=='learning'
    assert s['state']['completed']==[]
    assert service.get(s['session_id'])==s
    ledger=service.store.evidence.read(uid,simulated=True)
    assert ledger['records']==[]
