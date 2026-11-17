import json,threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from scripts.serve_product import make_server

def test_http_security_and_preview(service):
    server=make_server(service,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    def req(path,data=None,headers=None):
        r=Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers or {})
        try:
            with urlopen(r,timeout=10) as res:return res.status,json.load(res)
        except HTTPError as e:return e.code,json.load(e)
    try:
        assert req('/api/product/health')[1]['data']['database']=='available'
        boot=req('/api/product/bootstrap')[1]['data'];h={'X-Session-Token':boot['token'],'Content-Type':'application/json'}
        assert req('/api/product/profile',{})[0]==403
        assert req('/api/product/health',headers={'Host':'evil.example'})[0]==403
        assert req('/api/product/profile',{},dict(h,Origin='https://evil.example'))[0]==403
        u=req('/api/product/profile',{},h)[1]['data']['user_id']
        s=req('/api/product/session',dict(user_id=u,task_id='P02_window_fix'),h)[1]['data']
        assert req('/api/product/session?id='+s['session_id'])[1]['data']==s
        assert req('/api/product/material?session='+s['session_id']+'&unit=B07_more_chunked')[0]==400
        assert req('/api/product/session',dict(user_id=u,task_id='bad'),h)[0]==400
        assert req('/content/product/questions.private.json')[0]==404
        assert req('/api/product/assistant',{},h)[0]==400
        assert req('/api/product/issues?session='+s['session_id'])[0]==200
        assert req('/api/product/transfer',dict(session_id=s['session_id']),h)[0]==400
        body=dict(session_id=s['session_id'],revision=0,request_id='a',action='pause')
        assert req('/api/product/action',body,h)[0]==200
        body['request_id']='b';assert req('/api/product/action',body,h)[0]==409
    finally:server.shutdown();server.server_close();thread.join()


def test_occupied_port_is_rejected(service):
    import pytest
    server=make_server(service,0)
    try:
        with pytest.raises(OSError):make_server(service,server.server_port)
    finally:server.server_close()
