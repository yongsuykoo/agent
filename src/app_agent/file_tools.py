"""Fixed local file operations with exclusive outputs and independent verification.

No model-generated commands, implicit source paths, extraction or file execution.
"""
import hashlib
import json
import os
from pathlib import Path,PureWindowsPath
import re
import stat
import zipfile

MAX_ENTRIES=4096
MAX_BYTES=2*1024**3
CHUNK=1024*1024


def file_request(task):
    if not isinstance(task,str) or len(task)>8000:return None
    quote=r'"([^"\r\n]+)"'
    suffix=r'(?:\s+and\s+verify(?:\s+(?:the\s+)?(?:result|copy|archive))?)?\s*[.]?'
    patterns=[
        ('copy_file',r'copy\s+(?:the\s+)?file\s+'+quote+r'\s+to\s+(?:new\s+file\s+)?'+quote),
        ('copy_folder',r'copy\s+(?:the\s+)?folder\s+'+quote+r'\s+to\s+(?:a\s+)?(?:new\s+)?folder\s+'+quote),
        ('copy_folder',r'copy\s+all\s+files\s+from\s+(?:the\s+)?folder\s+'+quote+r'\s+to\s+(?:a\s+)?(?:new\s+)?folder\s+'+quote),
        ('zip_folder',r'(?:create|make)\s+(?:a\s+)?zip\s+archive\s+(?:of|from)\s+(?:the\s+)?folder\s+'+quote+r'\s+(?:at|to|as)\s+'+quote),
        ('zip_folder',r'compress\s+(?:the\s+)?folder\s+'+quote+r'\s+(?:into|to)\s+'+quote),
    ]
    for kind,pattern in patterns:
        match=re.fullmatch(pattern+suffix,task.strip(),re.I)
        if match:return {'kind':kind,'source':match[1],'destination':match[2]}
    return None


def safe_path(value):
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts or '\x00' in str(path):
        raise ValueError('File tools require explicit absolute paths without parent traversal.')
    if os.name=='nt':
        windows_path(str(path))
    for part in [path,*path.parents]:
        try:info=part.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('File paths cannot traverse links, junctions or reparse points.')
    return path


