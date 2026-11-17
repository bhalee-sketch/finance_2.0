"""Versioned Windows releases. Never replace user settings or source workbooks."""
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY='bhalee-sketch/financetool'
API=f'https://api.github.com/repos/{REPOSITORY}'
MAX_ARCHIVE=700*1024*1024
MAX_EXPANDED=2*1024*1024*1024

class UpdateError(ValueError):pass

class GithubAccessError(UpdateError):
    """Access may require a private-repository credential or renewed permission."""
    pass

def version_key(version):
    if not isinstance(version,str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,9}',version):
        raise UpdateError('업데이트 버전 형식이 올바르지 않습니다.')
    return tuple(map(int,version.split('.')))

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def install_root():
    value=os.environ.get('WORKSPACE_INSTALL_ROOT')
    return Path(value).resolve() if value else None

def release_path(root,version):
    version_key(version)
    return Path(root)/'versions'/version

def release_metadata(folder):
    info=read_json(Path(folder)/'release.json');version_key(info.get('version'))
    if info.get('repository')!=REPOSITORY or info.get('platform')!='windows-x64' or info.get('launcher_protocol')!=1:
        raise UpdateError('이 프로그램에서 지원하지 않는 업데이트입니다.')
    if not (Path(folder)/'WorkSpaceApp.exe').is_file():raise UpdateError('실행 파일이 없는 업데이트입니다.')
    return info

def current_state(root):
    state=read_json(Path(root)/'current.json');version_key(state.get('current'))
    if state.get('previous'):version_key(state['previous'])
    return state

class GithubRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        parsed=urllib.parse.urlparse(newurl)
        if parsed.scheme!='https' or parsed.hostname not in ('api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):
            raise UpdateError('허용되지 않은 다운로드 주소입니다.')
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None and parsed.hostname!='api.github.com':redirected.remove_header('Authorization')
        return redirected

class GithubClient:
    def __init__(self,token=''):
        self.token=token.strip();self.opener=urllib.request.build_opener(GithubRedirect())
    def open(self,url,asset=False):
        if not url.startswith(API+'/'):raise UpdateError('다른 저장소의 다운로드는 지원하지 않습니다.')
        headers={'User-Agent':'WorkSpace-Updater','Accept':'application/octet-stream' if asset else 'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        if self.token:headers['Authorization']='Bearer '+self.token
        try:return self.opener.open(urllib.request.Request(url,headers=headers),timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403,404):raise GithubAccessError('배포 버전이 없거나 GitHub 읽기 권한이 없습니다. 비공개 저장소라면 인증을 입력하세요.') from None
            raise UpdateError(f'GitHub 연결 실패 (HTTP {exc.code}). 잠시 후 다시 시도하세요.') from None
        except (urllib.error.URLError,TimeoutError,OSError):raise UpdateError('GitHub에 연결할 수 없습니다. 인터넷 연결을 확인하세요.') from None
    def json(self,url,asset=False):
        with self.open(url,asset) as response:
            data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise UpdateError('업데이트 정보가 너무 큽니다.')
        return json.loads(data)
    def latest(self,current):
        version_key(current)
        releases=self.json(API+'/releases?per_page=30')
        candidates=[]
        for item in releases:
            if item.get('draft'):continue
            tag=item.get('tag_name','')
            if not re.fullmatch(r'v\d+\.\d+\.\d+',tag):continue
            version=tag[1:]
            if version_key(version)>version_key(current):candidates.append((version_key(version),item))
        if not candidates:return None
        release=max(candidates,key=lambda pair:pair[0])[1]
        assets={a['name']:a for a in release['assets']}
        if 'update.json' not in assets or 'WorkSpace-windows-x64.zip' not in assets:raise UpdateError('배포 파일이 아직 준비되지 않았습니다.')
        manifest=self.json(API+'/releases/assets/'+str(int(assets['update.json']['id'])),True)
        version_key(manifest.get('version'))
        if manifest['version']!=release['tag_name'][1:] or manifest.get('repository')!=REPOSITORY or manifest.get('platform')!='windows-x64' or manifest.get('launcher_protocol')!=1:
            raise UpdateError('업데이트 정보가 배포 버전과 일치하지 않습니다.')
        if not re.fullmatch(r'[0-9a-f]{64}',str(manifest.get('sha256',''))):raise UpdateError('다운로드 검증 정보가 없습니다.')
        if type(manifest.get('size')) is not int or not 0<manifest['size']<=MAX_ARCHIVE:raise UpdateError('지원하지 않는 업데이트 크기입니다.')
        manifest['asset_id']=int(assets['WorkSpace-windows-x64.zip']['id']);manifest['notes']=release.get('body','')[:12000]
        return manifest
    def download(self,manifest,path,progress=lambda value:None):
        digest=hashlib.sha256();received=0
        with self.open(API+'/releases/assets/'+str(manifest['asset_id']),True) as response,Path(path).open('xb') as output:
            while block:=response.read(1024*1024):
                received+=len(block)
                if received>manifest['size']:raise UpdateError('다운로드 크기가 배포 정보와 다릅니다.')
                output.write(block);digest.update(block);progress(round(received/manifest['size']*100))
        if received!=manifest['size'] or digest.hexdigest()!=manifest['sha256']:raise UpdateError('다운로드 검증에 실패했습니다. 기존 버전은 유지됩니다.')

def extract_release(archive,destination):
    destination=Path(destination);seen=set();total=0
    with zipfile.ZipFile(archive) as bundle:
        entries=bundle.infolist()
        if len(entries)>30000:raise UpdateError('업데이트 파일 수 제한을 초과했습니다.')
        for item in entries:
            name=item.filename;path=PurePosixPath(name)
            if '\\' in name or ':' in name or path.is_absolute() or not path.parts or any(p in ('..','.') or p.endswith(('.', ' ')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',p) for p in name.rstrip('/').split('/')):
                raise UpdateError('업데이트 압축 파일에 잘못된 경로가 있습니다.')
            if stat.S_ISLNK(item.external_attr>>16):raise UpdateError('업데이트에는 링크를 포함할 수 없습니다.')
            normalized=str(path).casefold()
            if normalized in seen:raise UpdateError('업데이트 파일 이름이 중복됩니다.')
            seen.add(normalized);total+=item.file_size
            if total>MAX_EXPANDED:raise UpdateError('업데이트 압축 해제 크기 제한을 초과했습니다.')
        bundle.extractall(destination)
    return release_metadata(destination)

def prepare_release(root,manifest,client,progress=lambda value:None):
    root=Path(root);target=release_path(root,manifest['version'])
    if target.exists():
        verified=target.parent/(target.name+'.verified.json')
        if verified.is_file() and read_json(verified).get('sha256')==manifest['sha256'] and release_metadata(target)['version']==manifest['version']:
            return target
        raise UpdateError('같은 버전 폴더가 있지만 검증 정보를 확인할 수 없습니다. 설치 파일로 복구하세요.')
    stage=root/'downloads';stage.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='update-',dir=stage) as temporary:
        archive=Path(temporary)/'release.zip';payload=Path(temporary)/'payload'
        client.download(manifest,archive,progress);info=extract_release(archive,payload)
        if info['version']!=manifest['version']:raise UpdateError('실행 파일의 버전이 일치하지 않습니다.')
        target.parent.mkdir(parents=True,exist_ok=True)
        # Directory rename only; current.json is untouched until the application exits.
        payload.rename(target)
        atomic_json(target.parent/(target.name+'.verified.json'),{'sha256':manifest['sha256']})
    return target
