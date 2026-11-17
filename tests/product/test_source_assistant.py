import json
import sqlite3
import zipfile
import threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import pytest
from codecompass.product.service import Service
from scripts.B.comparison.b1 import SpendMeter
from scripts.export_product_safe import included,assert_safe,export
from tests.product.test_source_workspaces import ready
from scripts.serve_product import make_server


def connected(service,transport):
    service.assistant.transport=transport;service.assistant.injected=True;service.assistant.meter=SpendMeter(1)
    uid,job=ready(service)
    route=service.workspaces.create(uid,job['id'],'理解 chunk 分组')
    return uid,route,route['state']['result']['remaining'][0]


def raw(text):
    return dict(status='completed',model='explicit-test-model',output=[dict(type='message',content=[dict(type='output_text',text=text)])])


def test_grounded_context_secret_absent_and_single_charge(service,monkeypatch):
    key='sk-TEST_SECRET_CREDENTIAL_1234567890';monkeypatch.setenv('DEEPSEEK_API_KEY',key)
    calls=[]
    def transport(payload,cfg):
        assert key not in json.dumps(payload) and 'Authorization' not in json.dumps(payload)
        assert payload['store'] is False and cfg['timeout_seconds']==45
        context=json.loads(payload['input'].split('上下文JSON：',1)[1].split('\n问题：',1)[0])
        assert context['repository']=='example/demo' and context['goal']=='理解 chunk 分组'
        assert context['sources'][0]['path'].startswith('demo/') and len(context['sources'])<=3
        assert context['learner']['experience']=='new' and 'familiar' in context['learner']
        calls.append(payload)
        return raw('根据 demo/transform.py 的源码，可先追踪输入和循环。')
    uid,p,unit=connected(service,transport)
    result=service.source_assistant.ask(uid,p['id'],unit,'解释当前源码','same')
    assert result['mode']=='live' and result['status']=='completed' and result['sources']
    assert service.source_assistant.ask(uid,p['id'],unit,'解释当前源码','same')==result
    assert len(calls)==1 and service.assistant.meter.reserved==.25
    assert not service.store.evidence.read(uid,simulated=True)['records']
    assert service.workspaces.route(uid,p['id'])['revision']==0
    history=service.source_assistant.history(uid,p['id'])
    assert key not in json.dumps(history) and len(history['messages'])==1
    with service.store.connect() as db:
        rows=[tuple(r) for r in db.execute('SELECT * FROM product_source_messages')]
    assert key not in repr(rows)
    with pytest.raises(ValueError): service.source_assistant.ask(uid,p['id'],unit,'改变问题','same')


def test_model_echo_secret_quarantined_and_exception_never_saved(service,monkeypatch):
    key='sk-TEST_SECRET_CREDENTIAL_1234567890';monkeypatch.setenv('DEEPSEEK_API_KEY',key)
    uid,p,unit=connected(service,lambda *args:raw('密钥是 '+key))
    result=service.source_assistant.ask(uid,p['id'],unit,'解释源码','echo')
    assert result['status']=='error' and key not in json.dumps(result)
    def fail(*args):raise RuntimeError('Authorization: Bearer '+key)
    service.assistant.transport=fail
    result=service.source_assistant.ask(uid,p['id'],unit,'解释源码','exception')
    assert key not in json.dumps(result)
    with pytest.raises(ValueError): service.source_assistant.ask(uid,p['id'],unit,'我的密钥 '+key,'question-secret')
    assert key not in json.dumps(service.source_assistant.history(uid,p['id']))


