import json
import pytest
from codecompass.product.source_map import overview
from codecompass.product.service import Service
from tests.product.test_source_workspaces import ready,FILES,loader


def test_map_covers_all_files_and_exact_selected_spans(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    m=overview(service.workspaces,uid,route['id'])
    assert {n['path'] for n in m['nodes'] if n['kind']=='file'}==set(FILES)
    assert len(m['steps'])==len(route['state']['result']['remaining'])
    by_id={n['id']:n for n in m['nodes']}
    for step in m['steps']:
        node=by_id[step['node_id']];view=route['state']['data']['views'][step['unit_id']]
        assert node['selected'] and node['span']==view['span']
        assert step['number'] in node['steps'] and step['reason']
    assert all(e['kind']=='study_order' for e in m['study_edges'])
    assert all(e['kind']!='study_order' for e in m['edges'])
    assert all(e.get('resolution')=='unique_name_candidate' for e in m['edges'] if e['kind']=='call_candidate')
    assert all(e['source']=='repository' or e['source'] in by_id for e in m['edges'])
    assert all(e['target'] in by_id for e in m['edges'])


def test_verified_call_projection_and_order_reason(service):
    uid,job=ready(service)
    ids={s['name']:s['id'] for s in job['symbols']}
    route=service.workspaces.create(uid,job['id'],'chunk',[ids['chunk'],ids['clean']])
    state=route['state']; overview_data=overview(service.workspaces,uid,route['id'])
    verified=[e for e in overview_data['edges'] if e['kind']=='verified_call']
    pairs={(e['source'],e['target']) for e in verified}
    assert len(pairs)==len(verified)
    assert not pairs & {(e['source'],e['target']) for e in overview_data['edges'] if e['kind']=='call_candidate'}
    projected={(s['caller'],s['callee'],s['path'],s['line']) for e in verified for s in e['sites'] if s['used_for_order']}
    planned={(e['caller'],e['callee'],e['path'],e['line']) for e in state['data']['verified_order_edges']}
    assert projected==planned=={(ids['chunk'],ids['clean'],'demo/transform.py',7)}
    steps={s['node_id']:s for s in overview_data['steps']}
    assert steps[ids['clean']]['number']<steps[ids['chunk']]['number']
    assert steps[ids['clean']]['order_reason']['before']==['chunk'] and steps[ids['clean']]['reason']
    route=service.workspaces.feedback(uid,route['id'],route['revision'],'read-map','read',state['result']['remaining'][0])
    refreshed=overview(service.workspaces,uid,route['id'])
    assert all(s['order_reason'] is None for s in refreshed['steps'])
    assert not any(s['used_for_order'] for e in refreshed['edges'] if e['kind']=='verified_call' for s in e['sites'])


def test_map_user_isolation_and_start_does_not_mark_read(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    other=service.profile()['user_id']
    with pytest.raises(ValueError):overview(service.workspaces,other,route['id'])
    with pytest.raises(ValueError):service.workspaces.feedback(other,route['id'],0,'start','begin_learning')
    started=service.workspaces.feedback(uid,route['id'],0,'start','begin_learning')
    assert started['state']['learning_started'] and not started['state']['completed']
    assert started['state']['result']==route['state']['result'] and started['revision']==1
    assert not service.profile(uid)['metrics']['learning']['readings']
    assert not service.store.evidence.read(uid,simulated=True)['records']
    assert service.workspaces.feedback(uid,route['id'],0,'start','begin_learning')['revision']==1
    assert Service(service.root,service.store.path,'test_fixture').workspaces.route(uid,route['id'])['state']['learning_started']


def test_map_changes_with_goal_and_tracks_completed_order(service):
    uid,job=ready(service);a=service.workspaces.create(uid,job['id'],'chunk',budget=None);b=service.workspaces.create(uid,job['id'],'decode',budget=None)
    one=overview(service.workspaces,uid,a['id']);two=overview(service.workspaces,uid,b['id'])
    assert {n['id'] for n in one['nodes'] if n.get('target')}!={n['id'] for n in two['nodes'] if n.get('target')}
    first=a['state']['result']['remaining'][0]
    a=service.workspaces.feedback(uid,a['id'],0,'read','read',first)
    updated=overview(service.workspaces,uid,a['id'])
    assert updated['steps'][0]['unit_id']==first and updated['steps'][0]['completed']
    assert {n['path'] for n in updated['nodes'] if n['kind']=='file'}==set(FILES)


def test_import_declarations_are_separate_from_call_candidates(service):
    import time
    from tests.product.test_source_workspaces import archive
    def source(url,limit):
        if url.endswith('HEAD'):return loader(url,limit)
        return archive({'pkg/__init__.py':b'from .codec import decode\n', 'pkg/codec.py':b'def decode(text):\n    return text\n', 'main.py':b'from pkg.codec import decode\ndef run(text):\n    return decode(text)\n'})
    uid=service.profile()['user_id'];service.workspaces.onboard(uid,dict(experience='new',months='0',familiar=[]),0);service.workspaces.loader=source
    job=service.workspaces.start(uid,'https://github.com/example/imports','map-imports')
    for _ in range(100):
        job=service.workspaces.repository(uid,job['id'])
        if job['status']!='importing':break
        time.sleep(.02)
    route=service.workspaces.create(uid,job['id'],'run',budget=None);m=overview(service.workspaces,uid,route['id'])
    assert any(e['source']=='file:main.py' and e['target']=='file:pkg/codec.py' and e['kind']=='imports' for e in m['edges'])
    assert any(e['source']=='file:pkg/__init__.py' and e['target']=='file:pkg/codec.py' and e['kind']=='imports' for e in m['edges'])
    call,=[e for e in m['edges'] if e['kind']=='verified_call']
    assert call['source'].startswith('main.py::run') and call['target'].startswith('pkg/codec.py::decode')
    assert call['line']==3 and call['basis']=='snapshot_explicit_import'
    assert not any(e['kind']=='call_candidate' and (e['source'],e['target'])==(call['source'],call['target']) for e in m['edges'])
