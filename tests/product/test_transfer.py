import pytest
from codecompass.product.service import Service
from tests.product.test_learning import perform
from scripts.product_demo import answer_flow

def test_reference_does_not_copy_posterior(service):
    user=service.profile()['user_id'];s=perform(service,service.create(user,'P02_window_fix'),'skip_baseline')
    s=perform(service,s,'read',{'unit_id':'u_iterable'});s=perform(service,s,'check',{'choice':1})
    before=service.store.evidence.read(user,simulated=True)
    target=service.create(user,'P04_chunked_transfer');ref=target['state']['transfer_reference']
    assert ref['source_evidence_ids']==[before['records'][0]['evidence_id']]
    assert not ref['posterior_copied'] and not ref['mastery_granted']
    assert ref['source_project']!=ref['target_project']
    assert service.store.evidence.read(user,simulated=True)==before
    assert not any(e['project']==ref['target_project'] for e in before['records'])
    assert target['transfer_summary']['new_result'] is None
    assert target['transfer_summary']['knowledge_gaps']
    assert service.transfer(target['session_id'])['reference']==ref
    with service.store.connect() as db:assert db.execute('SELECT count(*) FROM product_transfers').fetchone()[0]==1
    with pytest.raises(ValueError):service.transfer(target['session_id'],'wrong-project')
    with pytest.raises(ValueError):service.transfer(target['session_id'],concept_id='invented')
    assert service.get(s['session_id'])['status']=='paused'

@pytest.mark.parametrize('choice',[None,0])
def test_direct_p04_unknown_or_wrong_retest_can_continue(service,choice):
    user=service.profile()['user_id'];s=service.create(user,'P04_chunked_transfer')
    assert s['state']['transfer_reference'] is None
    with service.store.connect() as db:assert db.execute('SELECT count(*) FROM product_transfers').fetchone()[0]==0
    s=perform(service,s,'skip_baseline');s=perform(service,s,'read',{'unit_id':'B07_more_chunked'})
    s=perform(service,s,'check',{'choice':choice})
    assert s['state']['feedback']['correct'] is (None if choice is None else False)
    assert s['state']['feedback']['explanation']
    s=perform(service,s,'check',{'continue':True});assert s['phase']=='practice'
    s=perform(service,s,'answers',{'answers':[1,1],'reflection':'分组不共享元素'})
    assert s['phase']=='review' and s['transfer_summary']['new_result']['correct'] is (None if choice is None else False)
    assert s['state']['draft']['reflection']=='分组不共享元素'

def test_p03_four_tasks_and_restored_draft(service):
    user=service.profile()['user_id'];first=answer_flow(service,user,'P01_unique_read')
    debug=answer_flow(service,user,'P03_window_debug')
    assert debug['state']['answer_results'] and debug['task']['name']=='排查窗口大小错误'
    s=service.create(user,'P04_chunked_transfer')
    assert s['phase']=='learning' and s['state']['baseline_done']
    s=perform(service,s,'read',{'unit_id':'B07_more_chunked'})
    s=perform(service,s,'check',{'choice':None});s=perform(service,s,'check',{'continue':True})
    s=service.draft(s['session_id'],'save',s['revision'],'practice',{'answers':[1,None],'reflection':'P04独立草稿'})
    fourth=service.create(user,'P02_window_fix');assert fourth['state']['draft'] is None
    restored=Service(service.root,service.store.path,'test_fixture')
    old=restored.get(s['session_id']);assert old['status']=='paused'
    assert old['state']['draft']['reflection']=='P04独立草稿'
    assert len(restored.profile(user)['sessions'])==4
    assert first['state']['draft']['reflection']!=old['state']['draft']['reflection']
