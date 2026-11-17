"""Explicit automated development examples; never served as learner material."""
import base64,hashlib,io,json,zipfile
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from codecompass.product.submissions import starter

def package(root,kind):
    z=zipfile.ZipFile(io.BytesIO(starter(root,'P02_window_fix')));source=z.read('candidate.py').decode()
    needle='def windowed_iter(src, size, fill=_UNSET):'
    if kind=='correct':source=source.replace(needle,needle+"\n    if type(size) is not int: raise TypeError('development example type')\n    if size <= 0: raise ValueError('development example range')")
    if kind=='wrong':source=source.replace(needle,needle+"\n    return []")
    data={'candidate.py':source.encode(),'explanation.md':'开发验证样包，非真人成绩。'.encode(),'regression_tests.py':b'print("learner record only")','patch.diff':b'development fixture','commands_and_elapsed.json':b'{"exit_code":0,"notice":"development fixture; not a platform score"}'}
    data['manifest.json']=json.dumps(dict(task_id='P02_window_fix',files={k:hashlib.sha256(v).hexdigest() for k,v in data.items()})).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as w:
        for name,content in data.items():w.writestr(name,content)
    return out.getvalue()
def act(service,s,action,payload=None):return service.action(s['session_id'],'demo-'+str(s['revision']),s['revision'],action,payload)
def exercise_flow(service,uid):
    assert service.actor!='local_user','Automated flow may not write the local user database'
    s=service.create(uid,'P02_window_fix')
    if s['phase']=='baseline':s=act(service,s,'skip_baseline')
    uid0=s['state']['remaining'][0]
    s=service.assistant.ask(s['session_id'],uid0,'用生活例子解释','demo-help','offline')['session']
    while s['phase'] in ('learning','check'):
        if s['phase']=='learning':s=act(service,s,'read',dict(unit_id=s['state']['remaining'][0]))
        else:
            s=act(service,s,'check',dict(choice=None));s=act(service,s,'check',{'continue':True})
    s=service.draft(s['session_id'],'demo-draft',s['revision'],'practice',dict(note='自动开发验证草稿'))
    for kind in ('original','wrong','correct'):
        out=service.submissions.submit(s['session_id'],'demo-'+kind,s['revision'],base64.b64encode(package(service.root,kind)).decode(),True,'明确开发演示')
        assert out['submission']['check_status']==('passed' if kind=='correct' else 'failed'),out
        s=out['session']
    assert s['phase']=='review' and s['status']=='completed'
    assert 'submission/candidate.py' in zipfile.ZipFile(io.BytesIO(service.submissions.export(s['session_id']))).namelist()
    return s


def answer_flow(service,user,task):
    assert service.actor!='local_user'
    s=service.create(user,task)
    if s['phase']=='baseline':s=act(service,s,'skip_baseline')
    while s['phase'] in ('learning','check'):
        if s['state']['plan_status']!='FEASIBLE':s=act(service,s,'budget',{'scope':'wide'})
        if s['phase']=='learning':s=act(service,s,'read',{'unit_id':s['state']['remaining'][0]})
        else:
            # Explicit unknown on unit questions exercises nonblocking supplementation.
            s=act(service,s,'check',{'choice':None});s=act(service,s,'check',{'continue':True})
    values=[q['answer'] for q in service.questions.practice(task)]
    s=act(service,s,'answers',dict(answers=values,reflection='明确开发演示：已对照固定源码核对。'))
    return s
