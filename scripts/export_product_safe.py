"""Allowlisted source-only hand-in package; no local runtime data or credentials."""
import argparse
import os
import re
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','pyproject.toml','LICENSE','LICENSE.md','LICENSE.txt'}
PREFIXES=('app/','src/','scripts/','configs/','content/','schemas/','benchmarks/dev/','benchmarks/sources/')
EXTENSIONS={'.py','.ps1','.json','.html','.css','.js','.toml','.txt','.md','.rst','.yaml','.yml','.in'}


def included(name):
    p=Path(name)
    return (name in ROOT_FILES or name=='docs/源码助手与密钥安全.md' or
            (name.startswith(PREFIXES) and (p.suffix.lower() in EXTENSIONS or p.name in ('LICENSE','COPYING','NOTICE')) and
             not any(x in p.parts for x in ('frozen','__pycache__','.git','.venv','local_data','tmp'))))


def assert_safe(name,data,known_key=None):
    if not included(name): raise ValueError('不允许打包的路径：'+name)
    if known_key and known_key.encode() in data: raise ValueError('检测到当前API密钥，已停止打包；文件：'+name)
    if re.search(rb'sk-[A-Za-z0-9_-]{16,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',data):
        raise ValueError('检测到疑似凭据，已停止打包；文件：'+name)


def export(destination,root=ROOT,*,known_key=None):
    names=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode('utf-8').split('\0')
    selected=[]
    for name in sorted(filter(included,filter(None,names))):
        path=root/name
        if path.is_symlink(): raise ValueError('不打包符号链接：'+name)
        raw=path.read_bytes();assert_safe(name,raw,known_key);selected.append((name,raw))
    if not selected: raise ValueError('未找到已纳入版本管理的作品源码')
    # Validate before touching the output; an unsafe source leaves the previous ZIP intact.
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.tmp')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in selected:z.writestr('CodeCompass/'+name,raw)
    with zipfile.ZipFile(temporary) as z:
        if z.testzip(): raise ValueError('作品包校验失败')
        for member in z.infolist():assert_safe(member.filename.removeprefix('CodeCompass/'),z.read(member),known_key)
    temporary.replace(destination)
    return len(selected)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'tmp/CodeCompass-source-safe.zip');args=parser.parse_args()
    try:count=export(args.output,known_key=os.environ.get('DEEPSEEK_API_KEY'))
    except (ValueError,subprocess.CalledProcessError) as exc:parser.exit(1,str(exc)+'\n')
    print(f'已生成不含本机密钥与用户数据的源码包：{args.output}（{count}个文件）')
