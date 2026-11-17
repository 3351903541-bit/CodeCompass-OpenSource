import hashlib
import json
from pathlib import Path
import time

from codecompass.graph import read_snapshot
from codecompass.product.call_resolution import cross_file_relations
from codecompass.product.goal_resolution import enrich
from .test_source_workspaces import archive


def test_bundled_itsdangerous_uses_production_import_and_route(service):
    source=service.root/'benchmarks/sources/r5-offline/itsdangerous/benchmarks/sources/imported'
    snap=json.loads((source/'snapshot.json').read_text(encoding='utf-8'))
    files=read_snapshot(source,snap)
    assert len(files)==15 and snap['commit']=='672971d66a2ef9f85151e53283113f33d642dabd'
    assert {line.split('  ',1)[1]:line.split('  ',1)[0] for line in
            (source/'SHA256SUMS').read_text().splitlines()}=={p:hashlib.sha256(b).hexdigest() for p,b in files.items()}
    def loader(url,limit):
        if url.endswith('/HEAD'):
            return json.dumps({'sha':snap['commit']}).encode()
        assert url.endswith('/zipball/'+snap['commit'])
        return archive(files)
    ws=service.workspaces
    uid=service.profile()['user_id']
    ws.onboard(uid,dict(experience='new',months='0',familiar=[]),0)
    ws.loader=loader
    job=ws.start(uid,snap['url'],'offline')
    for _ in range(200):
        if job['status']!='importing':break
        time.sleep(.02);job=ws.repository(uid,job['id'])
    assert job['status']=='ready'
    folder=ws.root/job['id']
    repo=enrich(folder,ws._repo(job['id']))
    sites=list(cross_file_relations(files,repo['symbols'],{s['id'] for s in repo['symbols']}))
    calls=[s for s in sites if 'kind' not in s]
    assert calls and any(s['expression']=='bytes_to_int' for s in calls)
    route=ws.create(uid,job['id'],'解码编码后的文本')
    assert route['state']['result']['audit']['goal_complete']
