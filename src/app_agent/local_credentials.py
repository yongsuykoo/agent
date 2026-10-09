"""Optional user-bound Windows DPAPI credential; no plaintext key file."""
import os
from pathlib import Path
import sys
from .research import validate_api_key


def credential_path(directory):
    path=Path(directory)/'provider-key.dpapi'
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [path,*path.parents]):
        raise ValueError('Credential storage cannot traverse a link or junction.')
    return path


def save_key(directory,key):
    if sys.platform!='win32':raise RuntimeError('Encrypted local key storage requires Windows DPAPI.')
    import win32crypt
    key=validate_api_key(key)
    encrypted=win32crypt.CryptProtectData(key.encode(),'App Agent provider credential',None,None,None,1)
    path=credential_path(directory);path.parent.mkdir(parents=True,exist_ok=True)
    import tempfile
    descriptor,temporary=tempfile.mkstemp(prefix='.provider-',suffix='.dpapi',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:stream.write(encrypted);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def load_key(directory):
    path=credential_path(directory)
    if not path.exists():return None
    if sys.platform!='win32':raise RuntimeError('Decrypting the local key requires its Windows account.')
    if not 1<=path.stat().st_size<=32768:raise ValueError('Invalid encrypted credential file size.')
    import win32crypt
    _,raw=win32crypt.CryptUnprotectData(path.read_bytes(),None,None,None,1)
    return validate_api_key(raw.decode())


def forget_key(directory):
    credential_path(directory).unlink(missing_ok=True)


def configured_key(directory):
    key=os.getenv('AGENT_API_KEY') or os.getenv('OPENAI_API_KEY')
    return validate_api_key(key) if key else load_key(directory)
