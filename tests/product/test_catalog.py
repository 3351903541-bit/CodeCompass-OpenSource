import pytest

def test_fixed_sources_and_materials(service):
    for task in service.catalog.tasks:
        d=service.catalog.source(task['task_id'])
        assert task['source_version']==d['snapshot']['commit']
        assert task['unit_ids']==[u['id'] for u in d['units']]
    for uid in service.catalog.task('P02_window_fix')['unit_ids']:
        m=service.catalog.material('P02_window_fix',uid)
        assert m['materials'] and 100<=len(m['explanation'])<=250
    with pytest.raises(ValueError):service.catalog.task('../secret')
    with pytest.raises(ValueError):service.catalog.material('P02_window_fix','B07_more_chunked')
    u=service.profile()['user_id']
    assert service.create(u,'P03_window_debug')['task']['available']
