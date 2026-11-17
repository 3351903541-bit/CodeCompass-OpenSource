import io
import json
import time
import zipfile
import itertools
import pytest
from codecompass.product.repositories import repository_url, unpack_python, acquire, FEATURES
from codecompass.product.source_routes import build, solve
from codecompass.product.service import Service

FILES = {
 'demo/transform.py': b'''def clean(items):
    """Filter and clean input values."""
    return [x.strip() for x in items if x]

def chunk(items):
    """Group iterable into chunks."""
    for x in clean(items):
        yield [x]
''',
 'demo/codec.py': b'''def decode(text):
    """Parse encoded input."""
    try:
        return text.split(":")
    except ValueError:
        return []
''',
 'demo/helpers.py': b'''def values(items):
    return [x for x in items]

def pairs(items):
    for x in items:
        yield x
''',
}


def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for path,data in files.items(): z.writestr('repo-sha/'+path,data)
    return out.getvalue()


def loader(url,limit):
    if url.endswith('HEAD'):
        return json.dumps({'sha':'a'*40,'commit':{'committer':{'date':'2026-10-25T00:00:00Z'}}}).encode()
    return archive(FILES)


def ready(service):
    uid=service.profile()['user_id']
    service.workspaces.loader=loader
    service.workspaces.onboard(uid,dict(experience='new',months='0',familiar=[]),0)
    job=service.workspaces.start(uid,'https://github.com/example/demo','import-1')
    for _ in range(200):
        job=service.workspaces.repository(uid,job['id'])
        if job['status']!='importing': break
        time.sleep(.02)
    assert job['status']=='ready',job
    return uid,job


def test_import_plan_profile_feedback_restart(service):
    uid,job=ready(service)
    assert len(job['snapshot']['files'])==3
    assert service.workspaces.start(uid,'https://github.com/example/demo','import-1')['id']==job['id']
    first=service.workspaces.create(uid,job['id'],'理解 chunk 的分组逻辑')
    state=first['state']; result=state['result']
    assert result['status']=='FEASIBLE' and result['audit']['goal_complete'] and result['audit']['valid']
    assert not result['optimality_claim']
    assert len(result['remaining'])>=3
    assert state['data']['dependencies']
    assert sum('python.iteration' in u['concept_ids'] for u in state['data']['units'])>=2
    assert all(not e['hard'] for e in state['data']['dependencies'])
    assert {state['data']['views'][x]['path'] for x in result['remaining']}=={'demo/transform.py','demo/helpers.py'} or len(result['remaining'])>=3
    item=result['remaining'][0]
    progressed=service.workspaces.feedback(uid,first['id'],0,'read-1','read',item)
    assert progressed['state']['completed']==[item]
    assert item not in progressed['state']['result']['remaining']
    assert service.workspaces.feedback(uid,first['id'],0,'read-1','read',item)['revision']==1
    with pytest.raises(ValueError): service.workspaces.feedback(uid,first['id'],0,'stale','read',item)
    fresh=Service(service.root,service.store.path,'test_fixture')
    assert fresh.workspaces.route(uid,first['id'])['state']['completed']==[item]
    assert not fresh.store.evidence.read(uid,simulated=True)['records']
    assert fresh.create(uid,'P01_unique_read')['phase']!='baseline'


def test_goal_and_ability_change_actual_content(service):
    uid,job=ready(service)
    a=service.workspaces.create(uid,job['id'],'chunk 分组')
    other=service.workspaces.create(uid,job['id'],'decode 解析')
    assert a['state']['data']['targets']!=other['state']['data']['targets']
    profile=service.workspaces.onboard(uid,dict(experience='comfortable',months='24+',familiar=list(FEATURES)),1)
    b=service.workspaces.create(uid,job['id'],'chunk 分组')
    assert len(b['state']['result']['remaining'])<len(a['state']['result']['remaining'])
    assert b['state']['result']['learning_cost']<a['state']['result']['learning_cost']
    assert all(not g['mastered'] for g in b['state']['result']['gate'].values())
    assert not service.store.evidence.read(uid,simulated=True)['records']
    assert service.workspaces.route(uid,a['id'])['profile_changed']
    assert profile['preferences']['onboarding']['source']=='self_report'


