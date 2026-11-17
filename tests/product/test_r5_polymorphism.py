import json
from pathlib import Path

from codecompass.product.call_resolution import cross_file_relations
from codecompass.product.goal_resolution import enrich
from codecompass.product.repositories import acquire
from .test_source_workspaces import archive


def test_snapshot_overrides_multiple_bases_and_explicit_reexports(tmp_path):
    files={
        'pkg/__init__.py':b'from .base import helper as public\n',
        'pkg/base.py':b'def helper(): return 1\nclass Base:\n    def act(self): return 2\n',
        'pkg/other.py':b'class Other:\n    def act(self): return 3\n',
        'pkg/client.py':b'''from .base import Base
from .other import Other
from pkg import public as call_public
class Parent(Base):
    def run(self): return self.act()
class Isolated(Base):
    def run(self): return self.act()
class Mixed(Base, Other):
    def run(self): return self.act()
def main(): return call_public()
''',
        'pkg/override.py':b'from .client import Parent\nclass Child(Parent):\n    def act(self): return 4\n',
    }
    def loader(url,limit):
        return json.dumps({'sha':'a'*40}).encode() if url.endswith('/HEAD') else archive(files)
    root=Path(__file__).resolve().parents[2]
    repo=enrich(tmp_path,acquire(root,tmp_path,'example/poly',loader=loader))
    names={s['id']:s['name'] for s in repo['symbols']}
    sites=list(cross_file_relations(files,repo['symbols'],names))
    assert {(names[e['caller']],names[e['callee']]) for e in sites if 'kind' not in e}=={
        ('main','helper'),('Isolated.run','Base.act')}
    assert {(names[e['caller']],names[e['callee']],e['basis']) for e in sites if e.get('kind')=='call_candidate'}=={
        ('Parent.run','Base.act','known_subclass_override'),
        ('Mixed.run','Base.act','ambiguous_method_dispatch'),
        ('Mixed.run','Other.act','ambiguous_method_dispatch')}
