import copy
import json
from pathlib import Path
import struct
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
import zlib

from app_agent.catalog import Catalog
from app_agent.design_artifacts import layer_names, png_info, psd_info, verify_exports
from app_agent.logo_design import constraints, logo_request, plan_logo, validate_design
from app_agent.machine import machine_report
from app_agent.native_tasks import run_logo
from app_agent.photoshop import Photoshop, select_photoshop, validate_native_identity
from app_agent.photoshop_script import render_script
from app_agent.task_director import TaskDirector
from app_agent.jobs import Jobs
from test_catalog import snapshot

DESIGN = {'width': 64, 'height': 64, 'background': None,
          'shapes': [{'color': '#0066CC', 'points': [[.2,.2],[.8,.2],[.8,.5],[.2,.5]]}],
          'texts': [{'text': 'ACME', 'color': '#CC0000', 'font': 'ArialMT', 'size': 8, 'x': .2, 'y': .8}],
          'rationale': 'A blue symbol and red editable wordmark.'}
BRIEF = 'Design a 64x64 transparent logo in Photoshop for brand "ACME" using #0066CC and #CC0000.'
APP = {'id': 'start:photoshop', 'name': 'Adobe Photoshop', 'version': '25.1', 'source': 'start_menu',
       'aliases': ['Photoshop'], 'launch_executable': r'C:\Adobe\Photoshop.exe'}
INFO = {'name': 'Adobe Photoshop', 'version': '25.1', 'path': r'C:\Adobe', 'fonts': ['ArialMT']}


def chunk(kind, payload):
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind+payload) & 0xffffffff)


def png(path, design=DESIGN, blank=False, method=0):
    w, h = design['width'], design['height']; rows = []
    previous = bytes(w * 4)
    for y in range(h):
        pixels = bytearray()
        for x in range(w):
            rgb = (0, 0, 0, 0) if design['background'] is None else (*bytes.fromhex(design['background'][1:]), 255)
            if not blank and w//5 < x < w*4//5 and h//5 < y < h//2:
                rgb = (0, 102, 204, 255)
            if not blank and w//5 < x < w//2 and h*3//4 < y < h*4//5:
                rgb = (204, 0, 0, 255)
            pixels.extend(rgb)
        encoded = bytearray(len(pixels))
        for i, value in enumerate(pixels):
            a = pixels[i-4] if i >= 4 else 0; b = previous[i]; c = previous[i-4] if i >= 4 else 0
            p = a+b-c
            pa,pb,pc = abs(p-a),abs(p-b),abs(p-c)
            paeth = a if pa <= pb and pa <= pc else b if pb <= pc else c
            predictor = [0,a,b,(a+b)//2,paeth][method]
            encoded[i] = (value - predictor) & 255
        rows.append(bytes([method])+encoded); previous = pixels
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB',w,h,8,6,0,0,0)) +
                    chunk(b'IDAT', zlib.compress(b''.join(rows))) + chunk(b'IEND', b''))


def psd(path, design=DESIGN, names=None, compression=0):
    w,h = design['width'],design['height']; records = bytearray()
    names = names or layer_names(design)
    for name in reversed(names):
        name = name.encode('ascii'); label = bytes([len(name)])+name
        label += bytes((-len(label)) % 4)
        extra = bytes(8) + label
        records.extend(struct.pack('>iiiiH',0,0,h,w,0) + b'8BIMnorm' + bytes([255,0,0,0]) + struct.pack('>I',len(extra)) + extra)
    info = struct.pack('>h',len(names)) + records
    mask = struct.pack('>I',len(info)) + info + bytes(4)
    if compression == 0:
        composite = bytes(w*h*3)
    else:
        row = bytes([257-w,0])
        composite = struct.pack('>H',len(row)) * (h*3) + row * (h*3)
    path.write_bytes(b'8BPS' + struct.pack('>H',1) + bytes(6) + struct.pack('>HIIHH',3,h,w,8,3) + bytes(8) +
                    struct.pack('>I',len(mask)) + mask + struct.pack('>H',compression) + composite)


def observation(design=DESIGN):
    return {'width':design['width'],'height':design['height'],'layers':list(reversed(layer_names(design))),
            'texts':[t['text'] for t in design['texts']], 'fonts':[t['font'] for t in design['texts']],
            'text_bounds':[[12,42,32,50] for t in design['texts']]}


