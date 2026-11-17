import json,subprocess,sys
import pytest
from codecompass.product.learning_view import EXAMPLES,profile_metrics
from codecompass.product.source_assistant import extract_reply,ReplyFailure
from tests.product.test_source_workspaces import ready


def test_every_lesson_example_has_real_output():
    for _,(_,_,code,expected,_) in EXAMPLES.items():
        p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        assert p.returncode==0 and p.stdout.strip()==expected


def test_source_grounded_lessons_and_reproducible_metrics(service):
    uid,job=ready(service);p=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    m=p['insights']['route'];s=p['state']
    assert m['goal_coverage']==100 and m['selected']==len(s['result']['remaining'])
    assert m['candidates']==len(s['data']['units']) and m['progress']==0
    for identity,l in p['insights']['lessons'].items():
        span=s['data']['views'][identity]['span']
        assert l['goal_link']=='chunk' and l['reason'] and l['completion']
        assert all(span['start_line']<=point['line']<=span['end_line'] for point in l['source_steps'])
    assert p['insights']['profile']['score'] is None
    with pytest.raises(ValueError):service.workspaces.feedback(uid,p['id'],0,'skip','skip_issues')


def test_issue_phase_after_reading_skip_and_report_restart(service):
    uid,job=ready(service);p=service.workspaces.create(uid,job['id'],'decode',budget=None)
    while p['state']['result']['remaining']:
        p=service.workspaces.feedback(uid,p['id'],p['revision'],'read-'+str(p['revision']),'read',p['state']['result']['remaining'][0])
    assert p['insights']['learning_phase']=='issues' and p['insights']['route']['progress']==100
    before=p['revision'];done=service.workspaces.feedback(uid,p['id'],before,'skip-end','skip_issues')
    assert done['insights']['learning_phase']=='review' and done['state']['issue_status']=='skipped'
    assert service.workspaces.feedback(uid,p['id'],before,'skip-end','skip_issues')['revision']==done['revision']
    from codecompass.product.service import Service
    restarted=Service(service.root,service.store.path,'test_fixture')
    assert restarted.workspaces.route(uid,p['id'])['insights']['learning_phase']=='review'
    other=service.profile()['user_id']
    with pytest.raises(ValueError):service.workspaces.feedback(other,p['id'],done['revision'],'other','finish_issues')


def test_partial_reply_email_and_credential_guard():
    raw=lambda text,status='completed':dict(status=status,output=[dict(type='message',content=[dict(type='output_text',text=text)])])
    reply,partial=extract_reply(raw('先读取输入，再过滤元素。','incomplete'))
    assert partial and reply
    reply,partial=extract_reply(raw('示例标签 test@example.org 用作普通字符串。'))
    assert not partial and 'test@example.org' not in reply and '示例标签' in reply
    with pytest.raises(ReplyFailure,match='CREDENTIAL_OUTPUT'):extract_reply(raw('sk-TEST_SECRET_STRING_123456789'))
    with pytest.raises(ReplyFailure,match='OUTPUT_LIMIT'):extract_reply(raw('','incomplete'))


def test_issue_index_has_components_without_invented_profile(service,monkeypatch):
    uid,job=ready(service);p=service.workspaces.create(uid,job['id'],'chunk')
    row=dict(number=12,state='open',title='chunk list handling',body='demo/transform.py function argument list',html_url='https://github.com/example/demo/issues/12')
    monkeypatch.setattr('codecompass.product.source_issues.fetch',lambda *args:json.dumps([row]).encode())
    item=service.workspaces.issues.get(uid,p['id'],True)['items'][0]
    assert 0<=item['match_percent']<=100 and item['match_components']['ability'] is None
    weights=item['match_weights'];components=item['match_components']
    assert abs(item['match_percent']-sum(components[k]*v for k,v in weights.items()))<=1
    assert abs(sum(weights.values())-1)<.001


def test_no_legacy_examples_in_product_shell(service):
    root=service.root/'app/product'
    assert '示例任务' not in (root/'index.html').read_text(encoding='utf-8')
    assert 'showTasks' not in (root/'app.js').read_text(encoding='utf-8')
    assert '辅助学习示例' not in (root/'workspaces.js').read_text(encoding='utf-8')
