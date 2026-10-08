"""Fixed, documented Office COM operations; models supply data, never code."""
import ntpath
import re
from pathlib import Path
from .office_plan import validate_workbook, validate_document, cell_name

FORMATS={'general':'General','decimal':'0.00','currency':'$#,##0.00','percent':'0.00%','text':'@'}


def validate_identity(app,info,family):
    if not isinstance(info,dict) or any(not isinstance(info.get(k),str) or not info[k] or len(info[k])>500 for k in ('name','version','path')):
        raise ValueError('Office native identity is incomplete.')
    if info['name']!=family:raise ValueError('Office family disagrees with the selected app.')
    expected=re.match(r'(\d+)',app.get('version',''));actual=re.match(r'(\d+)',info['version'])
    if expected and int(expected[1])<100 and (not actual or int(actual[1])!=int(expected[1])):
        raise ValueError('Active Office version differs from the installed catalog.')
    path=app.get('launch_executable','')
    if path and ntpath.dirname(path) and ntpath.normcase(ntpath.normpath(ntpath.dirname(path)))!=ntpath.normcase(ntpath.normpath(info['path'])):
        raise ValueError('Active Office installation differs from the selected executable.')
    return info


class Office:
    def __init__(self,app,observation,family):
        import pythoncom
        import win32com.client
        import win32process
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        self._pythoncom=pythoncom;self.application=None;self.family=family
        try:
            if family not in ('excel','word'):raise ValueError('Unknown Office tool.')
            # Only bind an already running app resolved by the desktop adapter.
            application=win32com.client.GetActiveObject({'excel':'Excel.Application','word':'Word.Application'}[family])
            hwnd=int(application.Hwnd if family=='excel' else application.ActiveWindow.Hwnd)
            _,pid=win32process.GetWindowThreadProcessId(hwnd)
            if pid!=observation.get('process_id'):raise ValueError('Office COM instance does not match the selected process.')
            info={'name':family,'version':str(application.Version),'path':str(application.Path)}
            validate_identity(app,info,family)
            self.application,self.info,self.pid=application,info,pid
        except BaseException:
            self.close();raise

    def close(self):
        self.application=None
        self._pythoncom.CoUninitialize()

    def render(self,plan,path,guard):
        (validate_workbook if self.family=='excel' else validate_document)(plan)
        path=Path(path)
        if path.exists() or not path.parent.is_dir() or any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [path,*path.parents]):
            raise ValueError('Office output needs a new file in an unlinked task directory.')
        if path.suffix!=('.xlsx' if self.family=='excel' else '.docx'):raise ValueError('Office output extension disagrees with the tool.')
        def current():
            guard()
            import win32process
            hwnd=int(self.application.Hwnd if self.family=='excel' else self.application.ActiveWindow.Hwnd)
            if win32process.GetWindowThreadProcessId(hwnd)[1]!=self.pid or str(self.application.Version)!=self.info['version'] or str(self.application.Path)!=self.info['path']:
                raise RuntimeError('Office process or native identity changed.')
        if self.family=='excel':self._workbook(plan,path,current)
        else:self._document(plan,path,current)
        guard()

    def _workbook(self,plan,path,guard):
        guard();book=self.application.Workbooks.Add(-4167)  # xlWBATWorksheet
        for index,design in enumerate(plan['sheets']):
            guard();sheet=book.Worksheets(1) if index==0 else book.Worksheets.Add(After=book.Worksheets(book.Worksheets.Count))
            guard();sheet.Name=design['name']
            rows=design['rows'];last=cell_name(len(rows)-1,len(rows[0])-1)
            target=sheet.Range('A1:'+last)
            # Text remains literal even when it begins with '=' or '+'.
            guard();target.NumberFormat='@'
            values=tuple(tuple(cell['value'] if cell['kind'] in ('text','number') else None for cell in row) for row in rows)
            guard();target.Value2=values
            for column,style in enumerate(design['formats'],1):
                guard();sheet.Range(cell_name(0,column-1)+':'+cell_name(len(rows)-1,column-1)).NumberFormat=FORMATS[style]
            for r,row in enumerate(rows):
                for c,cell in enumerate(row):
                    if cell['kind']=='formula':
                        guard();sheet.Range(cell_name(r,c)).Formula=cell['value']
            guard();target.Calculate()
            chart=design['chart']
            if chart:
                guard();plot=sheet.ChartObjects().Add(420,20,480,280).Chart
                guard();plot.ChartType=51 if chart['kind']=='column' else 4
                guard();series=plot.SeriesCollection().NewSeries()
                guard();series.XValues=sheet.Range(chart['categories'])
                guard();series.Values=sheet.Range(chart['values'])
                guard();series.Name=chart['title']
                guard();plot.HasTitle=True
                guard();plot.ChartTitle.Text=chart['title']
        guard();book.SaveAs(str(path),FileFormat=51)  # macro-free xlsx

    def _document(self,plan,path,guard):
        guard();document=self.application.Documents.Add()
        guard();document.Content.Text='\r'.join([plan['title'],*plan['paragraphs']])+'\r'
        guard();document.Paragraphs(1).Style=-63  # wdStyleTitle, locale independent
        if plan['table']:
            guard();position=document.Content.End-1
            guard();table=document.Tables.Add(document.Range(position,position),len(plan['table']),len(plan['table'][0]))
            for r,row in enumerate(plan['table'],1):
                for c,text in enumerate(row,1):
                    guard();table.Cell(r,c).Range.Text=text
        guard();document.SaveAs2(str(path),FileFormat=12)  # macro-free docx