def test_unknown_goal_budget_and_user_isolation(service):
    uid,job=ready(service)
    general=service.workspaces.create(uid,job['id'],'想了解这个项目',budget=None)
    assert general['state']['data']['intent']['kind']=='core'
    target=next(s['id'] for s in job['symbols'] if s['name']=='chunk')
    small=service.workspaces.create(uid,job['id'],'理解源码',[target],5)
    assert small['state']['result']['status']=='NO_FEASIBLE_FOUND'
    assert small['state']['result']['audit']['missing']
    uid2=service.profile()['user_id']
    with pytest.raises(ValueError): service.workspaces.repository(uid2,job['id'])
    with pytest.raises(ValueError): service.workspaces.route(uid2,small['id'])
    with pytest.raises(ValueError): service.workspaces.start(uid,'https://github.com/example/other','import-1')


@pytest.mark.parametrize('url',['http://github.com/a/b','https://evil.test/a/b','https://github.com/a/b/tree/main','https://github.com/a/..','https://github.com/a/b?token=secret','https://github.com@localhost/a/b'])
def test_url_boundaries(url):
    with pytest.raises(ValueError): repository_url(url)


def test_archive_boundaries_and_no_execution(tmp_path):
    with pytest.raises(ValueError): unpack_python(archive({'../../escape.py':b'x=1'}))
    with pytest.raises(ValueError): unpack_python(archive({'demo.py':b'x=1','DEMO.py':b'x=2'}))
    with pytest.raises(ValueError): unpack_python(archive({'CON.py':b'x=1'}))
    with pytest.raises(ValueError): unpack_python(archive({'large.py':b'x'*(513*1024)}))
    code=b'import pathlib\npathlib.Path("SHOULD_NOT_EXIST").write_text("executed")\ndef safe():\n    return 1\n'
    assert unpack_python(archive({'safe.py':code}))['safe.py']==code
    assert not (tmp_path/'SHOULD_NOT_EXIST').exists()


def test_feedback_saved_if_planner_breaks(service,monkeypatch):
    uid,job=ready(service); p=service.workspaces.create(uid,job['id'],'chunk')
    unit=p['state']['result']['remaining'][0]
    def broken(*args,**kwargs): raise RuntimeError('search unavailable')
    monkeypatch.setattr('codecompass.product.workspaces.solve',broken)
    p=service.workspaces.feedback(uid,p['id'],0,'hard-1','hard',unit)
    assert p['state']['planning_error'] and p['state']['events'][-1]['action']=='hard'
    assert not service.store.evidence.read(uid,simulated=True)['records']


def test_small_candidate_objective_against_exhaustive_subsets(service):
    uid,job=ready(service); ws=service.workspaces
    repo=ws._repo(job['id'])
    with ws.store.connect() as db: prefs=ws.preferences(db,uid)
    data=build(ws.root/job['id'],repo,'decode',None,prefs,uid,True)
    ledger=service.store.evidence.read(uid,simulated=True)
    result=solve(ws.root/job['id'],data,ledger,seconds=5)
    units={u['id']:u for u in data['units']}; ids=list(units)
    goals=set(data['request']['target_concept_ids']); values=[]
    # Independent enumeration, including duplicate-concept penalty and budget.
    for n in range(len(ids)+1):
        for subset in itertools.combinations(ids,n):
            cs=[c for x in subset for c in units[x]['concept_ids']]
            if not goals<=set(cs): continue
            objective=sum(result['costs'][x] for x in subset)+.4*(len(cs)-len(set(cs)))
            values.append(objective)
    assert result['objective']==pytest.approx(min(values))
    # Existing order is part of the optimization state, not canonicalized away.
    reference=list(reversed(result['remaining']))
    preserved=solve(ws.root/job['id'],data,ledger,reference=reference,seconds=5)
    assert preserved['remaining']==reference and preserved['switch_cost']==0
    assert preserved['state_key']=='full ordered prefix'


