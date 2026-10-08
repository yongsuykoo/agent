"""Optional, credential-free native tests creating only fresh Office files."""
from pathlib import Path
import uuid
from .catalog import Catalog
from .office import Office
from .office_artifacts import verify_workbook,verify_document
from .task_director import resolve_window
from .tool_broker import select_office

WORKBOOK={'sheets':[{'name':'AgentTest','rows':[
    [{'kind':'text','value':'Item'},{'kind':'text','value':'Amount'}],
    [{'kind':'text','value':'Paper'},{'kind':'number','value':12.5}],
    [{'kind':'text','value':'Ink'},{'kind':'number','value':7.5}],
    [{'kind':'text','value':'Total'},{'kind':'formula','value':'=SUM(B2:B3)'}]],
    'formats':['general','currency'],'chart':{'title':'Test costs','kind':'column','categories':'A2:A3','values':'B2:B3'}}]}
DOCUMENT={'title':'App Agent native test','paragraphs':['This is a disposable test document.','Literal text: =2+2 and Unicode 你好.'],
          'table':[['Item','Amount'],['Paper','12.5'],['Ink','7.5']]}


def office_smoke(data_dir,run_dir,family,cancel,adapter=Office,resolve=resolve_window):
    from .self_test import SkipCheck
    catalog=Catalog(data_dir);native=None
    try:
        app=select_office(catalog.apps(),family)
        if app is None:raise SkipCheck('No single installed '+family+' edition was identified; no Office operation attempted.')
        def guard():
            current=catalog.get(app['id'])
            if cancel.is_set() or not current or not current.get('present',True) or current['generation']!=app['generation']:
                raise RuntimeError('Native Office test cancelled or installation changed.')
        guard();desktop=resolve(app,cancel);native=adapter(app,desktop.observe(),family)
        folder=Path(run_dir)/('office-test-'+uuid.uuid4().hex)
        if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [folder,*folder.parents]):
            raise ValueError('Office test folder cannot traverse links or junctions.')
        folder.mkdir(parents=True,exist_ok=False)
        path=folder/('workbook.xlsx' if family=='excel' else 'document.docx')
        plan=WORKBOOK if family=='excel' else DOCUMENT
        native.render(plan,path,guard);guard()
        proof=(verify_workbook if family=='excel' else verify_document)(path,plan)
        return {'native_identity':native.info,'verification':proof,
                'note':'A fresh test document remains open; existing user documents were not edited. No cloud calls.'}
    finally:
        if native is not None:native.close()
        catalog.close()
