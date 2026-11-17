"""Boundary verification only. Production business modules are never rewritten."""
import argparse
from collections import Counter
from contextlib import contextmanager
from itertools import combinations, permutations
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import traceback
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--cache',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--helpers',type=Path,required=True)
args=parser.parse_args()
root=args.root.resolve()
args.output.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(root/'src'),str(root),str(args.helpers.resolve())]
from reproduce_r2 import CASES,load_inputs,loader_for
from codecompass.graph import read_snapshot
from codecompass.planner.adaptive import route_audit
from codecompass.product import workspaces
from codecompass.product.goal_resolution import enrich
from codecompass.product.repositories import FEATURES
from codecompass.product.service import Service
from codecompass.product.source_routes import solve
from scripts.serve_product import make_server

snapshots={name:(repo,path,snap) for name,repo,path,snap in load_inputs(root,args.cache.resolve())}
p=root/workspaces.DEMO_SOURCE/'snapshot.json'
snapshots['itsdangerous']=('pallets/itsdangerous',p,json.loads(p.read_text(encoding='utf-8')))
actual=workspaces.optimize_remaining_order
calls=[]
checks={}
raw={}
active=''

def output(name,value):
    (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

@contextmanager
def http(service):
    server=make_server(service,0)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    opener=build_opener(ProxyHandler({}))
    url=f'http://127.0.0.1:{server.server_port}/api/product/'
    token=''
    def request(endpoint,payload=None,status=200):
        data=json.dumps(payload).encode() if payload is not None else None
        req=Request(url+endpoint,data=data,headers={'Content-Type':'application/json','X-Session-Token':token})
        try:
            res=opener.open(req,timeout=30)
        except HTTPError as error:
            res=error
        with res:
            body=json.load(res)
            assert res.status==status,(endpoint,res.status,body)
        if active and endpoint!='bootstrap':
            raw[active].append(dict(endpoint=endpoint,payload=payload,response_status=status,response=body))
        return body['data'] if status==200 else body['error']
    token=request('bootstrap')['token']
    def close():
        if thread.is_alive():
            server.shutdown()
            server.server_close()
            thread.join()
    request.close=close
    try:
        yield request
    finally:
        close()

def capture(data,result,completed,reference):
    ordered=actual(data,result,completed,reference)
    calls.append((data,result,list(completed),list(reference),ordered))
    return ordered

def create(name,profile=None,scenario=None):
    repo,snapshot_path,snap=snapshots[name]
    uid=api('profile',{})['user_id']
    prefs=profile or dict(experience='new',months='0',familiar=[])
    api('onboarding',dict(user_id=uid,value=prefs,revision=0))
    loader=loader_for(snap['commit'],read_snapshot(snapshot_path.parent,snap))
    job=service.workspaces.start(uid,'https://github.com/'+repo,'import',bundled_loader=loader)
    assert job['status']=='ready'
    chosen=None
    goal='解码编码后的文本'
    if name in CASES:
        goal,suffix,names=scenario or next(c for c in CASES[name] if c[0] in ('legacy-truncate','pending-jobs','deduplication'))
        augmented=enrich(service.workspaces.root/job['id'],service.workspaces._repo(job['id']))
        chosen=[next(s['id'] for s in augmented['symbols'] if s['name']==label and s['path'].endswith(suffix) and not s['test_source'])
                for label in names]
    route=api('route',dict(user_id=uid,repository_id=job['id'],goal=goal,selected=chosen,budget=120,request_id='plan'))
    assert route['state']['result']['status']=='FEASIBLE'
    return uid,route,prefs

def feedback(uid,route,request_id,action,unit=None,status=200):
    return api('route-feedback',dict(user_id=uid,route_id=route['id'],revision=route['revision'],
               request_id=request_id,action=action,unit_id=unit),status)

def audit(data,result,completed,reference):
    req={**data['request'],'budget':result['budget']}
    suffix=result['remaining']
    assert len(suffix)==len(set(suffix)) and not set(suffix)&set(completed)
    assert result['completed']==list(completed)
    rerun=route_audit(req,data['units'],result['gate'],suffix,result['costs'],completed,reference,1,result['spent'])
    assert rerun==result['audit'] and rerun['valid'] and rerun['goal_complete']
    by_id={u['id']:u for u in data['units']}
    concepts=[c for u in (*completed,*suffix) for c in by_id[u]['concept_ids']]
    assert math.isclose(result['objective'],rerun['objective']+.4*(len(concepts)-len(set(concepts))),abs_tol=1e-9)
    assert result['switch_cost']==rerun['switch_cost']
    assert result['spent']+result['objective']<=result['budget']+1e-9
    order=result.get('reading_order')
    if order and order['scope']=='remaining':
        assert set(order['explanations'])==set(suffix)
        metrics=order['metrics']
        if metrics is not None:
            parents={(e['before'],e['after']) for e in data['verified_order_edges']
                     if {e['before'],e['after']}<=set(suffix)}
            pos={u:i for i,u in enumerate(suffix)}
            assert metrics['dependency_violations']==sum(pos[a]>=pos[b] for a,b in parents)
            if order['status']=='applied':
                assert metrics['dependency_violations']==0
                def gaps(candidate):
                    return sum(bool(d['suppliers']) and all(candidate.index(x)>candidate.index(d['target']) for x in d['suppliers'])
                               for d in metrics['demands'])
                assert gaps(suffix)==metrics['avoidable_supply_gap_count']
                if len(suffix)<=8 and order['exact_optimal']:
                    feasible=(seq for seq in permutations(suffix) if all(seq.index(a)<seq.index(b) for a,b in parents))
                    assert min(map(gaps,feasible))==metrics['avoidable_supply_gap_count']
        if order['status']=='applied':
            seen=set(data['order_familiar_features'])
            for uid in completed:
                seen.update(data['views'][uid]['pedagogical_features'])
            for uid in suffix:
                new=set(data['views'][uid]['pedagogical_features'])-seen
                assert order['explanations'][uid]['new_features']==sorted(new)
                seen.update(new)

def snapshot(name,route,prefs):
    s=route['state']; result=s['result']
    return dict(repository=name,commit=snapshots[name][2]['commit'],profile=prefs,goal=s['goal'],
         objective_formula=result['objective_formula'],revision=route['revision'],completed=s['completed'],
         remaining=result['remaining'],titles=[s['data']['views'][u]['title'] for u in result['remaining']],
         candidates=[dict(id=u['id'],title=s['data']['views'][u['id']]['title'],kind=s['data']['views'][u['id']]['kind'])
                     for u in s['data']['units']],spent=s['spent'],completed_costs=s['completed_costs'],
         J=result['objective'],switch_cost=result['switch_cost'],budget=result['budget'],route_audit=result['audit'],
         reading_order=result.get('reading_order'),events=s['events'])

def t1():
    trials=[]
    profiles=[['python.functions','python.iteration','python.containers','python.generators','python.classes','python.exceptions'],
              ['python.functions','python.iteration','python.containers'],['python.functions'],
              sorted(set(FEATURES)-{'python.async'})]
    for name in ('boltons','python-slugify'):
        for goal in CASES[name]:
            for familiar in profiles:
                prefs=dict(experience='new',months='0',familiar=familiar)
                uid,before,_=create(name,prefs,goal)
                first=before['state']['result']['remaining'][0]
                prior=len(calls)
                after=feedback(uid,before,'hard','hard',first)
                assert len(calls)==prior+1 and not after['state']['planning_error']
                data,stage,done,reference,result=calls[-1]
                audit(data,result,done,reference)
                new_ids=set(result['remaining'])-set(before['state']['result']['remaining'])
                new_foundations=[u for u in result['remaining'] if u in new_ids and data['views'][u]['kind']=='foundation']
                previous_candidates={u['id'] for u in before['state']['data']['units']}
                candidates={u['id'] for u in data['units']}
                trials.append(dict(repo=name,goal=goal[0],familiar=familiar,added=sorted(new_ids),
                                   entered_optimizer=True,new_foundations=new_foundations,
                                   added_candidates=sorted(candidates-previous_candidates),removed_candidates=sorted(previous_candidates-candidates)))
                if new_foundations:
                    for u in new_foundations:
                        span=data['views'][u]['span']
                        assert span['path'] in {e['path'] for e in after['state']['snapshot']['files']}
                    assert result['reading_order']['status']=='applied'
                    assert result['reading_order']['metrics']['avoidable_supply_gap_count']==0
                    explanations=result['reading_order']['explanations']
                    assert all(after['state']['data']['views'][u]['order_reason']==row['reason'] for u,row in explanations.items())
                    projected=api('source-map?user='+uid+'&id='+after['id'])
                    assert projected['remaining_order_explanations']==explanations
                    updated_profile=api('profile?user='+uid)['preferences']
                    return dict(status='passed',evidence_type='real_http_feedback',trials=trials,
                                before=snapshot(name,before,prefs),after=snapshot(name,after,prefs),
                                after_familiar=updated_profile['onboarding']['familiar'],
                                after_source_feedback=updated_profile['source_feedback'],
                                stage1_remaining=stage['remaining'],reference=reference,
                                added_foundations=[data['views'][u] for u in new_foundations])
    return dict(status='not_naturally_triggered',evidence_type='real_http_feedback',trials=trials)

def stage_for(uid,route,reference,budget=120,completed=(),spent=0):
    state=route['state']
    ledger=service.store.evidence.read(uid,simulated=True)
    return solve(service.workspaces.root/route['repository_id'],state['data'],ledger,completed=completed,
                 reference=reference,spent=spent,budget=budget)

def inverted():
    name='python-slugify'
    uid,route,prefs=create(name)
    data=route['state']['data']
    previous=route['state']['result']['remaining']
    edges=[e for e in data['verified_order_edges'] if {e['before'],e['after']}<=set(previous)]
    assert edges
    reference=list(reversed(previous))
    stage=stage_for(uid,route,reference)
    assert stage['status']=='FEASIBLE' and set(stage['remaining'])==set(previous)
    assert any(stage['remaining'].index(e['before'])>stage['remaining'].index(e['after']) for e in edges)
    return name,uid,route,prefs,reference,stage

def t2():
    name,uid,before,prefs,reference,stage=inverted()
    data=before['state']['data']
    optimized=actual(data,stage,[],reference)
    assert optimized['reading_order']['method']=='exact_supply_dp'
    assert optimized['remaining']!=stage['remaining'] and optimized['switch_cost']>stage['switch_cost']
    audit(data,optimized,[],reference)
    raw[active].append(dict(constructed_reference=reference,stage1=stage,optimized=optimized,
                            verified_edges=data['verified_order_edges']))
    return dict(status='passed',evidence_type='adversarial_invariant_probe',before=snapshot(name,before,prefs),
                event=dict(action='constructed_reference',reference=reference),stage1=stage,after=optimized)

def t3():
    name,uid,before,prefs,reference,stage=inverted()
    data=before['state']['data']
    leading=stage['remaining'][0]
    edges=[e for e in data['verified_order_edges'] if e['after']==leading and e['before'] in stage['remaining']]
    assert edges and leading!=before['state']['result']['remaining'][0]
    refused=feedback(uid,before,'skip-probe','read',leading,status=400)
    persisted=api('route?user='+uid+'&id='+before['id'])
    assert persisted==before
    # Isolated legacy-state simulation: preserve actual units and a legally audited Stage 1 result.
    injected={**before['state'],'result':stage}
    with service.store.connect() as database:
        database.execute('UPDATE product_source_routes SET state_json=? WHERE id=? AND user_id=?',
                        (json.dumps(injected,ensure_ascii=False),before['id'],uid))
    after=feedback(uid,before,'historical-probe','read',leading)
    s=after['state']; built,raw_stage,done,actual_ref,result=calls[-1]
    audit(built,result,done,actual_ref)
    assert s['completed']==[leading] and s['completed_costs'][leading]==stage['costs'][leading]
    assert s['spent']==stage['costs'][leading] and not s['planning_error']
    wanted={e['before'] for e in edges}
    assert wanted & set(s['result']['remaining'])
    historical=s['result']['reading_order']['historical_order_conflicts']
    assert all(dict(before=u,after=leading) in historical for u in wanted & set(s['result']['remaining']))
    raw[active].append(dict(isolated_seed=stage,refused=refused,after=after,reference=actual_ref))
    return dict(status='passed_with_constructed_history',evidence_type=['real_http_rejected_skip','persisted_legacy_state_probe'],
                before=snapshot(name,before,prefs),http_rejection=refused,constructed_stage1=stage,
                event=dict(action='read',unit=leading),after=snapshot(name,after,prefs))

def t4():
    name,uid,before,prefs,reference,stage=inverted()
    data=before['state']['data']
    unrestricted=actual(data,stage,[],reference)
    assert unrestricted['remaining']!=stage['remaining'] and unrestricted['objective']>stage['objective']
    budget=(unrestricted['objective']+stage['objective'])/2
    tight=stage_for(uid,before,reference,budget=budget)
    assert tight['remaining']==stage['remaining'] and tight['audit']['valid']
    fallback=actual(data,tight,[],reference)
    assert fallback['reading_order']['reason']=='reordered_budget_exceeded'
    assert {k:v for k,v in fallback.items() if k!='reading_order'}==tight
    audit(data,fallback,[],reference)
    verified={(e['before'],e['after']) for e in data['verified_order_edges'] if {e['before'],e['after']}<=set(reference)}
    compliant=[]
    for route in permutations(reference):
        if all(route.index(a)<route.index(b) for a,b in verified):
            replay=route_audit({**data['request'],'budget':120},data['units'],tight['gate'],route,
                               tight['costs'],[],reference,1,0)
            assert replay['valid'] and replay['goal_complete']
            compliant.append(dict(route=route,J=replay['objective']+tight['duplicate_cost']))
    assert min(entry['J'] for entry in compliant)>budget
    raw[active].append(dict(constructed_reference=reference,unrestricted=unrestricted,tight_stage1=tight,
                            fallback=fallback,compliant_permutations=compliant))
    return dict(status='passed',evidence_type='adversarial_invariant_probe',before=snapshot(name,before,prefs),
                event=dict(action='tight_budget_reference',budget=budget,reference=reference),
                legal_stage1=tight,reordering_if_budget_allows=unrestricted,after=fallback,
                min_verified_precedence_J=min(entry['J'] for entry in compliant))

def t5():
    name='itsdangerous'
    def series():
        uid,before,prefs=create(name)
        first=before['state']['result']['remaining'][0]
        one=feedback(uid,before,'same-read','read',first)
        one_profile=api('profile?user='+uid)
        replay=feedback(uid,before,'same-read','read',first)
        assert one==replay and api('profile?user='+uid)==one_profile
        repeat_with_new_id=feedback(uid,one,'other-read','read',first,status=400)
        assert repeat_with_new_id['message']
        second=feedback(uid,one,'first-replan','replan')
        third=feedback(uid,second,'second-replan','replan')
        assert second['revision']+1==third['revision']
        assert len(third['state']['events'])==3 and third['state']['completed']==[first]
        assert third['state']['spent']==one['state']['spent']
        final_profile=api('profile?user='+uid)
        assert one_profile['preferences']['learning_growth']['readings']==final_profile['preferences']['learning_growth']['readings']
        return uid,before,prefs,third,final_profile
    uid,initial,prefs,end,profile=series()
    uid2,start2,prefs2,end2,profile2=series()
    def score(route,p):
        s=route['state'];r=s['result']
        return dict(spent=s['spent'],completed=s['completed'],completed_costs=s['completed_costs'],
                    remaining=r['remaining'],J=r['objective'],switch_cost=r['switch_cost'],audit=r['audit'],
                    reading_order=r['reading_order'],readings=p['metrics']['learning']['readings'],
                    events=[(e['request_id'],e['action'],e['unit_id']) for e in s['events']])
    result=score(end,profile)
    assert result==score(end2,profile2)
    api.close()
    restarted=Service(root,db_path,'test_fixture')
    with http(restarted) as fresh:
        restored=fresh('route?user='+uid+'&id='+end['id'])
        restored_profile=fresh('profile?user='+uid)
        assert restored==end and restored_profile==profile
        same=fresh('route-feedback',dict(user_id=uid,route_id=end['id'],revision=initial['revision'],request_id='same-read',
                                        action='read',unit_id=end['state']['completed'][0]))
        assert same==restored
    return dict(status='passed',evidence_type='real_http_feedback_and_restart',before=snapshot(name,initial,prefs),
                after=snapshot(name,end,prefs),same_event_no_duplicate=True,new_request_events=3,
                archived_read_replay_returns_latest_state=True,stable_repeated_sequences=True,restarted=True,comparison=result)

with TemporaryDirectory(prefix='p1-final-',dir=args.output) as scratch:
    db_path=Path(scratch)/'boundary.sqlite3'
    service=Service(root,db_path,'test_fixture')
    with http(service) as api, patch.object(workspaces,'optimize_remaining_order',capture):
        for code,test in [('T1',t1),('T2',t2),('T3',t3),('T4',t4),('T5',t5)]:
            active=code
            raw[code]=[]
            try:
                checks[code]=test()
            except Exception as error:
                checks[code]=dict(status='failed',error=str(error),traceback=traceback.format_exc())
            output(code+'_raw.json',raw[code])
            (args.output/(code+'.log')).write_text(json.dumps(checks[code],ensure_ascii=False,indent=2),encoding='utf-8')
            print(code,checks[code]['status'],checks[code].get('error',''),flush=True)
    output('freeze_boundary_verification.json',dict(tests=checks,status_counts=Counter(c['status'] for c in checks.values())))
if any(v['status']=='failed' for v in checks.values()):
    sys.exit(1)
