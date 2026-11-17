import io,json,zipfile
from scripts.product_demo import answer_flow
from codecompass.product.examples import pinned_chunked

def test_export_only_current_session_and_public_sources(service):
    first=service.profile()['user_id'];other=service.profile()['user_id']
    unrelated=answer_flow(service,other,'P01_unique_read')
    with service.store.connect() as db:
        db.execute('UPDATE product_drafts SET content_json=? WHERE session_id=?',(json.dumps({'reflection':'OTHER_USER_SECRET'}),unrelated['session_id']))
    s=answer_flow(service,first,'P04_chunked_transfer')
    raw=service.submissions.export(s['session_id'])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert set(z.namelist())=={'learning-record.json','sources.json','answers.json','assistant.json','README.txt'}
        combined=b' '.join(z.read(n) for n in z.namelist())
        assert unrelated['session_id'].encode() not in combined and b'OTHER_USER_SECRET' not in combined
        assert b'questions.private' not in combined and b'DEEPSEEK_API_KEY' not in combined
        sources=json.loads(z.read('sources.json'))
        assert sources['repository'].endswith('/more-itertools')
        assert any(r['source_span']['path'].endswith('recipes.py') for r in sources['supporting_context'])
        answers=json.loads(z.read('answers.json'));assert all(r['project']==sources['snapshot_id'] for r in answers)

def test_fixed_chunked_and_take_context(service):
    context=pinned_chunked(service.root);chunked=context['chunked'];take=context['take']
    assert list(chunked([1,2,3,4,5],2))==[[1,2],[3,4],[5]]
    it=iter([3,6,9,12,15]);assert take(2,it)==[3,6] and take(2,it)==[9,12] and list(it)==[15]
