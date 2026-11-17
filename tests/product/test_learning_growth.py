import json
import pytest
from tests.product.test_source_workspaces import ready
from codecompass.product.learning_growth import CHECKS,topics,record_read,verified
from codecompass.product.learning_view import profile_metrics


def test_reading_updates_profile_without_inventing_test_results(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'decode',budget=None)
    unit=route['state']['result']['remaining'][0]
    before=service.profile(uid)['metrics'];assert before['learning']['readings']==0
    route=service.workspaces.feedback(uid,route['id'],route['revision'],'read-growth','read',unit)
    after=service.profile(uid)['metrics']
    assert after['learning']['readings']==1 and after['learning']['repositories']==1
    assert after['learning']['stage']=='源码研读' and after['score'] is None
    assert any(r['reading_count']==1 for r in after['topics'])
    assert all(ex['review'] for ex in route['insights']['lessons'][unit]['examples'])
    assert not any(r['check_correct'] for r in after['topics'])


def test_legacy_completed_steps_are_recovered_read_only(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'decode',budget=None)
    unit=route['state']['result']['remaining'][0]
    service.workspaces.feedback(uid,route['id'],route['revision'],'read-old','read',unit)
    with service.store.connect() as db:
        row=db.execute('SELECT preferences_json FROM product_users WHERE user_id=?',(uid,)).fetchone()
        prefs=json.loads(row[0]);prefs.pop('learning_growth',None)
        db.execute('UPDATE product_users SET preferences_json=? WHERE user_id=?',(json.dumps(prefs),uid))
    assert service.profile(uid)['metrics']['learning']['readings']==1
    with service.store.connect() as db:assert json.loads(db.execute('SELECT preferences_json FROM product_users WHERE user_id=?',(uid,)).fetchone()[0])==prefs


def test_check_is_source_scoped_idempotent_and_changes_future_foundations(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'decode',budget=None)
    unit=route['state']['result']['remaining'][0];view=route['state']['data']['views'][unit]
    concept=topics(view)[0]
    question=next(q for q in route['insights']['lessons'][unit]['practice'] if q['concept']==concept)
    assert 'answer' not in question and question['result'] is None
    other=service.profile()['user_id']
    with pytest.raises(ValueError):service.workspaces.learning_check(other,route['id'],unit,concept,CHECKS[concept][2])
    route=service.workspaces.learning_check(uid,route['id'],unit,concept,CHECKS[concept][2])
    route=service.workspaces.learning_check(uid,route['id'],unit,concept,CHECKS[concept][2])
    # A correct generic check alone must not claim source-reading experience.
    assert service.profile(uid)['metrics']['learning']['verified_topics']==0
    route=service.workspaces.feedback(uid,route['id'],route['revision'],'read-check','read',unit)
    prefs=service.profile(uid)['preferences'];assert concept in verified(prefs)
    assert service.profile(uid)['metrics']['learning']['verified_topics']==1
    assert concept not in route['state']['data']['support']
    with pytest.raises(ValueError):service.workspaces.learning_check(uid,route['id'],unit,concept,(CHECKS[concept][2]+1)%4)


def test_failed_check_does_not_promote_and_duplicate_spans_do_not_inflate():
    from codecompass.product.learning_growth import record_read
    view=dict(code='def f(x):\n    return x[0]',span=dict(path='a.py',content_hash='abc'))
    prefs={};record_read(prefs,view,'example/one');record_read(prefs,view,'example/one')
    assert profile_metrics(prefs)['learning']['readings']==1
    record_read(prefs,view,'example/two')
    assert profile_metrics(prefs)['learning']['stage']=='跨仓库实践'
    prefs['learning_growth']['checks']['python.containers']=dict(correct=False)
    assert 'python.containers' not in verified(prefs)
    assert next(r for r in profile_metrics(prefs)['topics'] if r['concept']=='python.containers')['growth_status']=='建议复习'


def test_ui_has_linked_line_numbers_and_no_fixed_list_topic(service):
    root=service.root/'app/product';ws=(root/'workspaces.js').read_text(encoding='utf-8');js=(root/'journey.js').read_text(encoding='utf-8')
    assert '列表专题' not in ws and '我想学习列表的用法' not in ws
    assert 'numberedSource(v)' in js and 'row.dataset.line=String(n)' in js and 'row.scrollIntoView' in js
    assert "el('summary','仓库原始文档注释')" in js


def test_growth_check_answers_match_controlled_programs():
    import subprocess,sys
    outputs={'functions':'7','containers':'[8, 5]','iteration':'[5, 7]','generators':'4\n[8]','classes':'5','exceptions':'A\nB','decorators':'12','async':'10'}
    for topic,(code,choices,answer,_) in CHECKS.items():
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        assert result.returncode==0 and result.stdout.strip()==outputs[topic.split('.')[1]]