def reply(design):
    return {'output':[{'content':[{'type':'output_text','text':json.dumps(design)}]}]}


class LogoPlanTests(unittest.TestCase):
    def test_specific_logo_goal_is_preserved_and_literal_text_is_not_routed_as_artwork(self):
        self.assertTrue(logo_request(BRIEF))
        self.assertFalse(logo_request('Replace the document text with exactly: design a logo'))
        self.assertEqual(constraints(BRIEF)['required_text'], 'ACME')
        self.assertEqual(validate_design(copy.deepcopy(DESIGN), BRIEF, ['ArialMT']), DESIGN)
        for field, value in [('width',128),('background','#FFFFFF')]:
            altered=copy.deepcopy(DESIGN);altered[field]=value
            with self.assertRaises(ValueError):validate_design(altered,BRIEF,['ArialMT'])
        for field, value in [('font','not-installed'),('text','wrong brand'),('size',float('nan')),('x',-1)]:
            altered=copy.deepcopy(DESIGN);altered['texts'][0][field]=value
            with self.assertRaises(ValueError):validate_design(altered,BRIEF,['ArialMT'])

    def test_executable_fields_and_degenerate_geometry_are_rejected_before_execution(self):
        for change in ({'script':'app.close()'}, {'shapes':[{'color':'#0066CC','points':[[0,0],[0,0],[0,0]]}]}):
            bad={**copy.deepcopy(DESIGN),**change}
            with self.assertRaises(ValueError):validate_design(bad,'design logo',['ArialMT'])
        cloud=Mock();cloud.request.side_effect=[reply({**DESIGN,'script':'bad'}),reply(DESIGN)]
        self.assertEqual(plan_logo(BRIEF,cloud,['ArialMT']),DESIGN)
        self.assertEqual(cloud.request.call_count,2)
        self.assertIn('declared',json.loads(cloud.request.call_args.kwargs['input'])['validation_feedback'])
        cloud.request.side_effect=None;cloud.request.return_value=reply({**DESIGN,'width':False})
        with self.assertRaises(ValueError):plan_logo(BRIEF,cloud,['ArialMT'])
        self.assertEqual(cloud.request.call_count,5)

    def test_cancellation_and_unsupported_size_make_no_provider_call(self):
        cloud=Mock();cancel=threading.Event();cancel.set()
        with self.assertRaises(RuntimeError):plan_logo(BRIEF,cloud,['ArialMT'],cancel=cancel)
        with self.assertRaises(ValueError):plan_logo('Design a 5000x5000 logo',cloud,['ArialMT'])
        with self.assertRaises(ValueError):plan_logo('Design a 10000x10000 logo',cloud,['ArialMT'])
        cloud.request.assert_not_called()

    def test_installed_edition_binding_and_duplicate_launch_entries(self):
        self.assertEqual(select_photoshop([APP,{**APP,'id':'registry:photoshop'}])['id'],APP['id'])
        self.assertEqual(select_photoshop([APP,{**APP,'id':'registry:photoshop','launch_executable':'','location':r'C:\Adobe'}])['id'],APP['id'])
        with self.assertRaises(RuntimeError):select_photoshop([APP,{**APP,'id':'other','launch_executable':r'D:\PS\Photoshop.exe'}])
        with self.assertRaises(RuntimeError):select_photoshop([])
        validate_native_identity(APP,INFO)
        for info in ({**INFO,'version':'26.0'},{**INFO,'path':r'D:\Other'},{**INFO,'fonts':'not-a-list'}):
            with self.assertRaises(ValueError):validate_native_identity(APP,info)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        psd(self.root/'logo.psd');png(self.root/'logo.png')
    def tearDown(self):self.temp.cleanup()

    def test_actual_bytes_dimensions_colors_transparency_and_layer_structure(self):
        checked=verify_exports(self.root,DESIGN,observation())
        self.assertEqual(checked['status'],'artifact_verified')
        self.assertTrue(checked['png']['pixel_content_checked'])
        self.assertGreater(checked['png']['transparent_pixels'],0)
        self.assertEqual(len(checked['files'][0]['sha256']),64)
        psd(self.root/'logo.psd',compression=1)
        self.assertEqual(psd_info(self.root/'logo.psd')['width'],64)

    def test_all_png_scanline_filters_recover_the_same_pixel_evidence(self):
        original=png_info(self.root/'logo.png',[64,64])
        for method in range(1,5):
            png(self.root/'logo.png',method=method)
            self.assertEqual(png_info(self.root/'logo.png',[64,64]),original)

    def test_blank_corrupt_wrong_dimensions_missing_color_and_mismatched_text_fail(self):
        png(self.root/'logo.png',blank=True)
        with self.assertRaises(ValueError):verify_exports(self.root,DESIGN,observation())
        png(self.root/'logo.png');data=bytearray((self.root/'logo.png').read_bytes());data[-1]^=1
        (self.root/'logo.png').write_bytes(data)
        with self.assertRaises(ValueError):verify_exports(self.root,DESIGN,observation())
        png(self.root/'logo.png')
        for obs in ({**observation(),'texts':['wrong']},{**observation(),'width':128},
                    {**observation(),'fonts':['substituted']},{**observation(),'text_bounds':[[12,42,999,50]]}):
            with self.assertRaises(ValueError):verify_exports(self.root,DESIGN,obs)
        changed=copy.deepcopy(DESIGN);changed['shapes'][0]['color']='#00FF00'
        with self.assertRaises(ValueError):verify_exports(self.root,changed,observation(changed))
        psd(self.root/'logo.psd',names=['wrong'])
        with self.assertRaises(ValueError):verify_exports(self.root,DESIGN,observation())

    def test_truncated_psd_composite_pixels_and_external_symlink_are_rejected(self):
        file=self.root/'logo.psd';file.write_bytes(file.read_bytes()[:-10])
        with self.assertRaises(ValueError):psd_info(file)
        file.unlink()
        other=self.root/'external.psd';psd(other)
        try:file.symlink_to(other)
        except OSError:self.skipTest('Symlink creation unavailable on this Windows account')
        with self.assertRaises(ValueError):verify_exports(self.root,DESIGN,observation())


