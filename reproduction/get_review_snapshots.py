import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

p=argparse.ArgumentParser()
p.add_argument('--manifests',required=True,type=Path)
p.add_argument('--output',required=True,type=Path)
p.add_argument('--source-cache',type=Path)
args=p.parse_args()
manifests=json.loads(args.manifests.read_bytes())
for name in ('python-slugify','schedule'):
    manifest=manifests[name]
    url=manifest['url']
    commit=manifest['commit']
    assert re.fullmatch('https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',url)
    assert re.fullmatch('[0-9a-f]{40}',commit)
    repo=url.removeprefix('https://github.com/')
    folder=args.output/name/'benchmarks/sources/imported'
    folder.mkdir(parents=True,exist_ok=True)
    source=None
    if args.source_cache:
        for path in args.source_cache.glob('*/benchmarks/sources/imported/snapshot.json'):
            match=json.loads(path.read_bytes())
            if (match['url'],match['commit'])==(url,commit):
                source=path.parent
                break
        assert source is not None,(name,commit)
    for f in manifest['files']:
        rel=PurePosixPath(f['path'])
        assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in str(rel)
        filename=folder.joinpath(*rel.parts)
        if source:
            data=(source/f['path']).read_bytes()
        else:
            request=Request(f"https://raw.githubusercontent.com/{repo}/{commit}/{quote(str(rel),safe='/')}",
                            headers={'User-Agent':'CodeCompass-review-reproduction'})
            with urlopen(request,timeout=25) as response:
                data=response.read(f['bytes']+1)
        assert len(data)==f['bytes'] and sha256(data).hexdigest()==f['sha256'],f['path']
        filename.parent.mkdir(parents=True,exist_ok=True)
        filename.write_bytes(data)
    (folder/'snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(name,commit,len(manifest['files']))
