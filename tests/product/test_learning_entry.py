import json
import time
from urllib.error import HTTPError
import subprocess
import sys
import pytest
from codecompass.product.goal_resolution import enrich,resolve
from codecompass.product.onboarding import ITEMS,VERSION
from tests.product.test_source_workspaces import ready,FILES
from scripts.B.comparison.b1 import SpendMeter


def test_everyday_goals_without_files_and_broad_selection(service):
    uid,job=ready(service)
    for text,kind in [('我想要学习这个仓库中有关列表的内容','topic'),('我想学习这个仓库中的核心内容','core'),('我想完整学习这个仓库','all')]:
        p=service.workspaces.create(uid,job['id'],text,budget=None)
        assert p['state']['data']['intent']['kind']==kind
        assert p['state']['result']['status']=='FEASIBLE' and p['state']['result']['audit']['goal_complete']
        spans=[str(p['state']['data']['views'][x]['span']) for x in p['state']['result']['remaining']]
        assert len(spans)==len(set(spans))
        if kind=='topic':
            assert p['state']['data']['targets']
            enriched=enrich(service.workspaces.root/job['id'],service.workspaces._repo(job['id']))
            by={s['id']:s for s in enriched['symbols']}
            assert all('list' in by[x]['semantic_tags'] for x in p['state']['data']['targets'])
    ids=[s['id'] for s in job['symbols']]
    selected=service.workspaces.create(uid,job['id'],'学习这些内容',selected=ids,budget=None)
    assert len(selected['state']['data']['targets'])==len(ids)>3
    assert selected['state']['result']['audit']['goal_complete']
    assert len(p['state']['data']['targets'])==len(ids)


def test_unknown_goal_clarifies_in_plain_language_and_cache(service,monkeypatch):
    uid,job=ready(service);calls=[]
    def unavailable(*args):calls.append(1);return None
    monkeypatch.setattr('codecompass.product.workspaces.model_resolve',unavailable)
    for _ in range(2):
        answer=service.workspaces.create(uid,job['id'],'我想研究量子纠缠',budget=None)
        assert answer['needs_clarification'] and '函数或类' not in answer['message']
    assert len(calls)==1


def test_tiered_quiz_answers_not_public_and_resume(service):
    uid,_=ready(service);a=service.onboarding.start(uid);b=service.onboarding.start(uid)
    assert a['id']==b['id'] and len(a['questions'])==12
    assert len({q['topic'] for q in a['questions']})==8
    assert all('answer' not in q and 'correct' not in q for q in a['questions'])
    chosen=[ITEMS[int(q['id'].rsplit(':',1)[1])][2] for q in a['questions']]
    result=service.onboarding.submit(uid,a['id'],chosen)
    assert result['summary']['correct']==12 and result['summary']['recommended_experience']=='comfortable'
    assert service.onboarding.submit(uid,a['id'],chosen)==result
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==12
    later=service.onboarding.start(uid);new_answers=[ITEMS[int(q['id'].rsplit(':',1)[1])][2] for q in later['questions']]
    service.onboarding.submit(uid,later['id'],new_answers)
    assert len(service.store.evidence.read(uid,simulated=True)['records'])==12
    assert service.create(uid,'P01_unique_read')['phase']!='baseline'
    stranger=service.profile()['user_id']
    with pytest.raises(ValueError):service.onboarding.submit(stranger,a['id'],chosen)


def test_wrong_quiz_overrides_optimistic_survey_and_changes_route(service):
    uid,job=ready(service)
    from codecompass.product.repositories import FEATURES
    service.workspaces.onboard(uid,dict(experience='comfortable',months='24+',familiar=list(FEATURES)),1)
    before=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    a=service.onboarding.start(uid)
    wrong=[(ITEMS[int(q['id'].rsplit(':',1)[1])][2]+1)%4 for q in a['questions']]
    result=service.onboarding.submit(uid,a['id'],wrong)
    after=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    assert result['summary']['recommended_experience']=='new'
    assert after['state']['data']['support'] and len(after['state']['result']['remaining'])>len(before['state']['result']['remaining'])
    assert after['state']['result']['learning_cost']>before['state']['result']['learning_cost']
    assert all(not g['mastered'] for g in after['state']['result']['gate'].values())


def test_question_oracles_match_actual_python():
    for code,_,_,oracle,_,_ in ITEMS:
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=8)
        assert result.returncode==0 and result.stdout.strip()==oracle


def test_enclosing_class_covers_private_methods(service,monkeypatch):
    monkeypatch.setitem(FILES,'demo/model.py',b'class Engine:\n    def step(self):\n        return self._work()\n    def _work(self):\n        return [1]\n')
    uid,job=ready(service)
    repo=enrich(service.workspaces.root/job['id'],service.workspaces._repo(job['id']))
    # Existing explicit names still take priority over generic topic words.
    r=resolve(repo,'我想学习 chunk 函数')
    assert len(r['targets'])==1 and 'chunk' in r['targets'][0]
    p=service.workspaces.create(uid,job['id'],'我想完整学习这个仓库',budget=None);state=p['state']
    assert any('Engine._work' in x for x in state['data']['targets'])
    titles=[state['data']['views'][x]['title'] for x in state['result']['remaining'] if state['data']['views'][x]['kind']=='target']
    assert 'Engine' in titles and 'Engine._work' not in titles and 'Engine.step' not in titles
    p=service.workspaces.feedback(uid,p['id'],0,'read-model','read',state['result']['remaining'][0])
    assert p['state']['result']['audit']['valid']


def test_semantic_fallback_validates_ids_and_caches_cost(service):
    service.assistant.injected=True;service.assistant.meter=SpendMeter(1);calls=[]
    def transport(payload,cfg):
        calls.append(1);context=json.loads(payload['input'].split('\n',1)[1]);identity=context['symbols'][0]['id']
        return dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(dict(ids=[identity])))])])
    service.assistant.transport=transport
    uid,job=ready(service)
    a=service.workspaces.create(uid,job['id'],'我想知道这份程序如何把杂乱输入变得整齐',budget=None)
    assert a['state']['data']['intent']['kind']=='semantic'
    b=service.workspaces.create(uid,job['id'],'我想知道这份程序如何把杂乱输入变得整齐',budget=None)
    assert len(calls)==1 and service.assistant.meter.reserved==.25
    service.assistant.transport=lambda *args:dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text='{"ids":["invented.py::fake"]}')])])
    c=service.workspaces.create(uid,job['id'],'我想知道不一样的事情',budget=None)
    assert c['needs_clarification']


def test_network_failure_reuses_only_verified_public_files(service):
    uid,job=ready(service);folder=service.workspaces.root/job['id']
    (folder/'benchmarks/sources/imported/not-in-manifest.txt').write_text('local extra file',encoding='utf-8')
    def denied(url,limit):raise HTTPError(url,403,'rate limit',{},None)
    service.workspaces.loader=denied
    second=service.workspaces.start(uid,'https://github.com/example/demo','cached')
    for _ in range(100):
        second=service.workspaces.repository(uid,second['id'])
        if second['status']!='importing':break
        time.sleep(.02)
    assert second['status']=='ready' and second['import_mode']=='cached'
    assert not (service.workspaces.root/second['id']/'benchmarks/sources/imported/not-in-manifest.txt').exists()