def windows_path(value):
    path=PureWindowsPath(value)
    if not path.is_absolute() or not re.fullmatch(r'[A-Za-z]:',path.drive):raise ValueError('File tools require a local drive path; device and network paths are unsupported.')
    for part in path.parts[1:]:
        if part in ('.','..') or any(c in part for c in ':<>"|?*') or any(ord(c)<32 for c in part) or part.endswith((' ','.')) or re.fullmatch(r'(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part,re.I):
            raise ValueError('Alternate streams and reserved Windows paths are unsupported.')
    return path


def identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def read_chunks(path,guard):
    safe_path(path);before=path.stat()
    if not stat.S_ISREG(before.st_mode):raise ValueError('Only regular files can be read.')
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
    descriptor=os.open(path,flags)
    with os.fdopen(descriptor,'rb') as stream:
        if identity(os.fstat(stream.fileno()))!=identity(before):raise ValueError('File changed before it could be read.')
        while True:
            guard();data=stream.read(CHUNK)
            if not data:break
            yield data
        safe_path(path)
        if identity(os.fstat(stream.fileno()))!=identity(before) or identity(path.stat())!=identity(before):
            raise ValueError('File changed while being read; verification stopped.')


def digest(path,guard=lambda:None):
    hasher=hashlib.sha256();size=0
    for data in read_chunks(Path(path),guard):hasher.update(data);size+=len(data)
    return {'size':size,'sha256':hasher.hexdigest()}


def validate_manifest(manifest,kind):
    if not isinstance(manifest,dict) or set(manifest)!={'files','directories'} or not all(isinstance(manifest[k],list) for k in manifest):
        raise ValueError('Invalid file inventory.')
    names=[];total=0
    def name(value):
        if not isinstance(value,str) or not value or value.startswith('/') or any(p in ('','.', '..') or '\\' in p or ':' in p or p.endswith((' ','.')) or any(ord(c)<32 for c in p) for p in value.split('/')):
            raise ValueError('Inventory names must be safe relative paths.')
        names.append(value.casefold())
    for item in manifest['files']:
        if not isinstance(item,dict) or set(item)!={'name','size','sha256'} or type(item['size']) is not int or item['size']<0 or not isinstance(item['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',item['sha256']):
            raise ValueError('Invalid file inventory entry.')
        total+=item['size']
        if kind=='copy_file' and item['name']=='.':names.append('.')
        else:name(item['name'])
    for value in manifest['directories']:name(value)
    if len(names)>MAX_ENTRIES or total>MAX_BYTES or len(names)!=len(set(names)):raise ValueError('File inventory exceeds bounds or contains duplicate names.')
    if kind=='copy_file':
        if len(manifest['files'])!=1 or manifest['files'][0]['name']!='.' or manifest['directories']:raise ValueError('Single-file inventory is invalid.')
    elif kind not in ('copy_folder','zip_folder'):raise ValueError('Unknown file inventory kind.')
    directories=set(manifest['directories'])
    for value in [item['name'] for item in manifest['files']]+manifest['directories']:
        parts=value.split('/')
        if any('/'.join(parts[:i]) not in directories for i in range(1,len(parts))):raise ValueError('Inventory omits a required parent directory.')
    return manifest


def listing(root,guard=lambda:None):
    root=safe_path(root)
    if not root.is_dir():raise ValueError('The requested source/output folder is missing.')
    files=[];directories=[];pending=[root];names=set();total=0
    while pending:
        parent=pending.pop();guard();safe_path(parent)
        with os.scandir(parent) as entries:
            for entry in entries:
                guard();path=safe_path(entry.path);relative=path.relative_to(root).as_posix()
                normalized=relative.casefold()
                if normalized in names:raise ValueError('Case-colliding names cannot be represented portably.')
                names.add(normalized)
                if len(names)>MAX_ENTRIES:raise ValueError('File task exceeds the supported entry count.')
                # These cannot become an alternate stream or ZIP path separator on Windows.
                if any('\\' in p or ':' in p or p.endswith((' ','.')) or any(ord(c)<32 for c in p) for p in path.relative_to(root).parts):
                    raise ValueError('Folder contains an unsupported filename.')
                info=path.lstat()
                if stat.S_ISDIR(info.st_mode):directories.append(relative);pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    total+=info.st_size
                    if total>MAX_BYTES:raise ValueError('File task exceeds the supported byte count.')
                    files.append({'name':relative,'size':info.st_size})
                else:raise ValueError('Only regular files and directories are supported.')
    return {'files':sorted(files,key=lambda p:p['name']),'directories':sorted(directories)}


def inventory(source,kind,guard=lambda:None):
    source=safe_path(source)
    if kind=='copy_file':
        if not source.is_file() or source.stat().st_size>MAX_BYTES:raise ValueError('Source must be a supported regular file.')
        return {'files':[{'name':'.',**digest(source,guard)}],'directories':[]}
    result=listing(source,guard)
    for item in result['files']:item.update(digest(source/item['name'],guard))
    # Detect additions/removals and size changes during the scan, before creating output.
    if listing(source,guard)!={'files':[{'name':f['name'],'size':f['size']} for f in result['files']],'directories':result['directories']}:
        raise ValueError('Source folder changed during inventory.')
    return result


def prepare(request):
    if set(request)!={'kind','source','destination'} or request['kind'] not in ('copy_file','copy_folder','zip_folder'):
        raise ValueError('Invalid fixed file operation.')
    source,destination=(safe_path(request[k]) for k in ('source','destination'))
    if not source.exists():raise ValueError('Requested source does not exist.')
    if source==destination or source.is_dir() and destination.is_relative_to(source):
        raise ValueError('Destination cannot be the source or inside its folder.')
    if destination.exists():raise FileExistsError('Destination already exists; no existing output is overwritten.')
    if not destination.parent.is_dir():raise ValueError('Destination parent folder must already exist.')
    if request['kind']=='zip_folder' and destination.suffix.casefold()!='.zip':raise ValueError('ZIP output needs a .zip filename.')
    return source,destination


def _copy(source,destination,expected,guard):
    guard();safe_path(destination);hasher=hashlib.sha256();size=0
    with destination.open('xb') as output:
        for data in read_chunks(source,guard):output.write(data);hasher.update(data);size+=len(data)
        output.flush();os.fsync(output.fileno())
    if {'size':size,'sha256':hasher.hexdigest()}!={k:expected[k] for k in ('size','sha256')}:
        raise ValueError('Source content changed after inventory; partial output retained.')
    safe_path(destination)


def execute(request,manifest,guard=lambda:None):
    kind=request['kind'];validate_manifest(manifest,kind)
    source,destination=prepare(request);guard()
    if kind=='copy_file':_copy(source,destination,manifest['files'][0],guard)
    elif kind=='copy_folder':
        destination.mkdir(exist_ok=False)
        for name in sorted(manifest['directories'],key=lambda s:(s.count('/'),s)):
            guard();safe_path(destination/name).mkdir(exist_ok=False)
        for item in manifest['files']:_copy(source/item['name'],destination/item['name'],item,guard)
    else:
        with destination.open('xb') as output:
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
                for name in manifest['directories']:
                    guard();archive.writestr(name+'/',b'')
                for item in manifest['files']:
                    guard();hasher=hashlib.sha256();size=0
                    with archive.open(item['name'],'w',force_zip64=True) as member:
                        for data in read_chunks(source/item['name'],guard):member.write(data);hasher.update(data);size+=len(data)
                    if {'size':size,'sha256':hasher.hexdigest()}!={k:item[k] for k in ('size','sha256')}:
                        raise ValueError('Source content changed after inventory; partial archive retained.')
            output.flush();os.fsync(output.fileno())
        safe_path(destination)
    if inventory(source,kind,guard)!=manifest:raise ValueError('Source content changed during the task; completion is unverified.')


def verify(destination,kind,manifest,guard=lambda:None):
    validate_manifest(manifest,kind);destination=safe_path(destination);guard()
    if kind=='copy_file':
        proof=digest(destination,guard)
        if proof!={k:manifest['files'][0][k] for k in ('size','sha256')}:raise ValueError('Copied file differs from the requested source bytes.')
    elif kind=='copy_folder':
        if inventory(destination,kind,guard)!=manifest:raise ValueError('Copied folder differs from the source inventory.')
        proof={'sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
               'size':sum(f['size'] for f in manifest['files'])}
    elif kind=='zip_folder':
        before=identity(destination.stat())
        expected={item['name']:item for item in manifest['files']}
        names=set(expected)|{name+'/' for name in manifest['directories']}
        with zipfile.ZipFile(destination) as archive:
            if len(archive.infolist())!=len(names) or set(archive.namelist())!=names:raise ValueError('ZIP entries differ from the source inventory.')
            for info in archive.infolist():
                guard()
                if info.flag_bits&1:raise ValueError('Encrypted archive entries are unsupported.')
                if info.is_dir():
                    if info.file_size:raise ValueError('Archive directory contains unexpected data.')
                    continue
                item=expected[info.filename]
                if info.file_size!=item['size']:raise ValueError('ZIP member size differs from source.')
                hasher=hashlib.sha256();size=0
                with archive.open(info) as member:
                    while True:
                        guard();data=member.read(CHUNK)
                        if not data:break
                        hasher.update(data);size+=len(data)
                        if size>item['size']:raise ValueError('Archive entry exceeds its expected size.')
                if size!=item['size'] or hasher.hexdigest()!=item['sha256']:raise ValueError('Archived bytes differ from the requested source.')
        proof=digest(destination,guard)
        if identity(destination.stat())!=before:raise ValueError('ZIP file changed during verification.')
    else:raise ValueError('Unknown file verification kind.')
    return {'path':str(destination),'kind':kind,**proof,'entries':len(manifest['files'])+len(manifest['directories'])}