class Desktop:
    def observe(self):return {'window_handle':101,'process_id':201,'controls':[]}


class NativeBindingTests(unittest.TestCase):
    def modules(self, pid=201, info=INFO):
        import sys
        self.com=Mock();self.com.DoJavaScript.return_value=json.dumps(info)
        self.client=Mock();self.client.GetActiveObject.return_value=self.com;self.client.Dispatch.return_value=self.com
        self.pythoncom=Mock()
        parent=types.ModuleType('win32com');parent.client=self.client
        return patch.dict(sys.modules,{'pythoncom':self.pythoncom,'win32com':parent,'win32com.client':self.client,
            'win32gui':types.SimpleNamespace(GetForegroundWindow=lambda:101),
            'win32process':types.SimpleNamespace(GetWindowThreadProcessId=lambda window:(11,pid))})

    def test_active_com_binding_restores_thread_and_fixed_script_exports(self):
        with self.modules(), tempfile.TemporaryDirectory() as directory:
            native=Photoshop(APP,Desktop().observe())
            self.pythoncom.CoInitialize.assert_called_once()
            self.com.DoJavaScript.side_effect=[json.dumps(INFO),json.dumps(observation())]
            value=native.render(DESIGN,Path(directory),'logo',threading.Event())
            self.assertEqual(value,observation())
            script=self.com.DoJavaScript.call_args.args[0]
            self.assertIn('new PhotoshopSaveOptions()',script)
            native.close();self.pythoncom.CoUninitialize.assert_called_once()

    def test_wrong_process_version_or_path_cannot_bind_an_operating_adapter(self):
        for pid, info in ((999,INFO),(201,{**INFO,'version':'26.0'}),(201,{**INFO,'path':r'C:\Other'})):
            with self.modules(pid,info):
                with self.assertRaises(RuntimeError):Photoshop(APP,Desktop().observe())
                self.pythoncom.CoUninitialize.assert_called_once()
                self.assertFalse(any('documents.add' in call.args[0] for call in self.com.DoJavaScript.call_args_list))

    def test_dispatch_fallback_uses_only_the_fixed_adobe_progid(self):
        with self.modules():
            self.client.GetActiveObject.side_effect=RuntimeError('not in ROT')
            native=Photoshop(APP,Desktop().observe())
            self.client.Dispatch.assert_called_once_with('Photoshop.Application')
            native.close()

    def test_changed_native_identity_and_stop_prevent_render(self):
        with self.modules(),tempfile.TemporaryDirectory() as directory:
            native=Photoshop(APP,Desktop().observe())
            self.com.DoJavaScript.return_value=json.dumps({**INFO,'version':'26.0'})
            with self.assertRaises(RuntimeError):native.render(DESIGN,Path(directory),'logo',threading.Event())
            self.assertFalse(any('documents.add' in call.args[0] for call in self.com.DoJavaScript.call_args_list))
            cancel=threading.Event();cancel.set();before=self.com.DoJavaScript.call_count
            with self.assertRaises(RuntimeError):native.render(DESIGN,Path(directory),'logo',cancel)
            self.assertEqual(self.com.DoJavaScript.call_count,before);native.close()


