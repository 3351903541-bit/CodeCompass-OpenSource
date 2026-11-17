import base64,hashlib,io,json,zipfile,stat
from pathlib import Path
import pytest
from codecompass.product.submissions import starter,validate_package,MAX_ZIP,FILES
from tests.product.test_learning import to_practice

def package(service,kind='original'):
    z=zipfile.ZipFile(io.BytesIO(starter(service.root,'P02_window_fix')))
    source=z.read('candidate.py').decode()
    needle='def windowed_iter(src, size, fill=_UNSET):'
    if kind=='correct':source=source.replace(needle,needle+"\n    if type(size) is not int: raise TypeError('size type')\n    if size <= 0: raise ValueError('size range')")
    if kind=='wrong':source=source.replace(needle,needle+"\n    return []")
    data={'candidate.py':source.encode(),'explanation.md':'开发验证样包，非真人成绩。'.encode(),'regression_tests.py':b'print("not a platform result")','patch.diff':b'development sample','commands_and_elapsed.json':b'{"exit_code":0,"notice":"learner record only"}'}
    data['manifest.json']=json.dumps({'task_id':'P02_window_fix','files':{n:hashlib.sha256(b).hexdigest() for n,b in data.items()}}).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as w:
        for n,b in data.items():w.writestr(n,b)
    return out.getvalue()
@pytest.mark.parametrize('kind,expected',[('original','failed'),('correct','passed'),('wrong','failed')])
def test_actual_public_checks(service,kind,expected):
    uid=service.profile()['user_id'];s=to_practice(service,service.create(uid,'P02_window_fix'))
    raw=package(service,kind)
    out=service.submissions.submit(s['session_id'],'submit',s['revision'],base64.b64encode(raw).decode(),True)
    assert out['submission']['check_status']==expected,out
    assert out['session']['phase']==('review' if expected=='passed' else 'practice')
    same=service.submissions.submit(s['session_id'],'submit',s['revision'],base64.b64encode(raw).decode(),True)
    assert same['submission']==out['submission']
    if expected=='passed':
        assert out['session']['status']=='completed'
        exported=zipfile.ZipFile(io.BytesIO(service.submissions.export(s['session_id'])))
        assert 'submission/candidate.py' in exported.namelist()
    assert service.store.evidence.read(uid,simulated=True)['records']==[]

def test_zip_errors(service):
    for name in ('../candidate.py','C:/candidate.py','sub/candidate.py'):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:z.writestr(name,b'')
        with pytest.raises(ValueError):validate_package(raw.getvalue())
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
        link=zipfile.ZipInfo('candidate.py');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(link,b'target')
    with pytest.raises(ValueError):validate_package(raw.getvalue())
    with pytest.raises(ValueError):validate_package(b'x'*(MAX_ZIP+1))
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:z.writestr('candidate.py',b'')
    with pytest.raises(ValueError,match='缺少'):validate_package(raw.getvalue())
