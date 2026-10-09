"""Fixed isolated PDF reader program; consumes bytes, never app procedures."""
import hashlib
import io
import json
import logging
import os
import sys

class ManualError(ValueError):
    pass

# This file is launched using -I -c from our packaged trusted source. No input
# text, PDF action, attachment, external command or model script is executed.
def constrain():
    memory=256*1024*1024
    if os.name!='nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
        resource.setrlimit(resource.RLIMIT_CPU,(6,6))
        return None
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_=[('user',ctypes.c_longlong),('job_user',ctypes.c_longlong),('flags',w.DWORD),('min',ctypes.c_size_t),('max',ctypes.c_size_t),('processes',w.DWORD),('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
    class IO(ctypes.Structure):
        _fields_=[(name,ctypes.c_ulonglong) for name in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
    class Extended(ctypes.Structure):
        _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];api.CreateJobObjectW.restype=w.HANDLE
    api.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];api.SetInformationJobObject.restype=w.BOOL
    api.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];api.AssignProcessToJobObject.restype=w.BOOL
    api.GetCurrentProcess.argtypes=[];api.GetCurrentProcess.restype=w.HANDLE
    api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
    job=api.CreateJobObjectW(None,None)
    if not job:raise RuntimeError('PDF process memory limit could not be created.')
    limit=Extended();limit.basic.flags=0x100|0x2;limit.basic.user=6*10_000_000;limit.process_memory=memory
    if not api.SetInformationJobObject(job,9,ctypes.byref(limit),ctypes.sizeof(limit)) or not api.AssignProcessToJobObject(job,api.GetCurrentProcess()):
        api.CloseHandle(job);raise RuntimeError('PDF process limits could not be applied.')
    return job  # OS releases the handle when this single reader exits.


def main():
    job=constrain()
    sys.path.insert(0,sys.argv[1])
    logging.disable(logging.CRITICAL)
    from pypdf import PdfReader,Configuration,overwrite_configuration
    config=Configuration(maximum_declared_stream_length=8_000_000,array_based_stream_maximum_output_length=8_000_000,
        zlib_maximum_output_length=8_000_000,lzw_maximum_output_length=8_000_000,run_length_maximum_output_length=8_000_000,
        stream_decoding_work_maximum_length=16_000_000,stream_filters_maximum_length=4,
        page_tree_maximum_entries=1024,page_tree_maximum_depth=32,xform_maximum_invocations_per_extraction=128,
        jbig2dec_binary=None,image_maximum_buffer_size=8_000_000)
    raw=sys.stdin.buffer.read(5_000_001)
    if not raw.startswith(b'%PDF-') or len(raw)>5_000_000:raise ManualError('Invalid or oversized PDF manual.')
    overwrite_configuration(config)
    reader=PdfReader(io.BytesIO(raw),strict=True,root_object_recovery_limit=1024)
    if reader.is_encrypted:raise ManualError('Encrypted PDF manuals are not read; no password is requested.')
    count=len(reader.pages);parts=[];pages=[];used=0;truncated=False
    for index in range(min(count,32)):
        text=(reader.pages[index].extract_text() or '').replace('\r\n','\n').replace('\r','\n').strip()
        prefix=f'[PDF page {index+1}]\n';available=24000-used-len(prefix)-2
        if available<=0:truncated=True;break
        sample=text[:available];limited=len(sample)!=len(text);truncated|=limited
        pages.append({'page':index+1,'sha256':hashlib.sha256(sample.encode()).hexdigest(),'characters':len(sample),'truncated':limited})
        if sample:parts.append(prefix+sample);used+=len(prefix)+len(sample)+2
        if limited:break
    if not parts:raise ManualError('PDF has no readable text in the inspected pages; scanned manuals require OCR, which is unavailable.')
    result={'format':'pdf','text':'\n\n'.join(parts),'pages':pages,'page_count':count,'pages_read':len(pages),
        'truncated':truncated or len(pages)<count,'process_limits':{'memory_bytes':256*1024*1024,'cpu_seconds':6}}
    sys.stdout.write(json.dumps({'result':result},ensure_ascii=True))


if __name__=='__main__':
    try:main()
    except Exception as error:
        # Library errors can contain PDF fragments; return only reviewed classes.
        message=str(error) if isinstance(error,ManualError) else 'PDF parsing failed: '+type(error).__name__
        sys.stdout.write(json.dumps({'error':message[:300]}));sys.exit(1)