class Adapter:
    info=INFO
    calls=0
    def __init__(self,app,obs):self.closed=False
    def render(self,design,directory,name,cancel):
        type(self).calls+=1;psd(directory/'logo.psd',design);png(directory/'logo.png',design)
        return observation(design)
    def close(self):self.closed=True


class LogoTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.catalog=Catalog(self.root);self.catalog.sync(snapshot([APP]))
        self.cloud=Mock();self.cloud.request.return_value=reply(DESIGN)
        self.approve=Mock(return_value=True);Adapter.calls=0
        self.director=TaskDirector(self.catalog,self.cloud,self.approve,lambda text:None,self.root,resolve=lambda a,c:Desktop())

    def test_durable_verified_exports_survive_restart_without_a_second_render(self):
        jobs=Jobs(self.root)
        try:
            identity=jobs.submit(BRIEF,autonomous=True)
            checkpoint=jobs.claim(identity);self.director.checkpoint=checkpoint
            first=run_logo(self.director,BRIEF,adapter=Adapter)
            self.assertEqual(first['outcome'],'artifacts_verified')
            self.assertEqual(len(jobs.get(identity)['verified']),1)
            # Abrupt loss after export checkpoint but before job completion.
            with jobs.db:
                jobs.db.execute('UPDATE jobs SET lease=0 WHERE id=?',(identity,))
                jobs.db.execute('UPDATE desktop_lease SET expires=0')
            self.director.checkpoint=jobs.claim(identity)
            second=run_logo(self.director,BRIEF,adapter=Adapter)
            self.assertEqual(second['verified_results'],first['verified_results'])
            self.assertEqual(Adapter.calls,1)
            self.assertEqual(jobs.settle(self.director.checkpoint,second)['status'],'completed')
        finally:
            jobs.close()

    def test_failed_native_render_is_not_repeated_by_durable_recovery(self):
        jobs=Jobs(self.root)
        try:
            identity=jobs.submit(BRIEF,autonomous=True)
            self.director.checkpoint=jobs.claim(identity)
            class Interrupted(Adapter):
                calls=0
                def render(self,*args):
                    type(self).calls+=1
                    raise RuntimeError('Lost COM connection after render dispatch')
            result=run_logo(self.director,BRIEF,adapter=Interrupted)
            self.assertEqual(Interrupted.calls,1)
            self.assertEqual(jobs.settle(self.director.checkpoint,result)['status'],'needs_review')
            jobs.resume();self.assertIsNone(jobs.claim(identity))
        finally:
            jobs.close()

    def test_deleted_checkpointed_exports_cannot_be_claimed_complete_or_rendered_again(self):
        jobs=Jobs(self.root)
        try:
            identity=jobs.submit(BRIEF,autonomous=True)
            self.director.checkpoint=jobs.claim(identity)
            result=run_logo(self.director,BRIEF,adapter=Adapter)
            Path(result['verified_results'][0]['path']).unlink()
            repeated=run_logo(self.director,BRIEF,adapter=Adapter)
            self.assertEqual(repeated['outcome'],'blocked')
            self.assertEqual(Adapter.calls,1)
        finally:
            jobs.close()
    def tearDown(self):self.catalog.close();self.temp.cleanup()

    def test_complete_goal_checks_files_then_reuses_recipe_without_cloud_and_invalidates_after_update(self):
        with patch('app_agent.native_tasks.Photoshop',Adapter):
            # Inject adapter at entry, keeping the real planner, verifier and catalog.
            first=run_logo(self.director,BRIEF,adapter=Adapter)
            self.assertEqual(first['outcome'],'artifacts_verified')
            second=run_logo(self.director,BRIEF,adapter=Adapter)
            self.assertEqual(second['outcome'],'artifacts_verified')
            self.assertNotEqual(first['verified_results'][0]['path'],second['verified_results'][0]['path'])
            self.assertEqual(self.cloud.request.call_count,1);self.assertEqual(Adapter.calls,2)
            self.assertEqual(self.catalog.workflows(APP['id'],1),[])
            self.assertEqual(machine_report(self.catalog)['summary']['with_verified_artifact_workflows'],1)
            self.catalog.sync(snapshot([{**APP,'version':'26.0'}]))
            self.assertIsNone(self.catalog.artifact_recipe(APP['id'],2,BRIEF))
            self.assertEqual(machine_report(self.catalog)['summary']['with_verified_artifact_workflows'],0)
            self.assertEqual(run_logo(self.director,BRIEF,adapter=Adapter)['outcome'],'artifacts_verified')
            self.assertEqual(self.cloud.request.call_count,2)

    def test_denial_or_stop_never_creates_files_or_calls_model(self):
        self.approve.return_value=False
        self.assertEqual(run_logo(self.director,BRIEF,adapter=Adapter)['outcome'],'blocked')
        self.director.cancel.set()
        self.assertEqual(run_logo(self.director,BRIEF,adapter=Adapter)['outcome'],'cancelled')
        self.cloud.request.assert_not_called();self.assertEqual(Adapter.calls,0)
        self.assertFalse((self.root/'outputs').exists())

    def test_extra_delivery_existing_logo_and_custom_destination_are_not_silently_discarded(self):
        for task in (BRIEF+' And email it to me.', 'I want to edit the existing logo in Photoshop.',
                     BRIEF+' Export to Desktop.', BRIEF+' Save to D:\\logos\\brand.png.'):
            self.assertEqual(run_logo(self.director,task,adapter=Adapter)['outcome'],'blocked')
        self.cloud.request.assert_not_called();self.assertEqual(Adapter.calls,0)

    def test_false_completion_is_repaired_once_then_retained_as_failure_without_recipe(self):
        class Broken(Adapter):
            def render(self,design,directory,name,cancel):return observation(design)
        result=run_logo(self.director,BRIEF,adapter=Broken)
        self.assertEqual(result['outcome'],'verification_failed');self.assertEqual(len(result['steps']),2)
        self.assertIsNone(self.catalog.artifact_recipe(APP['id'],1,BRIEF))
        self.assertEqual(self.cloud.request.call_count,2)
        self.assertIn('Artifact missing',result['steps'][0]['error'])

    def test_cancel_during_native_render_and_generation_change_prevent_certification(self):
        owner=self
        class Cancelled(Adapter):
            def render(self,design,directory,name,cancel):
                result=super().render(design,directory,name,cancel);cancel.set();return result
        self.assertEqual(run_logo(self.director,BRIEF,adapter=Cancelled)['outcome'],'cancelled')
        self.assertIsNone(self.catalog.artifact_recipe(APP['id'],1,BRIEF))
        self.director.cancel.clear()
        class Updated(Adapter):
            def render(self,design,directory,name,cancel):
                result=super().render(design,directory,name,cancel)
                owner.catalog.sync(snapshot([{**APP,'version':'26.0'}]));return result
        self.assertEqual(run_logo(self.director,BRIEF,adapter=Updated)['outcome'],'blocked')
        self.assertIsNone(self.catalog.artifact_recipe(APP['id'],1,BRIEF))

    def test_director_routes_creative_goal_and_preserves_text_entry_and_ui_workflow_semantics(self):
        with patch('app_agent.native_tasks.run_logo',return_value={'outcome':'artifacts_verified'}) as native:
            self.assertEqual(self.director.run(BRIEF)['outcome'],'artifacts_verified')
            native.assert_called_once_with(self.director,BRIEF)

    def test_script_data_escapes_injection_as_literal_text_and_refuses_arbitrary_fields(self):
        design=copy.deepcopy(DESIGN);design['texts'][0]['text']='ACME "); app.documents.removeAll(); //'
        script=render_script(design,self.root,'new logo',['ArialMT'])
        self.assertIn('ACME \\"); app.documents.removeAll(); //',script)
        self.assertNotIn('eval(',script)
        with self.assertRaises(ValueError):render_script({**design,'script':'evil'},self.root,'new logo',['ArialMT'])
