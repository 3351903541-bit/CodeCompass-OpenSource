import json,subprocess,os
import pytest
from codecompass.product.service import Service
from tests.product.test_learning import perform

def p01_practice(service,user):
    s=perform(service,service.create(user,'P01_unique_read'),'skip_baseline')
    s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    s=perform(service,s,'check',{'choice':None});return perform(service,s,'check',{'continue':True})

def test_p01_behavior_oracles_and_review(service):
    uid=service.profile()['user_id'];data=service.catalog.source('P01_unique_read')
    for q in [*service.questions.data['P01_unique_read'].values(),*service.questions.practice('P01_unique_read')]:
        env=dict(os.environ,PYTHONPATH=str(service.root/data['source_root']))
        run=subprocess.run([__import__('sys').executable,'-c',q['code']],capture_output=True,text=True,env=env,timeout=10)
        assert run.returncode==0 and run.stdout.strip()==q['oracle_output']
    s=p01_practice(service,uid)
    assert all('answer' not in q for q in s['practice_questions'])
    s=perform(service,s,'answers',{'answers':[0,1,1],'reflection':'需要复习'})
    assert s['phase']=='practice' and all(r['correct'] is False for r in s['state']['answer_results'])
    count=len(service.store.evidence.read(uid,simulated=True)['records']);assert count==3
    s=perform(service,s,'answers',{'answers':[1,0,0],'reflection':'seen保存key，yield原元素'})
    assert s['phase']=='review' and s['status']=='completed'
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==count
    assert not s['state']['plan_pending']

def test_restart_switch_review_and_content_compatibility(service):
    uid=service.profile()['user_id'];s=p01_practice(service,uid)
    s=service.draft(s['session_id'],'draft',s['revision'],'practice',dict(answers=[1,None,None],reflection='保留我'))
    unit=s['state']['completed'][0]
    s=service.assistant.ask(s['session_id'],unit,'给我一个类似例子','help','offline')['session']
    before=service.store.evidence.read(uid,simulated=True)
    service.material(s['session_id'],unit);service.material(s['session_id'],unit)
    assert service.store.evidence.read(uid,simulated=True)==before
    other=service.create(uid,'P02_window_fix');assert other['state']['draft'] is None
    restored=Service(service.root,service.store.path,'test_fixture')
    old=restored.get(s['session_id']);assert old['status']=='paused' and old['state']['draft']['reflection']=='保留我'
    assert len(restored.assistant.history(s['session_id'])['messages'])==1
    assert len(restored.profile(uid)['sessions'])==2
    # Text/content version changes do not invalidate matching source mappings.
    with service.store.connect() as db:db.execute('UPDATE product_sessions SET content_version=? WHERE session_id=?',('older-text',s['session_id']))
    assert not restored.get(s['session_id'])['read_only']
    with service.store.connect() as db:
        state=old['state'];state['remaining'].append('removed-unit')
        db.execute('UPDATE product_sessions SET state_json=? WHERE session_id=?',(json.dumps(state),s['session_id']))
    incompatible=restored.get(s['session_id']);assert incompatible['read_only']
    assert incompatible['state']['draft']['reflection']=='保留我'
    with pytest.raises(ValueError):perform(restored,incompatible,'resume')
    assert restored.store.evidence.read(uid,simulated=True)==before
