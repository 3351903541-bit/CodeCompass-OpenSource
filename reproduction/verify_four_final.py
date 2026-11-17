import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

parser=argparse.ArgumentParser()
parser.add_argument('--product',required=True,type=Path)
parser.add_argument('--cache',required=True,type=Path)
parser.add_argument('--freeze-reference',required=True,type=Path)
parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args()
root=args.product.resolve()
args.output.parent.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(root/'src'),str(root),str(Path(__file__).resolve().parent)]
from reproduce_r2 import CASES,load_inputs,loader_for
from codecompass.graph import read_snapshot
from codecompass.learner.model import initial_state
from codecompass.product.repositories import acquire
from codecompass.product.goal_resolution import enrich
from codecompass.product.source_routes import build, solve
from codecompass.product.reading_order import optimize_first_order
from codecompass.product.workspaces import DEMO_SOURCE

references=json.loads(args.freeze_reference.read_bytes())
fixtures=list(load_inputs(root,args.cache.resolve()))
fixed=root/DEMO_SOURCE/'snapshot.json'
fixtures.append(('itsdangerous','pallets/itsdangerous',fixed,json.loads(fixed.read_bytes())))
picks={'python-slugify':CASES['python-slugify'][0],
       'schedule':CASES['schedule'][0],
       'boltons':CASES['boltons'][1],
       'itsdangerous':('解码编码后的文本','/serializer.py',('Serializer.dump','Serializer.load'))}
manifest_rows={}
all_data={}
with TemporaryDirectory(dir=args.output.parent,prefix='cases-') as temp:
    for key,name,manifest,snap in fixtures:
        saved=references[key]
        folder=Path(temp)/key
        contents=read_snapshot(manifest.parent,snap)
        repo=enrich(folder,acquire(root,folder,name,loader=loader_for(snap['commit'],contents)))
        goal,suffix,names=picks[key]
        ids=[]
        for symbol in names:
            candidates=[row['id'] for row in repo['symbols'] if row['name']==symbol
                        and row['path'].endswith(suffix) and not row['test_source']]
            assert len(candidates)==1,(name,symbol)
            ids.extend(candidates)
        preferences={'onboarding':{'experience':'new','familiar':[]}}
        ledger=initial_state('final-fixed-cases',is_simulated=True)
        data=build(folder,repo,goal,ids,preferences,'final-fixed-cases',True)
        attempt=solve(folder,data,ledger,budget=120)
        ranked=optimize_first_order(data,attempt)
        comparisons=dict(
            commit=snap['commit']==saved['commit'],targets=ids==saved['targets'],
            same_candidates={u['id'] for u in data['units']}=={u['id'] for u in saved['units']},
            same_selected=set(attempt['remaining'])==set(saved['selected']),
            same_order=ranked['remaining']==saved['methods']['R6']['order'],
            same_J=math.isclose(ranked['objective'],saved['stage1']['objective'],abs_tol=1e-9),
            audit_valid=ranked['audit']['valid'] and ranked['audit']['goal_complete'])
        assert all(comparisons.values()),(key,comparisons)
        print(key,len(data['units']),len(ranked['remaining']),ranked['objective'],flush=True)
        manifest_rows[key]=snap
        all_data[key]=dict(repository=name,commit=snap['commit'],goal=goal,source_manifest_sha256=sha256(manifest.read_bytes()).hexdigest(),
          target_symbols=ids,initial_profile=preferences,units=data['units'],
          verified_order_edges=data['verified_order_edges'],candidate_order_edges=data.get('candidate_order_edges',[]),
          stage1=attempt,final=ranked,title_order=[data['views'][u]['title'] for u in ranked['remaining']],
          comparisons_to_freeze=comparisons)
args.output.write_text(json.dumps(dict(cases=all_data),ensure_ascii=False,indent=2),encoding='utf-8')
(args.output.parent/'输入快照清单.json').write_text(json.dumps(manifest_rows,ensure_ascii=False,indent=2),encoding='utf-8')
