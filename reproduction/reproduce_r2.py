"""Offline R2 diagnostics using manifest-validated local public source bytes."""
import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile


SLUG = '35aca63fc2672cba2c739ff6dff685a4f26a4f9a'
SCHEDULE = '82a43db1b938d8fdf60103bd41f329e06c8d3651'
CASES = {
    'python-slugify': [('legacy-truncate', '_legacy.py', ('slugify', 'smart_truncate')),
                      ('public-wrapper', '/slugify.py', ('slugify',)),
                      ('modern-helpers', '/slugify.py', ('_decode_entities', '_numeric_reference', '_modern_truncate'))],
    'schedule': [('pending-jobs', '__init__.py', ('Scheduler.run_pending', 'Scheduler._run_job', 'Job.run')),
                 ('job-setup', '__init__.py', ('Job.do', 'Job._schedule_next_run')),
                 ('job-query', '__init__.py', ('Scheduler.get_jobs', 'Scheduler.clear', 'Scheduler.cancel_job'))],
    'boltons': [('chunking', 'iterutils.py', ('chunked', 'chunked_iter')),
                ('deduplication', 'iterutils.py', ('unique', 'unique_iter')),
                ('strip-ends', 'iterutils.py', ('strip', 'strip_iter', 'lstrip_iter', 'rstrip_iter'))],
}
STAGE = {'foundation': 0, 'related': 1, 'target': 2}


def load_inputs(root, cache):
    manifests = [p for p in cache.glob('*/benchmarks/sources/imported/snapshot.json')]
    for key, repo, commit in [('python-slugify','un33k/python-slugify',SLUG), ('schedule','dbader/schedule',SCHEDULE)]:
        matches = [(p, json.loads(p.read_text(encoding='utf-8'))) for p in sorted(manifests)]
        p, snap = next((p,s) for p,s in matches if s['commit']==commit and s['url']=='https://github.com/'+repo)
        yield key, repo, p, snap
    p = root/'benchmarks/sources/boltons/snapshot.json'
    yield 'boltons','mahmoud/boltons',p,json.loads(p.read_text(encoding='utf-8'))


def loader_for(commit, files):
    buffer = io.BytesIO()
    with ZipFile(buffer,'w') as z:
        for name, raw in sorted(files.items()):
            z.writestr('fixed/'+name,raw)
    def loader(url, limit):
        if url.endswith('/HEAD'):
            return json.dumps({'sha':commit}).encode()
        assert url.endswith('/zipball/'+commit)
        return buffer.getvalue()
    return loader


