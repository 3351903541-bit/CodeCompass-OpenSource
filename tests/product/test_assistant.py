from pathlib import Path
import json,pytest
from codecompass.product.service import Service,Conflict
from scripts.B.comparison.b1 import SpendMeter
ROOT=Path(__file__).resolve().parents[2]

def configured(tmp_path,transport):
    cfg=json.loads((ROOT/'configs/B/D06_v2_deepseek.json').read_text())['b1']
    return Service(ROOT,tmp_path/'assistant.sqlite3','test_fixture',assistant_config=cfg,transport=transport,meter=SpendMeter(1))
def start(s):
    v=s.create(s.profile()['user_id'],'P02_window_fix')
    return s.action(v['session_id'],'skip',v['revision'],'skip_baseline')
def test_offline_recovery_and_idempotency(service):
    v=start(service);uid=v['state']['remaining'][0]
    a=service.assistant.ask(v['session_id'],uid,'给我一个类似例子','same','offline')
    assert a['message']['mode']=='offline' and '号码' in a['message']['reply']
    assert service.assistant.ask(v['session_id'],uid,'给我一个类似例子','same','offline')['message']==a['message']
    assert len(service.assistant.history(v['session_id'])['messages'])==1
    with pytest.raises(Conflict):service.assistant.ask(v['session_id'],uid,'changed','same','offline')
def test_transport_context_and_single_charge(tmp_path):
    seen=[]
    def transport(payload,cfg):
        seen.append(payload);assert cfg['timeout_seconds']==45
        assert '正确答案' not in payload['input'] and 'baseline_choices' not in payload['input'] and 'answer' not in payload['input']
        return dict(status='completed',model=cfg['model'],usage={'input_tokens':10,'output_tokens':10},output=[{'type':'message','content':[{'type':'output_text','text':'这是明确的测试讲解。'}]}])
    s=configured(tmp_path,transport);v=start(s);uid=v['state']['remaining'][0]
    a=s.assistant.ask(v['session_id'],uid,'带我读这段代码','once')
    s.assistant.ask(v['session_id'],uid,'带我读这段代码','once')
    assert len(seen)==1 and s.assistant.meter.reserved==.25 and a['message']['mode']=='live'
    assert s.get(v['session_id'])['phase']=='learning'
def test_timeout_keeps_progress_no_auto_retry(tmp_path):
    calls=[]
    def timeout(*a):calls.append(1);raise TimeoutError()
    s=configured(tmp_path,timeout);v=start(s);uid=v['state']['remaining'][0]
    a=s.assistant.ask(v['session_id'],uid,'带我读这段代码','timeout')
    assert a['message']['status']=='timeout'
    s.assistant.ask(v['session_id'],uid,'带我读这段代码','timeout')
    assert len(calls)==1 and s.get(v['session_id'])['phase']=='learning'
