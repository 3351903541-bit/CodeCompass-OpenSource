from codecompass.graph.provenance import digest
from codecompass.product.learning_view import source_outline


def test_local_outline_keeps_defaults_conditions_and_source_coordinates():
    code='''def sample(value, /, maximum=5, *, html="<script>{`}</script>"):
    """Return the given value when it is positive."""
    if value <= 0:
        return None
    def hidden():
        return "not a sample return"
    return value
'''
    code=code.rstrip('\n')
    result=source_outline(dict(code=code,span=dict(start_line=20,content_hash=digest((code+'\n').encode()))))
    assert result['signature'].startswith('sample(value, /, maximum=5, *, html=')
    assert '<script>{`}</script>' in result['signature']
    assert [(r['line'],r['expression'],r['early']) for r in result['returns']]==[(23,'None',True),(26,'value',False)]
    assert result['returns'][0]['conditions']==['value <= 0']
    assert result['phases'][0]['line']==22


def test_bundled_demo_builds_real_route_and_local_explanations(service,monkeypatch):
    from codecompass.product import repositories
    from codecompass.product.workspaces import DEMO_COMMIT
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    def deny(*args,**kwargs):
        raise AssertionError('The bundled demo must not access the network')
    monkeypatch.setattr(repositories,'urlopen',deny)
    old=service.profile()
    demo=service.workspaces.demo();uid=demo['profile']['user_id'];route=demo['route']
    assert uid!=old['user_id'] and service.profile(old['user_id'])['preferences']==old['preferences']
    assert route['state']['snapshot']['commit']==DEMO_COMMIT and route['state']['result']['audit']['goal_complete']
    unit=next(uid for uid,v in route['state']['data']['views'].items() if v['title']=='TimestampSigner.unsign')
    assert unit in route['state']['result']['remaining']
    lesson=route['insights']['lessons'][unit]
    for i,(prompt,kind) in enumerate([('函数全景','overview'),('分阶段执行流程','flow'),('阅读路线依据','route'),('天气如何',None)]):
        ans=service.source_assistant.ask(uid,route['id'],unit,prompt,str(i))
        assert ans['mode']=='offline' and ans['status']=='completed' and ans['explanation_kind']==kind
        if kind:
            assert ans['sources'][0]['path']=='src/itsdangerous/timed.py'
        if kind=='overview':
            assert lesson['signature'] in ans['reply'] and 'max_age' in ans['reply']
        if kind=='flow':
            assert lesson['source_steps'][0]['title'] in ans['reply']
        if kind=='route':
            assert '第 ' in ans['reply'] and '步' in ans['reply']
