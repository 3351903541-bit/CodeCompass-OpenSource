import copy,pytest

def perform(service,s,action,payload=None,rid=None):
    return service.action(s['session_id'],rid or 'r'+str(s['revision']),s['revision'],action,payload)
def to_practice(service,s,*,help_first=False,wrong=False):
    if s['phase']=='baseline':s=perform(service,s,'skip_baseline')
    while s['phase'] in ('learning','check'):
        if s['phase']=='learning':
            uid=s['state']['remaining'][0]
            if help_first:
                out=service.assistant.ask(s['session_id'],uid,'用生活例子解释','help-'+uid,'offline');s=out['session']
            s=perform(service,s,'read',{'unit_id':uid})
        else:
            q=service.questions.unit(s['task_id'],s['state']['current_check'])
            s=perform(service,s,'check',{'choice':(q['answer']+1)%len(q['choices']) if wrong else None})
            assert s['state']['feedback']['explanation']
            s=perform(service,s,'check',{'continue':True})
    assert s['phase']=='practice';return s

def test_baseline_save_skip_and_no_timeout(service):
    u=service.profile()['user_id'];s=service.create(u,'P02_window_fix')
    assert s['phase']=='baseline' and len(s['baseline_questions'])==4
    assert 'answer' not in str(s['baseline_questions'])
    s=perform(service,s,'baseline',{'choices':[1,None,None,None]})
    assert service.get(s['session_id'])['state']['baseline_choices']==[1,None,None,None]
    s=perform(service,s,'skip_baseline');assert all(f['correct'] is None for f in s['state']['baseline_feedback'])
    s=to_practice(service,s);assert service.store.evidence.read(u,simulated=True)['records']==[]

def test_wrong_answer_atomic_and_duplicate(service):
    u=service.profile()['user_id'];s=perform(service,service.create(u,'P02_window_fix'),'skip_baseline')
    s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    before=copy.deepcopy(s)
    s=perform(service,s,'check',{'choice':0},'first')
    assert s['state']['feedback']['correct'] is False and s['state']['feedback']['independent']
    assert perform(service,before,'check',{'choice':0},'first')==s
    assert len(service.store.evidence.read(u,simulated=True)['records'])==1
    s=perform(service,s,'check',{'choice':1});assert not s['state']['feedback']['independent']
    assert len(service.store.evidence.read(u,simulated=True)['records'])==1
    s=perform(service,s,'check',{'continue':True});assert s['phase']=='learning'

def test_help_then_answer_no_independent_evidence(service):
    u=service.profile()['user_id'];s=perform(service,service.create(u,'P02_window_fix'),'skip_baseline');uid=s['state']['remaining'][0]
    s=service.assistant.ask(s['session_id'],uid,'带我读这段代码','help','offline')['session']
    s=perform(service,s,'read',{'unit_id':uid});s=perform(service,s,'check',{'choice':1})
    assert not s['state']['feedback']['independent'];assert not service.store.evidence.read(u,simulated=True)['records']

def test_draft_restores_and_pause_blocks(service):
    u=service.profile()['user_id'];s=to_practice(service,service.create(u,'P02_window_fix'))
    out=service.draft(s['session_id'],'draft',s['revision'],'practice',{'note':'我的修改理由'})
    assert service.get(s['session_id'])['state']['draft']['note']=='我的修改理由'
    assert service.draft(s['session_id'],'draft',s['revision'],'practice',{'note':'我的修改理由'})==out
    out=perform(service,out,'pause')
    with pytest.raises(ValueError):service.draft(out['session_id'],'draft2',out['revision'],'practice',{'note':'changed'})

def test_evidence_and_progress_rollback_together(service,monkeypatch):
    u=service.profile()['user_id'];s=perform(service,service.create(u,'P02_window_fix'),'skip_baseline');s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    def fail(*args):raise RuntimeError('injected transaction failure')
    monkeypatch.setattr(service,'save',fail)
    with pytest.raises(RuntimeError):perform(service,s,'check',{'choice':1})
    assert not service.store.evidence.read(u,simulated=True)['records']
    assert service.get(s['session_id'])==s