def diagnostic(root, scratch, cache, baseline_only, all_cases):
    sys.path[:0] = [str(root/'src'),str(root)]
    from codecompass.graph import read_snapshot
    from codecompass.learner.model import initial_state
    from codecompass.product.repositories import acquire
    from codecompass.product.goal_resolution import enrich
    from codecompass.product.source_routes import build, solve
    if not baseline_only:
        from codecompass.product.reading_order import optimize_first_order
    all_rows = {}; repos = {}
    for key,name,manifest,snap in load_inputs(root,cache):
        files=read_snapshot(manifest.parent,snap)
        folder=scratch/key
        repo=enrich(folder,acquire(root,folder,name,loader=loader_for(snap['commit'],files)))
        repos[key]=dict(input_snapshot=snap['snapshot_id'], dynamic_snapshot=repo['snapshot']['snapshot_id'],commit=snap['commit'],
                        input_manifest_sha256=snap['hash'],input_files=len(files),imported_files=len(repo['snapshot']['files']))
        for label,suffix,symbol_names in CASES[key]:
            if not all_cases and label not in {'legacy-truncate','pending-jobs','deduplication'}:
                continue
            chosen=[]
            for symbol in symbol_names:
                matches=[s for s in repo['symbols'] if s['name']==symbol and s['path'].endswith(suffix) and not s['test_source']]
                assert len(matches)==1,(label,symbol,matches)
                chosen.append(matches[0])
            ledger=initial_state('r2',is_simulated=True)
            prefs={'onboarding':{'experience':'new','familiar':[]}}
            data=build(folder,repo,label,[s['id'] for s in chosen],prefs,'r2',True)
            base=solve(folder,data,ledger,budget=120)
            assert base['status']=='FEASIBLE' and base['audit']['valid'] and base['audit']['goal_complete'],label
            views=data['views']; ids=base['remaining']
            result=dict(targets=chosen,dependencies=data['dependencies'],candidates=data['units'],views=views,
                        stage1=base, verified_order_edges=data.get('verified_order_edges',[]))
            if not baseline_only:
                ordered=optimize_first_order(data,base)
                assert ordered['reading_order']['status']=='applied', (label,ordered['reading_order'])
                methods={'no_tiebreak':sorted(ids),'category_baseline':sorted(ids,key=lambda uid:(STAGE[views[uid]['kind']],uid)),
                         'ppt_order':ordered['remaining']}
                def score(route):
                    seen=set(data['order_familiar_features']); steps=[]
                    for uid in route:
                        features=set(views[uid]['pedagogical_features']);steps.append(len(features-seen));seen.update(features)
                    pos={u:i for i,u in enumerate(route)}
                    edges={(e['before'],e['after']) for e in data['verified_order_edges'] if e['before'] in pos and e['after'] in pos}
                    dropped={tuple(e) for e in ordered['reading_order']['dropped_cycle_edges']}
                    eligible=edges-dropped
                    violations=sorted((a,b) for a,b in eligible if pos[a]>=pos[b])
                    return dict(ids=route,names=[views[u]['title'] for u in route],delta=steps,mcs=max(steps,default=0),
                                squares=sum(x*x for x in steps), eligible_edges=len(eligible),
                                cycle_edges_excluded=len(edges & dropped),violations=violations)
                result.update(methods={k:score(v) for k,v in methods.items()},stage2=ordered)
                assert set(ordered['remaining'])==set(ids) and ordered['objective']==base['objective']
                assert not result['methods']['ppt_order']['violations']
                assert optimize_first_order(data,base,reference=ids) is base
                assert optimize_first_order(data,base,completed=ids[:1]) is base
            all_rows[key+'/'+label]=result
    probes = {}
    if not baseline_only:
        original = Path(__file__).resolve().parent.parent/'R1-D1-V2/reproduce.py'
        extra = runpy.run_path(str(original))['EXTRA']
        fixture = runpy.run_path(str(root/'tests/product/test_source_workspaces.py'))
        files = {**fixture['FILES'],'demo/probe.py':extra,'demo/other.py':b'def same():\n    return 3\n'}
        folder = scratch/'extra'
        repo = enrich(folder,acquire(root,folder,'example/relations',loader=loader_for('a'*40,files)))
        names = {s['id']:s['name'] for s in repo['symbols']}
        for name, expected in {'direct':['helper'],'ambiguous':[],'qualified':[],
                               'Child.public':['Base.method'],'Child._hidden':['Base.method','Child.public']}.items():
            row = next(s for s in repo['symbols'] if s['name']==name and s['path']=='demo/probe.py')
            data = build(folder,repo,'probe',[row['id']],{},'r2',True)
            candidates = sorted(names[e['target']] for e in data['dependencies'])
            assert candidates==expected,(name,candidates,expected)
            probes[name] = dict(calls=row['calls'],expected=expected,related=candidates,passed=True)
    return dict(snapshots=repos,routes=all_rows,extra_probes=probes,
                metric_scope='software conformance on resolver-derived edges; no human evaluation')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline-only',action='store_true')
    parser.add_argument('--all-cases',action='store_true',help='Also rerun the six engineering cases collected before the scope revision.')
    args=parser.parse_args()
    with TemporaryDirectory(prefix='r2-',dir=args.output.resolve().parent) as directory:
        result=diagnostic(args.root.resolve(),Path(directory),args.cache.resolve(),args.baseline_only,args.all_cases)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
