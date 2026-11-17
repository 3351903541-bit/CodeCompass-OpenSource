import json
from pathlib import Path
import pytest

from codecompass.learner.model import initial_state
from codecompass.product.goal_resolution import enrich
from codecompass.product.repositories import DefinitionIndex, acquire, normalize_symbols
from codecompass.product.source_routes import build, solve
from .test_source_workspaces import archive

FILES={
    'a.py':b'''if 1:
    def choose(): return []
else:
    def choose(): return {}
class A:
    @property
    def value(self): return self.same()
    @value.setter
    def value(self, x): self.x=x
    def same(self): return 1
class B:
    def same(self): return 2
def shared(): return 1
def unique(): return shared()
''',
    'b.py':b'def shared(): return 2\ndef shared(): return 3\n',
}


def test_exact_source_identity_pipeline(tmp_path):
    root=Path(__file__).resolve().parents[2]
    def loader(url,limit):
        return json.dumps({'sha':'a'*40}).encode() if url.endswith('/HEAD') else archive(FILES)
    raw=acquire(root,tmp_path,'example/identity',loader=loader)
    assert len(raw['symbols'])==len({s['id'] for s in raw['symbols']})
    repo=enrich(tmp_path,raw)
    symbols=repo['symbols']
    for name,locations in [('choose',{2,4}),('A.value',{6,8})]:
        matches=[s for s in symbols if s['name']==name]
        assert {s['span']['start_line'] for s in matches}==locations
    assert len([s for s in symbols if s['name']=='shared'])==3
    assert {s['name'] for s in symbols}>={'A.same','B.same','unique'}
    assert next(s for s in symbols if s['name']=='A.value')['calls']==['self.same']
    unique=next(s for s in symbols if s['name']=='unique')
    merged=normalize_symbols([unique,{**unique,'calls':['other']}])
    assert merged[0]['calls']==['other','shared']
    with pytest.raises(ValueError,match='distinct spans'):
        normalize_symbols([unique,{**unique,'span':{**unique['span'],'start_line':1}}])
    ledger=initial_state('fixture',is_simulated=True)
    for targets in [[unique['id']],[s['id'] for s in symbols if s['name'] in {'choose','A.value','shared'}]]:
        data=build(tmp_path,repo,'源码定义',targets,{},'fixture',True)
        assert len(set(data['request']['unit_ids']))==len(data['units'])
        assert solve(tmp_path,data,ledger,budget=120)['status']=='FEASIBLE'


def test_legacy_fallback_reports_ambiguity():
    a=('a.py','single','function',1,2)
    b=('a.py','repeat','function',4,5)
    c=('a.py','repeat','function',7,8)
    table=DefinitionIndex([(a,'first'),(b,'second'),(c,'third')]); notes=[]
    assert table.match(c,notes)=='third' and not notes
    assert table.match((*a[:3],20,21),notes)=='first'
    assert table.match((*b[:3],20,21),notes) is None
    assert [n['status'] for n in notes]==['unique_legacy_fallback','ambiguity']