def test_isolation_tamper_timeout_budget_and_restart(service):
    calls=[]
    def timeout(*args):calls.append(1);raise TimeoutError()
    uid,p,unit=connected(service,timeout)
    uid2=service.profile()['user_id']
    with pytest.raises(ValueError):service.source_assistant.history(uid2,p['id'])
    with pytest.raises(ValueError):service.source_assistant.ask(uid,p['id'],'outside','why','bad-unit')
    a=service.source_assistant.ask(uid,p['id'],unit,'解释源码','timeout')
    assert a['status']=='connection_error'
    service.source_assistant.ask(uid,p['id'],unit,'解释源码','timeout');assert len(calls)==1
    service.assistant.meter=SpendMeter(.01)
    assert service.source_assistant.ask(uid,p['id'],unit,'解释源码','budget')['status']=='budget_exhausted'
    assert len(calls)==1
    restored=Service(service.root,service.store.path,'test_fixture')
    assert len(restored.source_assistant.history(uid,p['id'])['messages'])==2
    source=service.workspaces.root/p['repository_id']/'benchmarks/sources/imported/demo/transform.py'
    source.write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError,match='Snapshot byte mismatch'):service.source_assistant.ask(uid,p['id'],unit,'解释源码','tamper')
    assert len(calls)==1


def test_offline_explicit_and_pending_restart(service):
    uid,p,unit=connected(service,lambda *args:pytest.fail('offline must not call model'))
    result=service.source_assistant.ask(uid,p['id'],unit,'解释源码','offline','offline')
    assert result['mode']=='offline' and result['explanation_kind']=='flow'
    assert '第 ' in result['reply'] and result['sources']
    with service.store.connect() as db:
        db.execute('INSERT INTO product_source_messages VALUES(?,?,?,?,?,?,?)',(p['id'],'interrupted','x',unit,'why',None,'2026-10-25T00:00:00Z'))
    restored=Service(service.root,service.store.path,'test_fixture')
    assert restored.source_assistant.history(uid,p['id'])['messages'][-1]['status']=='interrupted'


def test_submission_allowlist_and_secret_block(tmp_path,monkeypatch):
    for name in ['tmp/deepseek-key.dpapi','.env','local_data/product/product.sqlite3','.git/config','report_materials/chat.json']:
        assert not included(name)
    assert included('src/codecompass/product/source_assistant.py')
    with pytest.raises(ValueError):assert_safe('configs/key.json',b'{"key":"sk-THIS_IS_A_TEST_SECRET_123456"}')
    (tmp_path/'src').mkdir();(tmp_path/'tmp').mkdir()
    (tmp_path/'src/app.py').write_text('print("hello")',encoding='utf-8')
    (tmp_path/'tmp/deepseek-key.dpapi').write_text('private-data',encoding='utf-8')
    monkeypatch.setattr('scripts.export_product_safe.subprocess.check_output',lambda *args,**kwargs:b'src/app.py\0tmp/deepseek-key.dpapi\0.env\0')
    archive=tmp_path/'safe.zip';assert export(archive,tmp_path)==1
    with zipfile.ZipFile(archive) as z: assert z.namelist()==['CodeCompass/src/app.py']
    previous=archive.read_bytes();(tmp_path/'src/app.py').write_text('sk-THIS_IS_A_TEST_SECRET_123456',encoding='utf-8')
    with pytest.raises(ValueError):export(archive,tmp_path)
    assert archive.read_bytes()==previous


def test_http_keeps_key_server_side_and_protects_posts(service,monkeypatch):
    key='sk-TEST_SERVER_ONLY_1234567890';monkeypatch.setenv('DEEPSEEK_API_KEY',key)
    uid,p,unit=connected(service,lambda *args:raw('参考当前文件与行号读取输入。'))
    server=make_server(service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def send(path,data=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-Session-Token']=token
        req=Request(base+'/api/product/'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=10) as r:return r.status,r.read()
        except HTTPError as e:return e.code,e.read()
    try:
        _,boot=send('bootstrap');token=json.loads(boot)['data']['token']
        path='source-assistant';body=dict(user_id=uid,route_id=p['id'],unit_id=unit,message='解释源码',request_id='http')
        assert send(path,body)[0]==403
        status,result=send(path,body,token)
        assert status==200 and key.encode() not in result and json.loads(result)['data']['mode']=='live'
        status,history=send(path+'?user='+uid+'&route='+p['id'])
        assert status==200 and key.encode() not in history and key.encode() not in boot
    finally:server.shutdown();server.server_close();thread.join()
