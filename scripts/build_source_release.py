"""Export allowlisted runtime sources/assets; tracked files by default, local edits on request."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
from contextlib import closing
from tempfile import TemporaryDirectory
import zipfile

ROOT=Path(__file__).resolve().parents[1]
LEDGERS={'data/ledgers/ledgers.sqlite3','data/ledgers/ledgers-2024.sqlite3','data/ledgers/ledgers-2023.sqlite3'}
RUNTIME_DATA={
    *LEDGERS,'data/statements/statements.sqlite3','data/appendices/balance.sqlite3',
    'data/appendices/operation.sqlite3','data/deposit/fixed_accounts.sqlite3',
    'data/deposit/regular_accounts.sqlite3','data/transfer/accounts.sqlite3',
    'data/govsubsidy/statements.json','data/fund/statements.json',
}


def allowed(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts:return False
    if len(path.parts)==1:
        return path.suffix in ('.py','.pyw') or name in ('requirements.txt','source_start.bat','SOURCE_TEST_README.md')
    if name in RUNTIME_DATA or (path.parts[:3]==('data','appendices','originals')
                              and len(path.parts)==4 and path.suffix.lower() in ('.xlsx','.xlsm','.xls')):
        return True
    return path.parts[0] in ('assets','templates','scripts') and not any(p.startswith('.') or p=='__pycache__' for p in path.parts)


def compact_ledger(source,target):
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as original:
        with closing(sqlite3.connect(target)) as runtime:
            original.backup(runtime)
            runtime.execute('ALTER TABLE entries DROP COLUMN raw_json')
            runtime.commit()
            runtime.execute('VACUUM')
            if runtime.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Ledger snapshot integrity check failed')


def build(label,output,working_tree=False):
    if not re.fullmatch(r'source-dev\.[1-9][0-9]*',label):raise ValueError('Invalid source release label')
    command=['git','ls-files','-z']
    if working_tree:command += ['--cached','--others','--exclude-standard']
    files=set(subprocess.check_output(command,cwd=ROOT).decode().split('\0'))
    if missing:=RUNTIME_DATA-files:raise ValueError(f'Missing runtime data: {sorted(missing)}')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    target=output/f'WorkSpace-{label}.zip';prefix=f'WorkSpace-{label}/'
    with TemporaryDirectory(prefix='workspace-release-') as temporary, \
            zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for name in sorted(filter(allowed,filter(None,files))):
            path=ROOT/name
            if path.is_symlink():raise ValueError('Symlinks are not allowed in source releases')
            if name in LEDGERS:
                snapshot=Path(temporary)/path.name
                compact_ledger(path,snapshot)
                path=snapshot
            bundle.write(path,prefix+name)
        bundle.writestr(prefix+'build-profile.json',json.dumps({'beta':'3.3-beta.1','source':label}))
        bundle.writestr(prefix+'source-release.json',json.dumps({'label':label,'working_tree':working_tree,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}))
    with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    checksum=output/(target.name+'.sha256');checksum.write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(target);return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--output',default='dist/source')
    parser.add_argument('--working-tree',action='store_true');options=parser.parse_args();build(options.label,options.output,options.working_tree)
