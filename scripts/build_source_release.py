"""Export allowlisted runtime sources/assets; tracked files by default, local edits on request."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def allowed(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:return False
    if len(path.parts)==1:
        return path.suffix in ('.py','.pyw') or name in ('requirements.txt','source_start.bat','SOURCE_TEST_README.md')
    if name in ('data/govsubsidy/statements.json','data/fund/statements.json'):
        return True
    return path.parts[0] in ('assets','templates','scripts') and not any(p.startswith('.') or p=='__pycache__' for p in path.parts)


def build(label,output,working_tree=False):
    if not re.fullmatch(r'source-dev\.[1-9][0-9]*',label):raise ValueError('Invalid source release label')
    command=['git','ls-files','-z']
    if working_tree:command += ['--cached','--others','--exclude-standard']
    files=set(subprocess.check_output(command,cwd=ROOT).decode().split('\0'))
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    target=output/f'WorkSpace-{label}.zip';prefix=f'WorkSpace-{label}/'
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for name in sorted(filter(allowed,filter(None,files))):
            path=ROOT/name
            if path.is_symlink():raise ValueError('Symlinks are not allowed in source releases')
            bundle.write(path,prefix+name)
        bundle.writestr(prefix+'build-profile.json',json.dumps({'beta':'3.3-beta.1','source':label}))
        bundle.writestr(prefix+'source-release.json',json.dumps({'label':label,'working_tree':working_tree,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}))
    checksum=output/(target.name+'.sha256');checksum.write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+target.name+'\n',encoding='utf-8')
    print(target);return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--output',default='dist/source')
    parser.add_argument('--working-tree',action='store_true');options=parser.parse_args();build(options.label,options.output,options.working_tree)
