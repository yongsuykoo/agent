"""Real file/SQLite validation; native Office adapters are simulated on Linux."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock,patch
from xml.etree import ElementTree as ET

from app_agent.catalog import Catalog
from app_agent.jobs import Jobs
from app_agent.office import Office,validate_identity
from app_agent.office_plan import FormulaEngine,validate_workbook,validate_document,plan_office
from app_agent.office_artifacts import verify_workbook,verify_document,same_number,S,W,C,P
from app_agent.office_tasks import run_office
from app_agent.tool_broker import choose_tool,select_office
from app_agent.task_director import TaskDirector
from office_fixtures import WORKBOOK,DOCUMENT,workbook_parts,document_parts,save,xml
from test_catalog import snapshot

APP={'id':'start:excel','name':'Microsoft Excel','version':'16.0','source':'start_menu','launch_executable':r'C:\Office\EXCEL.EXE','aliases':['Excel']}
WORD={**APP,'id':'start:word','name':'Microsoft Word','launch_executable':r'C:\Office\WINWORD.EXE','aliases':['Word']}
INFO={'name':'excel','version':'16.0','path':r'C:\Office'}
TASK='Create an Excel workbook listing Paper 12.5 and Ink 7.5 with a total and a column chart titled Costs.'
OBS={'window':'Excel','window_handle':10,'process_id':20,'controls':[]}
def reply(plan):return {'output':[{'content':[{'type':'output_text','text':json.dumps(plan)}]}]}


class PlanTests(unittest.TestCase):
    def test_formula_dependencies_and_supported_aggregates(self):
        rows=[[{'kind':'number','value':2},{'kind':'formula','value':'=A1*3'}],
              [{'kind':'formula','value':'=SUM(A1:B1)+AVERAGE(A1:B1)+MIN(A1:B1)+MAX(A1:B1)+COUNT(A1:B1)'},{'kind':'blank','value':None}]]
        self.assertEqual(FormulaEngine(rows).value('A2'),Decimal(22))
        self.assertEqual(validate_workbook(copy.deepcopy(WORKBOOK)),WORKBOOK)

    def test_formula_code_links_cycles_and_bad_values_are_rejected(self):
        for formula in ('=WEBSERVICE("http://bad")','=HYPERLINK(A1)','=A1**2','=__import__(1)','=A999','=B4','=1/0','=R(A1,A2)','=Sheet2!A1','=SUM(A1:Z200)'):
            plan=copy.deepcopy(WORKBOOK);plan['sheets'][0]['rows'][3][1]['value']=formula
            with self.subTest(formula=formula),self.assertRaises(ValueError):validate_workbook(plan)
        for value in (True,float('nan'),float('inf'),1e13,1.1234567890123456):
            plan=copy.deepcopy(WORKBOOK);plan['sheets'][0]['rows'][1][1]['value']=value
            with self.subTest(value=value),self.assertRaises(ValueError):validate_workbook(plan)

    def test_literal_goal_constraints_and_plan_bounds(self):
        plan=copy.deepcopy(WORKBOOK)
        with self.assertRaises(ValueError):validate_workbook(plan,'Create Excel A1 = 33')
        with self.assertRaises(ValueError):validate_document(DOCUMENT,'Create Word titled "Wrong title"')
        for alter in (lambda p:p.update(script='bad'),lambda p:p['sheets'][0].update(name='../bad'),lambda p:p['sheets'][0]['rows'].append([]),lambda p:p['sheets'][0]['chart'].update(values='B1:B3')):
            plan=copy.deepcopy(WORKBOOK);alter(plan)
            with self.assertRaises(ValueError):validate_workbook(plan)
        with self.assertRaises(ValueError):validate_document({**DOCUMENT,'paragraphs':['one\ntwo']})

    def test_plan_repairs_before_execution_and_stop_prevents_api_calls(self):
        cloud=Mock();cloud.request.side_effect=[reply({'sheets':[]}),reply(WORKBOOK)]
        self.assertEqual(plan_office(TASK,'excel',cloud,threading.Event()),WORKBOOK)
        self.assertEqual(cloud.request.call_count,2)
        self.assertIn('worksheets',json.loads(cloud.request.call_args.kwargs['input'])['validation_feedback'])
        cancel=threading.Event();cancel.set()
        with self.assertRaises(RuntimeError):plan_office(TASK,'excel',cloud,cancel)
        self.assertEqual(cloud.request.call_count,2)


class ArtifactTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.xlsx'
    def tearDown(self):self.temp.cleanup()
    def test_actual_workbook_bytes_formula_cache_format_and_chart(self):
        save(self.path,workbook_parts())
        result=verify_workbook(self.path,WORKBOOK)
        self.assertEqual(result['status'],'artifact_verified');self.assertEqual(result['sheets'][0]['formulas_checked'],1)
        self.assertTrue(result['sheets'][0]['chart_checked']);self.assertEqual(len(result['files'][0]['sha256']),64)
    def test_cell_and_formula_cache_lies_cannot_pass(self):
        self.assertFalse(same_number(0,Decimal('1e-20')))
        self.assertFalse(same_number('1000000000001',Decimal('1000000000000')))
        self.assertTrue(same_number(0.1+0.2,Decimal('0.3')))
        for ref,field,value in [('B2','v','999'),('B4','v','999'),('B4','f','SUM(B2:B2)')]:
            parts=workbook_parts();root=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
            root.find(f'.//{{{S}}}c[@r="{ref}"]/{{{S}}}{field}').text=value
            parts['xl/worksheets/sheet1.xml']=xml(root);save(self.path,parts)
            with self.subTest(ref=ref,field=field),self.assertRaises(ValueError):verify_workbook(self.path,WORKBOOK)
    def test_literal_formula_like_text_remains_literal(self):
        plan=copy.deepcopy(WORKBOOK);plan['sheets'][0]['rows'][1][0]['value']='=2+2'
        save(self.path,workbook_parts(plan));verify_workbook(self.path,plan)
        parts=workbook_parts(plan);root=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
        cell=root.find(f'.//{{{S}}}c[@r="A2"]');ET.SubElement(cell,'{'+S+'}f').text='2+2'
        parts['xl/worksheets/sheet1.xml']=xml(root);save(self.path,parts)
        with self.assertRaises(ValueError):verify_workbook(self.path,plan)
    def test_corrupt_chart_title_source_cache_and_format_are_rejected(self):
        for kind in ('title','source','cache','format'):
            parts=workbook_parts()
            if kind=='format':
                root=ET.fromstring(parts['xl/worksheets/sheet1.xml']);root.find(f'.//{{{S}}}c[@r="B2"]').set('s','0');part='xl/worksheets/sheet1.xml'
            else:
                part='xl/charts/chart1.xml';root=ET.fromstring(parts[part])
                tag={'title':'{http://schemas.openxmlformats.org/drawingml/2006/main}t','source':'{'+C+'}f','cache':'{'+C+'}v'}[kind]
                root.find('.//'+tag).text='wrong'
            parts[part]=xml(root);save(self.path,parts)
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_workbook(self.path,WORKBOOK)
    def test_multiple_sheets_line_chart_and_blank_cells(self):
        plan=copy.deepcopy(WORKBOOK);sheet=copy.deepcopy(plan['sheets'][0]);sheet['name']='Second';sheet['chart']['kind']='line';sheet['rows'][3][0]={'kind':'blank','value':None};plan['sheets'].append(sheet)
        save(self.path,workbook_parts(plan));self.assertEqual(len(verify_workbook(self.path,plan)['sheets']),2)
    def test_missing_formula_cache_is_not_treated_as_verified(self):
        parts=workbook_parts();root=ET.fromstring(parts['xl/worksheets/sheet1.xml']);cell=root.find(f'.//{{{S}}}c[@r="B4"]');cell.remove(cell.find('{'+S+'}v'))
        parts['xl/worksheets/sheet1.xml']=xml(root);save(self.path,parts)
        with self.assertRaises(ValueError):verify_workbook(self.path,WORKBOOK)
    def test_macro_external_relationship_traversal_and_entities_are_rejected(self):
        for name,raw in [('xl/vbaProject.bin',b'bad'),('../outside.xml',b'bad'),('xl/_rels/bad.rels',b'<Relationships><Relationship TargetMode="External"/></Relationships>'),('xl/workbook.xml',b'<!DOCTYPE root><root/>')]:
            parts=workbook_parts();parts[name]=raw;save(self.path,parts)
            with self.subTest(name=name),self.assertRaises(ValueError):verify_workbook(self.path,WORKBOOK)
    def test_document_text_and_table_are_read_from_saved_bytes(self):
        path=self.path.with_suffix('.docx');save(path,document_parts())
        result=verify_document(path,DOCUMENT);self.assertEqual(result['paragraphs_checked'],3);self.assertEqual(result['table_cells_checked'],4)
        parts=document_parts();root=ET.fromstring(parts['word/document.xml']);root.find(f'.//{{{W}}}tbl/.//{{{W}}}t').text='Wrong'
        parts['word/document.xml']=xml(root);save(path,parts)
        with self.assertRaises(ValueError):verify_document(path,DOCUMENT)
    def test_document_fields_and_hidden_content_do_not_pass(self):
        path=self.path.with_suffix('.docx')
        for tag in ('instrText','fldSimple','drawing','hyperlink','vanish','altChunk'):
            parts=document_parts();root=ET.fromstring(parts['word/document.xml']);ET.SubElement(root.find(f'{{{W}}}body/{{{W}}}p'),'{'+W+'}'+tag)
            parts['word/document.xml']=xml(root);save(path,parts)
            with self.subTest(tag=tag),self.assertRaises(ValueError):verify_document(path,DOCUMENT)
    def test_output_link_is_rejected(self):
        original=self.path.with_name('real.xlsx');save(original,workbook_parts());self.path.symlink_to(original)
        with self.assertRaises(ValueError):verify_workbook(self.path,WORKBOOK)
    def test_package_document_type_and_executable_mime_cannot_be_faked(self):
        for kind in ('missing','macro','wrong_root'):
            parts=workbook_parts()
            if kind=='missing':del parts['[Content_Types].xml']
            elif kind=='macro':parts['[Content_Types].xml']=parts['[Content_Types].xml'].replace(b'spreadsheetml.sheet.main+xml',b'ms-excel.sheet.macroEnabled.main+xml')
            else:parts['_rels/.rels']=parts['_rels/.rels'].replace(b'xl/workbook.xml',b'xl/styles.xml')
            save(self.path,parts)
            with self.subTest(kind=kind),self.assertRaises((ValueError,KeyError)):verify_workbook(self.path,WORKBOOK)


class BrokerTests(unittest.TestCase):
    def test_office_creation_prefers_fixed_tools_and_selected_app(self):
        self.assertEqual(choose_tool(TASK,[APP,WORD])['family'],'excel')
        self.assertEqual(choose_tool('Write a Word document titled "Brief".',[APP,WORD])['family'],'word')
        self.assertEqual(choose_tool(TASK,[APP,WORD],WORD)['kind'],'desktop')
    def test_compound_delivery_other_app_and_literal_text_stay_on_desktop(self):
        for task in (TASK+' and email it.',TASK+' in D:\\output',TASK+' using LibreOffice','Replace the document text with exactly: Create an Excel workbook','Create an Excel spreadsheet with a photo','Edit the existing Excel workbook'):
            with self.subTest(task=task):self.assertEqual(choose_tool(task,[APP,{'id':'libre','name':'LibreOffice'}])['kind'],'desktop')
    def test_duplicate_registrations_are_coalesced_and_editions_remain_ambiguous(self):
        self.assertIsNotNone(select_office([APP,{**APP,'id':'registry:excel'}],'excel'))
        self.assertIsNone(select_office([APP,{**APP,'id':'older','launch_executable':r'C:\Old\EXCEL.EXE'}],'excel'))


class SimulatedOffice:
    renders=0
    def __init__(self,app,observation,family):self.family=family;self.info={**INFO,'name':family}
    def render(self,plan,path,guard):
        guard();type(self).renders+=1;save(path,workbook_parts(plan) if self.family=='excel' else document_parts(plan));guard()
    def close(self):pass


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.catalog=Catalog(self.temp.name);self.catalog.sync(snapshot([APP,WORD]));self.cloud=Mock();self.cloud.request.return_value=reply(WORKBOOK)
        self.desktop=Mock();self.desktop.observe.return_value=OBS;self.approve=Mock(return_value=True)
        self.director=TaskDirector(self.catalog,self.cloud,self.approve,lambda _:None,self.temp.name,resolve=lambda app,cancel:self.desktop)
        self.app=self.catalog.get(APP['id']);self.route={'kind':'office','family':'excel','app':self.app};SimulatedOffice.renders=0
    def tearDown(self):self.catalog.close();self.temp.cleanup()
    def run_goal(self):return run_office(self.director,TASK,self.route,adapter=SimulatedOffice)
    def test_success_retains_verified_recipe_and_reuses_without_api(self):
        result=self.run_goal();self.assertEqual(result['outcome'],'artifacts_verified');self.assertEqual(self.cloud.request.call_count,1)
        second=self.run_goal();self.assertEqual(second['outcome'],'artifacts_verified');self.assertEqual(self.cloud.request.call_count,1)
        self.assertNotEqual(result['verified_results'][0]['path'],second['verified_results'][0]['path']);self.assertEqual(SimulatedOffice.renders,2)
    def test_false_native_save_cannot_become_a_verified_recipe(self):
        class Liar(SimulatedOffice):
            def render(self,plan,path,guard):path.write_bytes(b'not an xlsx')
        result=run_office(self.director,TASK,self.route,adapter=Liar)
        self.assertEqual(result['outcome'],'verification_failed');self.assertIsNone(self.catalog.artifact_recipe(self.app['id'],self.app['generation'],TASK))
    def test_rejection_and_stop_make_no_native_write(self):
        self.approve.return_value=False;self.assertEqual(self.run_goal()['outcome'],'blocked');self.assertEqual(SimulatedOffice.renders,0)
        self.director.cancel.set();self.assertEqual(self.run_goal()['outcome'],'cancelled');self.assertEqual(SimulatedOffice.renders,0)
    def test_unavailable_com_and_unrepresentable_plan_can_fall_back_before_effect(self):
        unavailable=Mock(side_effect=RuntimeError('No active interface'))
        self.assertIsNone(run_office(self.director,TASK,self.route,adapter=unavailable));self.cloud.request.assert_not_called()
        self.cloud.request.return_value=reply({'sheets':[]});self.assertIsNone(self.run_goal());self.assertEqual(SimulatedOffice.renders,0)
    def test_updated_generation_invalidates_cached_recipe(self):
        self.run_goal();self.catalog.sync(snapshot([{**APP,'version':'16.1'},WORD]));self.route['app']=self.catalog.get(APP['id']);self.run_goal()
        self.assertEqual(self.cloud.request.call_count,2)
    def test_director_dispatches_to_native_broker(self):
        with patch('app_agent.office_tasks.run_office',return_value={'outcome':'artifacts_verified'}) as run:
            self.assertEqual(self.director.run(TASK)['outcome'],'artifacts_verified');self.assertEqual(run.call_args.args[2]['family'],'excel')
    def test_durable_resume_rechecks_file_without_rendering_again(self):
        jobs=Jobs(self.temp.name);identity=jobs.submit(TASK,autonomous=True);lease=jobs.claim(identity);self.director.checkpoint=lease
        try:
            first=self.run_goal();self.assertEqual(len(jobs.get(identity)['verified']),1)
            second=self.run_goal();self.assertEqual(second['verified_results'],first['verified_results']);self.assertEqual(SimulatedOffice.renders,1)
            self.assertEqual(jobs.settle(lease,second)['status'],'completed')
        finally:jobs.close()
    def test_missing_saved_file_and_dirty_effect_stop_automatic_recreation(self):
        jobs=Jobs(self.temp.name);identity=jobs.submit(TASK);lease=jobs.claim(identity);self.director.checkpoint=lease
        try:
            first=self.run_goal();Path(first['verified_results'][0]['path']).unlink();second=self.run_goal()
            self.assertEqual(second['outcome'],'blocked');self.assertEqual(SimulatedOffice.renders,1);self.assertNotEqual(jobs.settle(lease,second)['status'],'completed')
        finally:jobs.close()
    def test_uncertain_native_failure_remains_needs_review(self):
        jobs=Jobs(self.temp.name);identity=jobs.submit(TASK);lease=jobs.claim(identity);self.director.checkpoint=lease
        class Crash(SimulatedOffice):
            def render(self,plan,path,guard):
                guard();raise RuntimeError('Native write may have happened')
        try:
            result=run_office(self.director,TASK,self.route,adapter=Crash)
            self.assertEqual(jobs.settle(lease,result)['status'],'needs_review');self.assertFalse(jobs.ready())
        finally:jobs.close()


class NativeBindingTests(unittest.TestCase):
    def modules(self,application,pid=20):
        com=types.SimpleNamespace(COINIT_MULTITHREADED=0,CoInitializeEx=Mock(),CoUninitialize=Mock())
        client=types.SimpleNamespace(GetActiveObject=Mock(return_value=application))
        package=types.ModuleType('win32com');package.client=client
        process=types.SimpleNamespace(GetWindowThreadProcessId=Mock(return_value=(1,pid)))
        return {'pythoncom':com,'win32com':package,'win32com.client':client,'win32process':process},com,client
    def application(self,family='excel'):
        app=Mock();app.Version='16.0';app.Path=r'C:\Office';app.Hwnd=10;app.ActiveWindow.Hwnd=11;return app
    def test_readonly_binding_checks_pid_installation_and_balances_com(self):
        app=self.application();modules,com,client=self.modules(app)
        with patch.dict('sys.modules',modules):
            native=Office(APP,OBS,'excel');native.close()
        client.GetActiveObject.assert_called_once_with('Excel.Application');com.CoUninitialize.assert_called_once();app.Workbooks.Add.assert_not_called()
        for pid,path in ((999,r'C:\Office'),(20,r'C:\Other')):
            app=self.application();app.Path=path;modules,com,client=self.modules(app,pid)
            with patch.dict('sys.modules',modules),self.assertRaises(ValueError):Office(APP,OBS,'excel')
            com.CoUninitialize.assert_called_once()
    def test_word_uses_active_window_hwnd_and_macro_free_save(self):
        app=self.application('word');modules,com,client=self.modules(app)
        with tempfile.TemporaryDirectory() as directory,patch.dict('sys.modules',modules):
            native=Office(WORD,OBS,'word');document=app.Documents.Add.return_value;document.Content.End=100
            native.render(DOCUMENT,Path(directory)/'document.docx',lambda:None);native.close()
        modules['win32process'].GetWindowThreadProcessId.assert_any_call(11)
        document.SaveAs2.assert_called_once();self.assertEqual(document.SaveAs2.call_args.kwargs['FileFormat'],12)
        app.Quit.assert_not_called();document.Close.assert_not_called()
    def test_excel_batches_cells_and_uses_only_fixed_formula_chart_save_methods(self):
        app=self.application();modules,com,client=self.modules(app)
        with tempfile.TemporaryDirectory() as directory,patch.dict('sys.modules',modules):
            native=Office(APP,OBS,'excel');native.render(WORKBOOK,Path(directory)/'workbook.xlsx',lambda:None);native.close()
        app.Workbooks.Add.assert_called_once_with(-4167);book=app.Workbooks.Add.return_value;sheet=book.Worksheets.return_value
        book.SaveAs.assert_called_once();self.assertEqual(book.SaveAs.call_args.kwargs['FileFormat'],51)
        self.assertIn('A1:B4',[call.args[0] for call in sheet.Range.call_args_list]);sheet.Range.return_value.Calculate.assert_called_once()
        self.assertEqual(sheet.Range.return_value.Formula,'=SUM(B2:B3)');app.Calculate.assert_not_called();app.Quit.assert_not_called();book.Close.assert_not_called()
    def test_cancelled_guard_blocks_before_document_creation(self):
        app=self.application();modules,com,client=self.modules(app)
        with tempfile.TemporaryDirectory() as directory,patch.dict('sys.modules',modules):
            native=Office(APP,OBS,'excel')
            with self.assertRaises(RuntimeError):native.render(WORKBOOK,Path(directory)/'workbook.xlsx',Mock(side_effect=RuntimeError('Stopped')))
            native.close()
        app.Workbooks.Add.assert_not_called()


class NativeCheckTests(unittest.TestCase):
    def test_optional_checks_create_verified_files_without_a_cloud_client(self):
        from app_agent.office_checks import office_smoke
        with tempfile.TemporaryDirectory() as directory:
            catalog=Catalog(directory);catalog.sync(snapshot([APP,WORD]));catalog.close()
            desktop=Mock();desktop.observe.return_value=OBS
            for family in ('excel','word'):
                result=office_smoke(directory,directory,family,threading.Event(),SimulatedOffice,lambda app,cancel:desktop)
                self.assertEqual(result['verification']['status'],'artifact_verified');self.assertTrue(Path(result['verification']['files'][0]['path']).is_file())
    def test_missing_office_is_skipped_and_cancellation_does_not_create_files(self):
        from app_agent.office_checks import office_smoke
        from app_agent.self_test import SkipCheck
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SkipCheck):office_smoke(directory,directory,'excel',threading.Event(),SimulatedOffice)
            catalog=Catalog(directory);catalog.sync(snapshot([APP]));catalog.close();cancel=threading.Event();cancel.set()
            with self.assertRaises(RuntimeError):office_smoke(directory,directory,'excel',cancel,SimulatedOffice)
            self.assertFalse(list(Path(directory).glob('office-test-*')))


if __name__=='__main__':unittest.main()
