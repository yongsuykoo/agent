"""Local file goals share task permission, STOP and durable output checkpoints."""
from datetime import datetime,timezone
import os
from .file_tools import prepare,inventory,execute,verify
from .native_tasks import _save


def run_files(director,task,request):
    checkpoint=director.checkpoint;started=False
    result={'task':task,'outcome':'blocked','steps':[],'verified_results':[],
            'time':datetime.now(timezone.utc).isoformat(),
            'scope':'Exact local paths and saved file bytes verified; no source execution or universal app certification.'}
    durable={'tool':'files','request':request,'steps':[{'task':task,'expected_result':'Verified file bytes'}]}
    def guard():
        if director.cancel.is_set():raise RuntimeError('File task cancelled.')
        if checkpoint:checkpoint.touch()
    try:
        guard()
        if checkpoint:
            saved=checkpoint.jobs.get(checkpoint.id)
            if saved['plan'] and saved['plan']!=durable:
                if saved['verified'] or checkpoint.pending_actions():raise RuntimeError('Saved file scope changed after an effect; no automatic replay.')
                director.emit('Selecting the native file tool before any previous action; source and output scope remain the submitted task.')
            if saved['verified']:
                record=checkpoint.records()[-1]
                proof=verify(request['destination'],request['kind'],record['manifest'],guard)
                if [proof]!=saved['verified'][0]:raise RuntimeError('Previously verified file output changed; no automatic recreation.')
                result.update(outcome='artifacts_verified',steps=[record],verified_results=[proof])
                return _save(director,result)
        observation={'window':'Local file tools','window_handle':None,'process_id':os.getpid(),
                     'controls':[{'id':0,'name':request['destination'],'type':'File output'}]}
        action={'kind':'create_artifact','target':0,'text':request['kind']+': '+request['source']+' → '+request['destination'],
                'reason':'Read only the explicitly requested source and create a new output; verify all saved bytes.'}
        if not director.approve(action,observation):
            result['outcome']='cancelled' if director.cancel.is_set() else 'blocked'
            return _save(director,result)
        guard();source,destination=prepare(request)
        director.emit('Inspecting requested source files; no provider call is needed.')
        manifest=inventory(source,request['kind'],guard)
        if checkpoint:checkpoint.save_plan(durable)
        guard()
        record={'tool':'files','request':request,'manifest':manifest,'path':str(destination)}
        result['steps'].append(record)
        effect=checkpoint.begin_effect({'kind':'create_artifact','path':str(destination),'operation':request['kind']}) if checkpoint else None
        started=True;execute(request,manifest,guard)
        if checkpoint:checkpoint.applied(effect)
        proof=verify(destination,request['kind'],manifest,guard);guard()
        record.update(outcome='artifact_verified',verification=proof)
        if checkpoint:checkpoint.verified([proof],record)
        result.update(outcome='artifacts_verified',verified_results=[proof])
        director.emit('Verified file output: '+str(destination))
    except Exception as error:
        result.update(error=str(error)[:1500],outcome='cancelled' if director.cancel.is_set() else 'verification_failed' if started else 'blocked')
        director.emit('File task stopped: '+str(error)[:500])
    return _save(director,result)
