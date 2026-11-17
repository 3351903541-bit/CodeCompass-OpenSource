"""Development mechanism cases using the real planner; no calibrated learner claims."""
import copy,math
import pytest
from codecompass.product.planning import plan,remaining
from codecompass.learner import mastery_gate
from tests.product.test_learning import perform

def seed(service,user,concept,outcome='pass',count=8,prefix='mechanism'):
    project=service.catalog.source('P02_window_fix')['snapshot']['snapshot_id']
    rows=[dict(evidence_id=f'{prefix}:{i}',item_id=f'{prefix}:{i}',concept_id=concept,project=project,timestamp='2026-10-23T20:00:00+08:00',pseudonymous_user_id=user,is_fixture=True,independent=True,evidence_type='independent_quiz',outcome=outcome) for i in range(count)]
    service.store.evidence.submit_many(user,rows,simulated=True)
    return rows

def test_deterministic_real_gate_and_failure_cost(service):
    uid=service.profile()['user_id'];data=service.catalog.source('P02_window_fix',uid)
    ledger=service.store.evidence.read(uid,simulated=True)
    a=plan(service.root,data,ledger,service.config);b=plan(service.root,data,ledger,service.config)
    assert a['remaining']==b['remaining'] and a['plan_audit']['valid']
    assert a['default_budget']==math.ceil(sum(a['unit_costs'].values())+2)
    seed(service,uid,'python.iterator_protocol')
    ledger=service.store.evidence.read(uid,simulated=True)
    gate=mastery_gate(ledger,data['snapshot']['snapshot_id'],['python.iterator_protocol'],allow_simulated=True)
    assert gate['python.iterator_protocol']['mastered']
    strong=plan(service.root,data,ledger,service.config)
    assert 'u_iterable' not in strong['remaining'] and strong['plan_audit']['valid']
    seed(service,uid,'python.iterator_protocol','fail',20,'failure')
    failed=plan(service.root,data,service.store.evidence.read(uid,simulated=True),service.config)
    assert failed['unit_costs']['u_iterable']>strong['unit_costs']['u_iterable']
    assert 'u_iterable' in failed['remaining'] and failed['plan_audit']['valid']

def test_short_scope_missing_and_wide_restore(service):
    uid=service.profile()['user_id'];s=service.create(uid,'P02_window_fix')
    initial=s['state']['default_budget']
    s=perform(service,s,'budget',{'scope':'short'})
    assert s['state']['budget']==math.ceil(initial*.6)
    assert s['state']['plan_status']=='NO_FEASIBLE_FOUND' and s['state']['missing']
    assert s['status']=='active'
    s=perform(service,s,'budget',{'scope':'wide'})
    assert s['state']['budget']==math.ceil(initial*1.2) and s['state']['plan_status']=='FEASIBLE'

def test_feedback_timeout_saved_and_retry_only_search(service,monkeypatch):
    uid=service.profile()['user_id'];s=perform(service,service.create(uid,'P02_window_fix'),'skip_baseline')
    first=s['state']['remaining'][0];s=perform(service,s,'read',{'unit_id':first})
    frozen=s['state']['completed_costs'][first];old=list(s['state']['remaining'])
    service.config['search']['time_limit_seconds']=0
    s=perform(service,s,'check',{'choice':1},'answer-before-timeout')
    assert s['state']['plan_status']=='TIMEOUT' and s['state']['plan_pending']
    assert s['state']['remaining']==old and s['state']['completed']==[first]
    assert s['state']['feedback']['independent'] and len(service.store.evidence.read(uid,simulated=True)['records'])==1
    spent=s['state']['quiz_spent'];service.config['search']['time_limit_seconds']=5
    s=perform(service,s,'retry_plan')
    assert s['state']['plan_status']=='FEASIBLE' and not s['state']['plan_pending']
    assert s['state']['quiz_spent']==spent and s['state']['completed_costs'][first]==frozen
    assert first not in s['state']['remaining'] and s['state']['plan_audit']['valid']
    assert s['state']['spent']==pytest.approx(s['state']['learning_spent']+s['state']['quiz_spent']+s['state']['switch_spent'])

def test_search_exception_does_not_lose_evidence(service,monkeypatch):
    uid=service.profile()['user_id'];s=perform(service,service.create(uid,'P02_window_fix'),'skip_baseline');s=perform(service,s,'read',{'unit_id':s['state']['remaining'][0]})
    def broken(*args):raise RuntimeError('injected search failure')
    monkeypatch.setattr('codecompass.product.service.remaining',broken)
    out=perform(service,s,'check',{'choice':1},'saved')
    assert out['state']['plan_status']=='ERROR' and out['state']['plan_pending']
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==1
    assert perform(service,s,'check',{'choice':1},'saved')==out

def test_switch_cost_paid_once_and_completed_cost_frozen(service):
    uid=service.profile()['user_id'];seed(service,uid,'python.iterator_protocol')
    data=service.catalog.source('P02_window_fix',uid)
    ledger=service.store.evidence.read(uid,simulated=True)
    state=plan(service.root,data,ledger,service.config,scope='wide')
    seed(service,uid,'python.iterator_protocol','fail',20,'new-failure')
    ledger=service.store.evidence.read(uid,simulated=True)
    state=remaining(service.root,data,ledger,service.config,state,'new_failure')
    assert state['switch_spent']>0 and state['plan_audit']['valid']
    paid=state['switch_spent'];spent=state['spent']
    state=remaining(service.root,data,ledger,service.config,state,'retry')
    assert state['switch_spent']==paid and state['spent']==spent
