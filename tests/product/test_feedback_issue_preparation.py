import json
import pytest
from tests.product.test_source_workspaces import ready
from codecompass.product.issue_public import parse_page
from codecompass.product.repositories import FEATURES


def finish_reading(service,uid,route):
    while route['state']['result']['remaining']:
        route=service.workspaces.feedback(uid,route['id'],route['revision'],'read-'+str(route['revision']),'read',route['state']['result']['remaining'][0])
    return route


def test_explicit_skip_overrides_old_quiz_and_does_not_claim_reading(service,monkeypatch):
    # Exercise the skip at a foundation step regardless of first-plan presentation order.
    monkeypatch.setattr('codecompass.product.workspaces.optimize_first_order',lambda data,result:result)
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    first=route['state']['result']['remaining'][0];view=route['state']['data']['views'][first]
    assert view['kind']=='foundation'
    with service.store.connect() as db:
        prefs=service.workspaces.preferences(db,uid)
        prefs['assessment']={'topics':{c:dict(correct=0,answered=1) for c in view['concepts']}}
        db.execute('UPDATE product_users SET preferences_json=? WHERE user_id=?',(json.dumps(prefs),uid))
    after=service.workspaces.feedback(uid,route['id'],route['revision'],'skip-base','familiar',first)
    assert first not in after['state']['result']['remaining']
    assert after['state']['adjustment']['current_skipped']
    assert first in after['state']['skipped_foundations'] and not after['state']['completed']
    assert not service.profile(uid)['metrics']['learning']['readings']
    assert all(ex['concept'] not in after['state']['adjustment']['topics'] for l in after['insights']['lessons'].values() for ex in l['examples'])
    replay=service.workspaces.feedback(uid,route['id'],route['revision'],'skip-base','familiar',first)
    assert replay['revision']==after['revision']


def test_extra_foundation_expands_previously_read_examples(service):
    uid,job=ready(service);route=service.workspaces.create(uid,job['id'],'chunk',budget=None)
    first=route['state']['result']['remaining'][0]
    with service.store.connect() as db:
        prefs=service.workspaces.preferences(db,uid)
        prefs['learning_growth']=dict(readings={},checks={},explained=list(FEATURES))
        db.execute('UPDATE product_users SET preferences_json=? WHERE user_id=?',(json.dumps(prefs),uid))
    after=service.workspaces.feedback(uid,route['id'],route['revision'],'more-base','hard',first)
    assert after['state']['adjustment']['action']=='hard'
    current=after['state']['result']['remaining'][0]
    assert any(not ex['review'] for ex in after['insights']['lessons'][current]['examples'])


def test_closed_topic_issue_is_valid_fallback_and_api_prs_are_excluded(service,monkeypatch):
    uid,job=ready(service);route=finish_reading(service,uid,service.workspaces.create(uid,job['id'],'学习文本替换和字符处理',[next(s['id'] for s in job['symbols'] if s['name']=='decode')],None))
    rows=[dict(number=9,state='closed',title='Unicode character replacement error',body='',html_url='https://github.com/example/demo/issues/9'),dict(number=10,state='open',title='Unicode replacement',html_url='https://github.com/example/demo/issues/10',pull_request={})]
    monkeypatch.setattr('codecompass.product.source_issues.fetch',lambda *args:json.dumps(rows).encode())
    result=service.workspaces.issues.get(uid,route['id'],True)
    assert len(result['items'])==1 and result['items'][0]['recommendation_kind']=='retrospective'
    assert result['items'][0]['state']=='closed' and result['items'][0]['match_percent']>0
    with pytest.raises(ValueError):service.workspaces.feedback(uid,route['id'],route['revision'],'empty-finish','finish_issues')
    prep=dict(number=9,checks=[True,True,True],note='定位字符转换入口，并使用特殊字符输入复盘历史问题。')
    for bad in ({**prep,'checks':[False,True,True]},{**prep,'note':'太短'},{**prep,'number':999}):
        with pytest.raises(ValueError):service.workspaces.feedback(uid,route['id'],route['revision'],'bad-finish','finish_issues',preparation=bad)
    done=service.workspaces.feedback(uid,route['id'],route['revision'],'real-prep','finish_issues',preparation=prep)
    assert done['state']['issue_preparation']['number']==9 and done['state']['issue_preparation']['note']==prep['note']
    assert done['state']['issue_status']=='completed' and done['insights']['learning_phase']=='review'
    assert service.workspaces.feedback(uid,route['id'],route['revision'],'real-prep','finish_issues',preparation=prep)['revision']==done['revision']
    skipped=service.workspaces.feedback(uid,done['id'],done['revision'],'explicit-skip','skip_issues')
    assert skipped['state']['issue_status']=='skipped'


def test_public_page_parser_checks_type_owner_url_and_state():
    issue=dict(number=12,title='Unicode characters',state='REPO_ISSUE_STATE_CLOSED',permalink='https://github.com/a/b/issues/12',repoNameWithOwner='a/b')
    rows=[dict(itemType='REPO_ISSUES_DASHBOARD_ITEM_TYPE_ISSUE',issue=issue),dict(itemType='PULL_REQUEST',issue=issue),dict(itemType='REPO_ISSUES_DASHBOARD_ITEM_TYPE_ISSUE',issue={**issue,'permalink':'https://evil.test'})]
    raw=('<script type="application/json">'+json.dumps({'payload':{'issuesIndexContentRoute':{'results':rows}}})+'</script>').encode()
    assert len(parse_page(raw,'a/b'))==1 and not parse_page(raw,'other/repo')
    with pytest.raises(ValueError):parse_page(b'<p>Login</p>','a/b')
