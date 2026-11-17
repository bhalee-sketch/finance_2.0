"""Per-Windows-user encrypted updater credential; never store plaintext."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
from release_update import UpdateError

class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def _crypt(data,decrypt=False):
    if sys.platform!='win32':raise UpdateError('토큰 저장은 Windows에서만 지원합니다.')
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));result=Blob()
    api=ctypes.WinDLL('crypt32',use_last_error=True)
    function=api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    function.restype=wintypes.BOOL
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise UpdateError('Windows 인증 토큰을 저장하거나 읽지 못했습니다. 토큰을 다시 입력하세요.')
    try:return ctypes.string_at(result.data,result.size)
    finally:
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
        kernel.LocalFree(result.data)

def load_token(root):
    path=Path(root)/'update-token.bin'
    return _crypt(path.read_bytes(),True).decode('utf-8') if path.exists() else ''

def save_token(root,token):
    path=Path(root)/'update-token.bin'
    if not token.strip():path.unlink(missing_ok=True);return
    encrypted=_crypt(token.strip().encode('utf-8'))
    temporary=path.with_suffix('.tmp')
    try:
        temporary.write_bytes(encrypted);temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


class Credential(ctypes.Structure):
    _fields_=[('flags',wintypes.DWORD),('type',wintypes.DWORD),
              ('target',wintypes.LPWSTR),('comment',wintypes.LPWSTR),
              ('written',wintypes.FILETIME),('size',wintypes.DWORD),
              ('data',ctypes.POINTER(ctypes.c_ubyte)),('persist',wintypes.DWORD),
              ('attribute_count',wintypes.DWORD),('attributes',ctypes.c_void_p),
              ('alias',wintypes.LPWSTR),('username',wintypes.LPWSTR)]


def load_windows_credential(target='WorkSpace.GitHub'):
    """Read only this app's Generic Credential, set through Windows settings."""
    if sys.platform!='win32':return ''
    api=ctypes.WinDLL('advapi32',use_last_error=True);pointer=ctypes.POINTER(Credential)()
    api.CredReadW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))]
    api.CredReadW.restype=wintypes.BOOL
    api.CredFree.argtypes=[ctypes.c_void_p];api.CredFree.restype=None
    if not api.CredReadW(target,1,0,ctypes.byref(pointer)):
        if ctypes.get_last_error()==1168:return ''
        raise UpdateError('Windows 업데이트 자격 증명을 읽지 못했습니다.')
    try:
        size=pointer.contents.size
        if size>65536 or size%2:raise UpdateError('Windows 업데이트 자격 증명 형식을 확인하세요.')
        return ctypes.string_at(pointer.contents.data,size).decode('utf-16-le').rstrip('\x00').strip() if size else ''
    finally:api.CredFree(pointer)


def load_update_token(root):
    """No bundled secret: reuse a PC binding, encrypted token, or OS credential."""
    import os
    configured=os.environ.get('WORKSPACE_GITHUB_TOKEN','').strip()
    if configured:return configured
    configured=load_windows_credential()
    return configured or load_token(root)


def save_windows_credential(token,target='WorkSpace.GitHub'):
    """Bind the updater once to the signed-in Windows user's credential vault."""
    if sys.platform!='win32':raise UpdateError('업데이트 인증 저장은 Windows에서 지원합니다.')
    encoded=token.strip().encode('utf-16-le')
    if not encoded or len(encoded)>2560:raise UpdateError('접근 토큰을 확인하세요.')
    buffer=ctypes.create_string_buffer(encoded)
    credential=Credential();credential.type=1;credential.target=target
    credential.username='WorkSpace';credential.persist=2;credential.size=len(encoded)
    credential.data=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte))
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    api.CredWriteW.argtypes=[ctypes.POINTER(Credential),wintypes.DWORD];api.CredWriteW.restype=wintypes.BOOL
    try:
        if not api.CredWriteW(ctypes.byref(credential),0):raise UpdateError('Windows 자격 증명 저장에 실패했습니다. 다시 시도하세요.')
    finally:ctypes.memset(buffer,0,len(buffer))
