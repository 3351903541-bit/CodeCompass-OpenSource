import copy,json,shutil
from pathlib import Path
import pytest
from codecompass.product.service import Service

ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def service(tmp_path):
    root = tmp_path / "runtime"
    for name in ("benchmarks", "configs", "content", "schemas"):
        shutil.copytree(ROOT / name, root / name)
    target = root / "benchmarks/B/D07/issues_snapshot.json"
    target.write_bytes((ROOT / "tests/product/fixtures/synthetic_boltons_issues.json").read_bytes())
    return Service(root, tmp_path / "issues.sqlite3", "test_fixture")

from codecompass.product.issues import Issues

def snapshot(service,state='open'):
    data=json.loads((service.root/'benchmarks/B/D07/issues_snapshot.json').read_text(encoding='utf-8'))
    data['issues']=data['issues'][:1]
    data['issues'][0].update(title='iterutils related fixed historical case',body='iterutils',state=state)
    return data

def test_fixture_historical_candidates_and_failed_refresh(service,monkeypatch):
    s=service.create(service.profile()['user_id'],'P02_window_fix')
    old=service.issues.get(s['session_id']);assert 0<len(old['items'])<=3
    assert old['source_mode']=='historical_snapshot' and old['captured_at'].startswith('2026-10-16')
    calls=[]
    def fail(repo):calls.append(repo);raise TimeoutError('fixture')
    monkeypatch.setattr('codecompass.product.issues.fetch_snapshot',fail)
    failed=service.issues.get(s['session_id'],True)
    assert '刷新失败' in failed['notice'] and failed['captured_at']==old['captured_at']
    service.issues.get(s['session_id'],True);assert calls==['mahmoud/boltons']
    assert not failed['current_state_claimed']

def test_closed_learning_case_and_zero_matches(service,monkeypatch):
    s=service.create(service.profile()['user_id'],'P03_window_debug')
    data=snapshot(service,'closed')
    monkeypatch.setattr('codecompass.product.issues.fetch_snapshot',lambda repo:data)
    result=service.issues.get(s['session_id'],True)
    assert len(result['items'])==1 and result['items'][0]['state_at_capture']=='closed'
    assert '仅供学习' in result['items'][0]['label'] and not result['items'][0]['community_submission']
    assert result['items'][0]['preparation_steps']==['回看相关函数','用一个小例子复现或理解问题','阅读贡献说明后再决定参与']
    with service.store.connect() as db:db.execute('DELETE FROM product_issue_snapshots')
    data=copy.deepcopy(data);data['issues'][0].update(title='No matching module',body='unrelated')
    monkeypatch.setattr('codecompass.product.issues.fetch_snapshot',lambda repo:data)
    result=service.issues.get(s['session_id'],True)
    assert not result['items'] and result['empty_message']=='暂未找到合适的贡献任务'
    assert result['next_learning']

def test_new_repo_without_snapshot_and_wrong_links_fall_back(service,monkeypatch):
    s=service.create(service.profile()['user_id'],'P04_chunked_transfer')
    result=service.issues.get(s['session_id']);assert result['source_mode']=='unavailable' and not result['items']
    invalid=snapshot(service);invalid['issues'][0]['html_url']='https://untrusted.invalid'
    monkeypatch.setattr('codecompass.product.issues.fetch_snapshot',lambda repo:invalid)
    result=service.issues.get(s['session_id'],True)
    assert result['source_mode']=='unavailable' and '刷新失败' in result['notice']