def test_hard_and_familiar_replan_without_claiming_mastery(service):
    uid,job=ready(service); p=service.workspaces.create(uid,job['id'],'chunk',request_id='plan-1')
    assert service.workspaces.create(uid,job['id'],'chunk',request_id='plan-1')['id']==p['id']
    with pytest.raises(ValueError): service.workspaces.create(uid,job['id'],'decode',request_id='plan-1')
    unit=p['state']['result']['remaining'][0]
    p=service.workspaces.feedback(uid,p['id'],0,'familiar','familiar',unit)
    assert p['state']['data']['self_report_familiar']
    assert all(not g['mastered'] for g in p['state']['result']['gate'].values())
    assert service.profile(uid)['preferences']['source_feedback']
    unit=p['state']['result']['remaining'][0]
    p=service.workspaces.feedback(uid,p['id'],1,'hard','hard',unit)
    assert p['revision']==2 and p['state']['result']['audit']['valid']
    assert not service.store.evidence.read(uid,simulated=True)['records']


def test_issue_matching_filters_pr_cache_and_fallback(service,monkeypatch):
    uid,job=ready(service); route=service.workspaces.create(uid,job['id'],'chunk')
    rows=[dict(number=1,state='open',title='chunk fails for empty input',body='demo/transform.py',html_url='https://github.com/example/demo/issues/1',labels=[]),
          dict(number=2,state='open',title='chunk PR',html_url='https://github.com/example/demo/issues/2',pull_request={}),
          dict(number=3,state='open',title='chunk malicious link',html_url='https://evil.test/issues/3')]
    calls=[]
    def issue_fetch(url,limit): calls.append(url);return json.dumps(rows).encode()
    monkeypatch.setattr('codecompass.product.source_issues.fetch',issue_fetch)
    result=service.workspaces.issues.get(uid,route['id'],True)
    assert [x['number'] for x in result['items']]==[1]
    assert result['items'][0]['matched_paths']==['demo/transform.py']
    service.workspaces.issues.get(uid,route['id'],True);assert len(calls)==1
    path=service.workspaces.root/job['id']/'issues.json';cache=json.loads(path.read_text(encoding='utf-8'));cache['attempted_at']='2000-01-01T00:00:00+00:00';path.write_text(json.dumps(cache),encoding='utf-8')
    def failed(*args): raise TimeoutError()
    monkeypatch.setattr('codecompass.product.source_issues.fetch',failed)
    monkeypatch.setattr('codecompass.product.source_issues.fetch_page',failed)
    fallback=service.workspaces.issues.get(uid,route['id'],True)
    assert fallback['items']==result['items'] and fallback['error'] and fallback['captured_at']==result['captured_at']


def test_tampered_snapshot_and_interrupted_import_preserve_route(service):
    uid,job=ready(service); route=service.workspaces.create(uid,job['id'],'chunk')
    source=service.workspaces.root/job['id']/'benchmarks/sources/imported/demo/transform.py'
    source.write_text('def altered():\n    return 0\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Snapshot byte mismatch'): service.workspaces.create(uid,job['id'],'chunk')
    assert service.workspaces.route(uid,route['id'])['state']['result']['status']=='FEASIBLE'
    with service.store.connect() as db:
        db.execute('INSERT INTO product_repositories VALUES(?,?,?,?,?,?,?)',('r_interrupted',uid,'interrupted','example/demo','importing','pending','2026-10-25T00:00:00Z'))
    restored=Service(service.root,service.store.path,'test_fixture')
    assert restored.workspaces.repository(uid,'r_interrupted')['status']=='interrupted'
    assert restored.workspaces.route(uid,route['id'])['state']['goal']=='chunk'
