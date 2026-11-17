import json
from pathlib import Path

from codecompass.product.call_resolution import cross_file_relations
from codecompass.product.goal_resolution import enrich
from codecompass.product.repositories import acquire
from codecompass.product.source_routes import build
from .test_source_workspaces import archive


FILES = {
    'pkg/__init__.py': b'',
    'pkg/one.py': b'def helper(): return 1\nclass Base:\n    def act(self): return 2\n',
    'pkg/two.py': b'''from .one import helper
from .one import helper as renamed
from pkg.one import helper as absolute
from . import one as module
import pkg.one as qualified
from .one import Base as Parent
from .duplicate import bad
def rel(): return helper()
def alias(): return renamed()
def abs_call(): return absolute()
def mod(): return module.helper()
def mod_abs(): return qualified.helper()
def shadow(renamed): return renamed()
def local():
    renamed = lambda: 0
    return renamed()
def ambiguous(): return bad()
class Child(Parent):
    def inherited(self): return self.act()
class Override(Parent):
    def act(self): return 3
    def check(self): return self.act()
''',
    'pkg/duplicate.py': b'def bad(): return 1\ndef bad(): return 2\n',
    'pkg/star.py': b'from .one import *\ndef elsewhere(): return helper()\n',
}


def test_cross_file_imports_inheritance_and_stage_one_isolation(tmp_path):
    root=Path(__file__).resolve().parents[2]
    def loader(url,limit):
        return json.dumps({'sha':'a'*40}).encode() if url.endswith('/HEAD') else archive(FILES)
    repo=enrich(tmp_path,acquire(root,tmp_path,'example/cross',loader=loader))
    symbols=repo['symbols']; names={s['id']:s['name'] for s in symbols}
    sites=list(cross_file_relations(FILES,symbols,names.keys()))
    calls={(names[s['caller']],names[s['callee']]) for s in sites if s.get('kind')!='verified_inheritance'}
    assert calls=={(name,'helper') for name in ('rel','alias','abs_call','mod','mod_abs')}|{('Child.inherited','Base.act')}
    assert {(names[s['caller']],names[s['callee']]) for s in sites if s.get('kind')=='verified_inheritance'}=={
        ('Child','Base'),('Override','Base')}
    assert all(s['line']>0 and s['path'] in FILES for s in sites)
    ids={name:uid for uid,name in names.items()}
    alone=build(tmp_path,repo,'rel',[ids['rel']],{},'fixture',True)
    assert not alone['dependencies'] and not alone['verified_order_edges']
    together=build(tmp_path,repo,'rel',[ids['rel'],ids['helper']],{},'fixture',True)
    assert not together['dependencies']
    edge,=together['verified_order_edges']
    assert edge['caller']==ids['rel'] and edge['callee']==ids['helper']
