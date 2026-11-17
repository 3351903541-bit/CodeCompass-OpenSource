import json
from pathlib import Path
from itertools import permutations
from random import Random

from codecompass.product.goal_resolution import enrich
from codecompass.product.reading_order import exact_order, optimize_first_order
from codecompass.product.repositories import acquire
from codecompass.product.source_routes import build, solve
from .test_source_workspaces import archive, ready


def test_exact_topological_order_matches_independent_permutations():
    random = Random(42)
    for size in range(1,8):
        ids = list(range(size))
        for _ in range(4):
            parents = {i:{j for j in range(i) if random.random()<.2} for i in ids}
            features = {i:frozenset(j for j in range(5) if random.random()<.4) for i in ids}
            conditions = {i:([{'suppliers':list(range(i))}] if i and random.random()<.4 else []) for i in ids}
            familiar = {0}
            choices = []
            for seq in permutations(ids):
                seen = familiar.copy(); visited = set(); changes = []
                for i in seq:
                    if parents[i]-visited or not all(visited.intersection(c['suppliers']) for c in conditions[i]):
                        break
                    changes.append(len(features[i]-seen)); seen.update(features[i]); visited.add(i)
                else:
                    choices.append((max(changes),sum(n*n for n in changes),seq))
            route,count,states = exact_order(ids,parents,features,familiar,conditions)
            assert (tuple(route),count)==(min(choices)[2],len(choices))
    ids = list(range(10)); parents = {i:set() for i in ids}; features = {i:frozenset() for i in ids}
    assert exact_order(ids,parents,features,set())==(ids,3628800,2048)


def test_first_route_uses_verified_target_order_and_preserves_selection(service):
    uid, job = ready(service)
    ws = service.workspaces
    ids = {s['name']:s['id'] for s in job['symbols']}
    first = ws.create(uid,job['id'],'chunk',[ids['chunk'],ids['clean']])['state']
    data = first['data']; final = first['result']
    edge, = data['verified_order_edges']
    assert (edge['callee'],edge['caller'],edge['line']) == (ids['clean'],ids['chunk'],7)
    assert final['remaining'].index(edge['before']) < final['remaining'].index(edge['after'])
    assert all(not u['prerequisites'] for u in data['units'])
    assert len({u['id'] for u in data['units']}) == len(data['units'])
    ledger = service.store.evidence.read(uid,simulated=True)
    original = solve(ws.root/job['id'],data,ledger,budget=120)
    for key in ('objective','costs','audit','budget','gate','duplicate_cost','learning_cost','switch_cost'):
        assert final[key] == original[key]
    assert set(final['remaining']) == set(original['remaining'])
    assert optimize_first_order(data,original,reference=original['remaining']) is original
    assert optimize_first_order(data,original,completed=original['remaining'][:1]) is original
    assert '建议先读' in data['views'][edge['before']]['order_reason']
    data['verified_order_edges'].append({'before':edge['after'],'after':edge['before']})
    fallback = optimize_first_order(data,original)
    cycle = fallback['reading_order']
    assert cycle['status'] == 'fallback' and cycle['reason'] == 'verified_call_cycle'
    assert cycle['cycles'] and cycle['dropped_cycle_edges'] == [] and fallback['remaining'] == original['remaining']


def test_scoped_attribute_resolution_does_not_guess_module_or_nested_calls(tmp_path):
    root = Path(__file__).resolve().parents[2]
    files = {'probe.py': b'''import bridge as module
def helper(): return 1
def func(): return 2
def same(): return 3
def direct(): return helper()
def ambiguous(): return same()
def qualified(): return module.func()
def outer():
    def nested(): return helper()
    return 0
class Base:
    def method(self): return helper()
class Child(Base):
    def public(self): return self.method()
    def _hidden(self): return self.method(), module.func(), Child.public(self)
''', 'other.py': b'def same(): return 4\n'}
    def loader(url,limit):
        return json.dumps({'sha':'a'*40}).encode() if url.endswith('/HEAD') else archive(files)
    repo = enrich(tmp_path,acquire(root,tmp_path,'example/probe',loader=loader))
    rows = {s['name']:s for s in repo['symbols']}
    names = {s['id']:s['name'] for s in repo['symbols']}
    expected = {'direct':{'helper'},'ambiguous':set(),'qualified':set(),
                'Child.public':{'Base.method'},'Child._hidden':{'Base.method','Child.public'},'outer':set()}
    for caller,callees in expected.items():
        data = build(tmp_path,repo,caller,[rows[caller]['id']],{},'fixture',True)
        assert {names[e['target']] for e in data['dependencies']} == callees
    assert rows['Child.public']['calls'] == ['self.method']
    assert rows['Child._hidden']['calls'] == ['Child.public','module.func','self.method']
    assert rows['outer']['calls'] == []
