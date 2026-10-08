"""Verify saved Office bytes and formula caches independently of COM/model claims."""
from decimal import Decimal
import hashlib
import math
from pathlib import Path, PurePosixPath
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from .office_plan import FormulaEngine, cell_name, cell_range, validate_workbook, validate_document

S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
C='http://schemas.openxmlformats.org/drawingml/2006/chart'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P='http://schemas.openxmlformats.org/package/2006/relationships'
FORMATS={'general':['General'],'decimal':['0.00'],'currency':['$#,##0.00'],'percent':['0.00%'],'text':['@']}
BUILTIN={0:'General',1:'0',2:'0.00',9:'0%',10:'0.00%',49:'@'}


def safe_output(path):
    path=Path(path)
    if any(p.is_symlink() or (hasattr(p,'is_junction') and p.is_junction()) for p in [path,*path.parents]):
        raise ValueError('Office output cannot traverse a link or junction.')
    if not path.is_file() or not 0<path.stat().st_size<=10_000_000:
        raise ValueError('Office artifact is missing or exceeds its size limit.')
    return path


class Package:
    def __init__(self,path):
        self.path=safe_output(path)
        self.archive=zipfile.ZipFile(self.path)
        try:
            files=self.archive.infolist();names=[f.filename for f in files]
            if len(files)>250 or len(names)!=len(set(names)) or sum(f.file_size for f in files)>25_000_000 or any(f.file_size>10_000_000 for f in files):
                raise ValueError('Invalid Office package size or duplicate parts.')
            if any('..' in PurePosixPath(n).parts or n.startswith('/') or '\\' in n for n in names):
                raise ValueError('Invalid Office package paths.')
            if any(re.search(r'vba|activex|macrosheet|externalLink|connections|embeddings',n,re.I) for n in names):
                raise ValueError('Unexpected executable, embedded or linked Office content.')
            if self.archive.testzip():raise ValueError('Office package checksum failed.')
            self.names=set(names)
            for name in names:
                if name.endswith('.rels'):
                    root=self.xml(name)
                    for rel in root:
                        if rel.get('TargetMode','').lower()=='external':raise ValueError('External Office relationship is excluded.')
        except BaseException:
            self.archive.close();raise

    def close(self):self.archive.close()

    def xml(self,name):
        raw=self.archive.read(name)
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('XML entity declarations are excluded.')
        try:return ET.fromstring(raw)
        except ET.ParseError as error:raise ValueError('Malformed Office XML.') from error

    def relationships(self,part):
        name=posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels') if part else '_rels/.rels'
        if name not in self.names:return {}
        result={}
        for entry in self.xml(name):
            identity=entry.get('Id');target=entry.get('Target','')
            if not identity or identity in result:raise ValueError('Duplicate Office relationship.')
            resolved=posixpath.normpath(posixpath.join(posixpath.dirname(part),target)) if not target.startswith('/') else target[1:]
            if resolved.startswith('../') or resolved not in self.names:raise ValueError('Office relationship target is missing or invalid.')
            result[identity]=(resolved,entry.get('Type',''))
        return result

    def main_document(self,part,content_type):
        roots=[target for target,kind in self.relationships('').values() if kind.endswith('/officeDocument')]
        if roots!=[part]:raise ValueError('Package does not identify the expected Office document.')
        root=self.xml('[Content_Types].xml')
        types={entry.get('PartName'):entry.get('ContentType','') for entry in root if entry.tag.endswith('Override')}
        if types.get('/'+part)!=content_type or any(re.search(r'macroEnabled|vba|activex',entry.get('ContentType',''),re.I) for entry in root):
            raise ValueError('Package content types disagree with the macro-free Office format.')

    def file_record(self):
        return {'path':str(self.path),'size':self.path.stat().st_size,'sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}


def same_number(actual,expected):
    try:
        value=Decimal(str(actual));wanted=Decimal(str(expected))
        if not value.is_finite() or not wanted.is_finite():return False
        # Excel uses binary doubles and can persist a 15-significant-digit
        # decimal cache. Avoid a fixed absolute tolerance that would accept
        # zero instead of a requested small number, or whole-unit errors.
        rounded=Decimal(format(float(wanted),'.15g'))
        tolerance=Decimal(str(math.ulp(float(wanted))))*4 if wanted else Decimal('1e-15')
        return value==rounded or abs(value-wanted)<=tolerance
    except Exception:return False


def normalize_formula(formula):
    return re.sub(r'\s+','',formula.lstrip('=')).upper()


def verify_workbook(path,plan):
    validate_workbook(plan)
    package=Package(path)
    try:
        package.main_document('xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
        workbook=package.xml('xl/workbook.xml');relationships=package.relationships('xl/workbook.xml')
        sheets=workbook.findall(f'{{{S}}}sheets/{{{S}}}sheet')
        if [s.get('name') for s in sheets]!=[s['name'] for s in plan['sheets']]:raise ValueError('Saved worksheet names/order disagree with the plan.')
        if any(s.get('state','visible')!='visible' for s in sheets):raise ValueError('Unexpected hidden worksheet.')
        strings=[]
        if 'xl/sharedStrings.xml' in package.names:
            for item in package.xml('xl/sharedStrings.xml').findall(f'{{{S}}}si'):
                strings.append(''.join(t.text or '' for t in item.findall(f'.//{{{S}}}t')))
        styles=['General']
        if 'xl/styles.xml' in package.names:
            style_root=package.xml('xl/styles.xml')
            formats={**BUILTIN,**{int(n.get('numFmtId')):n.get('formatCode') for n in style_root.findall(f'{{{S}}}numFmts/{{{S}}}numFmt')}}
            styles=[formats.get(int(x.get('numFmtId','0')),'unsupported') for x in style_root.findall(f'{{{S}}}cellXfs/{{{S}}}xf')]
        verified=[]
        for sheet,design in zip(sheets,plan['sheets']):
            part,kind=relationships[sheet.get(f'{{{R}}}id')]
            if not kind.endswith('/worksheet'):raise ValueError('Worksheet relationship has the wrong type.')
            root=package.xml(part);actual={};cell_styles={};engine=FormulaEngine(design['rows'])
            for cell in root.findall(f'{{{S}}}sheetData/{{{S}}}row/{{{S}}}c'):
                ref=cell.get('r')
                if not ref or ref in actual:raise ValueError('Duplicate or missing cell reference.')
                t=cell.get('t','n');value=cell.find(f'{{{S}}}v');formula=cell.find(f'{{{S}}}f')
                text=value.text if value is not None else None
                if t=='s':value=strings[int(text)] if text is not None else ''
                elif t=='inlineStr':value=''.join(t.text or '' for t in cell.findall(f'{{{S}}}is/.//{{{S}}}t'))
                elif t=='str':value=text or ''
                elif t=='n':value=Decimal(text) if text is not None else None
                else:raise ValueError('Saved workbook contains an unexpected cell type/error.')
                actual[ref]=(value,formula.text if formula is not None else None)
                index=int(cell.get('s','0'))
                if not 0<=index<len(styles):raise ValueError('Cell style is missing.')
                cell_styles[ref]=styles[index]
            expected_refs=set()
            for r,row in enumerate(design['rows']):
                for c,cell in enumerate(row):
                    ref=cell_name(r,c);expected_refs.add(ref)
                    value,formula=actual.get(ref,(None,None));expected=engine.value(ref)
                    if cell['kind']=='formula':
                        if formula is None or normalize_formula(formula)!=normalize_formula(cell['value']):raise ValueError('Saved formula changed: '+ref)
                    elif formula is not None:raise ValueError('A literal cell became a formula: '+ref)
                    if isinstance(expected,Decimal):
                        if not isinstance(value,Decimal) or not same_number(value,expected):raise ValueError('Saved numeric value/formula cache disagrees with independent calculation: '+ref)
                    elif value!=expected and not (expected is None and value==''):
                        raise ValueError('Saved literal cell disagrees with the plan: '+ref)
                    if cell['kind']!='blank' and cell_styles.get(ref,'General') not in FORMATS[design['formats'][c]]:
                        raise ValueError('Saved column format disagrees with the plan: '+ref)
            if any(ref not in expected_refs and (value is not None or formula is not None) for ref,(value,formula) in actual.items()):
                raise ValueError('Unexpected data outside planned cells.')
            chart=verify_chart(package,part,root,design,engine)
            verified.append({'name':design['name'],'cells_checked':len(expected_refs),
                'formulas_checked':sum(c['kind']=='formula' for row in design['rows'] for c in row),'chart_checked':chart})
        return {'status':'artifact_verified','files':[package.file_record()],'sheets':verified,
                'scope':'Saved cell data, independent arithmetic, formats and chart source/cache; not a semantic proof of unprovided data.'}
    finally:package.close()


def verify_chart(package,part,worksheet,design,engine):
    drawings=worksheet.findall(f'{{{S}}}drawing');planned=design['chart']
    if planned is None:
        if drawings:raise ValueError('Unexpected worksheet drawing/chart.')
        return False
    if len(drawings)!=1:raise ValueError('Planned chart drawing is absent or ambiguous.')
    rels=package.relationships(part);drawing_part,kind=rels[drawings[0].get(f'{{{R}}}id')]
    if not kind.endswith('/drawing'):raise ValueError('Wrong drawing relationship.')
    drawing=package.xml(drawing_part);charts=drawing.findall(f'.//{{{C}}}chart')
    if len(charts)!=1:raise ValueError('Planned chart is absent or ambiguous.')
    drawing_namespace='http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing'
    if any(drawing.findall('.//{'+drawing_namespace+'}'+tag) for tag in ('pic','sp','grpSp')):
        raise ValueError('Unexpected additional worksheet artwork.')
    chart_part,kind=package.relationships(drawing_part)[charts[0].get(f'{{{R}}}id')]
    if not kind.endswith('/chart'):raise ValueError('Wrong chart relationship.')
    root=package.xml(chart_part)
    title=''.join(t.text or '' for t in root.findall(f'{{{C}}}chart/{{{C}}}title/.//{{{A}}}t'))
    if title!=planned['title']:raise ValueError('Chart title changed.')
    tag='barChart' if planned['kind']=='column' else 'lineChart'
    plots=root.findall(f'{{{C}}}chart/{{{C}}}plotArea/{{{C}}}{tag}')
    if len(plots)!=1:raise ValueError('Chart type changed.')
    all_plots=[item for area in root.findall(f'{{{C}}}chart/{{{C}}}plotArea') for item in area if item.tag.endswith('Chart')]
    if all_plots!=plots:raise ValueError('Unexpected additional chart plot.')
    if tag=='barChart' and (plots[0].find(f'{{{C}}}barDir') is None or plots[0].find(f'{{{C}}}barDir').get('val')!='col'):
        raise ValueError('Expected a column chart.')
    series=plots[0].findall(f'{{{C}}}ser')
    if len(series)!=1:raise ValueError('Unexpected chart series.')
    for field,ref in [('cat',planned['categories']),('val',planned['values'])]:
        branch=series[0].find(f'{{{C}}}{field}')
        if branch is None:raise ValueError('Chart source is missing.')
        formula=branch.find(f'.//{{{C}}}f')
        wanted=design['name']+'!'+ref
        if formula is None or (formula.text or '').replace("'",'').replace('$','')!=wanted:raise ValueError('Chart source range changed.')
        points=branch.findall(f'.//{{{C}}}pt')
        values={int(pt.get('idx')):pt.find(f'{{{C}}}v').text for pt in points}
        if len(values)!=len(points):raise ValueError('Duplicate chart cache indices.')
        expected=[engine.value(cell_name(r,c)) for r,c in cell_range(ref,len(design['rows']),len(design['rows'][0]))]
        if set(values)!=set(range(len(expected))):raise ValueError('Chart cache is incomplete.')
        for index,value in enumerate(expected):
            if (isinstance(value,Decimal) and not same_number(values[index],value)) or (not isinstance(value,Decimal) and values[index]!=(value or '')):
                raise ValueError('Chart cache disagrees with its source data.')
    return True


def verify_document(path,plan):
    validate_document(plan)
    package=Package(path)
    try:
        package.main_document('word/document.xml','application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml')
        root=package.xml('word/document.xml');body=root.find(f'{{{W}}}body')
        if body is None:raise ValueError('Word document body is missing.')
        if any(body.findall(f'.//{{{W}}}'+tag) for tag in ('instrText','fldSimple','altChunk','drawing','object','pict','hyperlink','del','ins','vanish')):
            raise ValueError('Unexpected Word fields or imported content.')
        if any(child.tag not in {f'{{{W}}}p',f'{{{W}}}tbl',f'{{{W}}}sectPr'} for child in body):
            raise ValueError('Unexpected Word body content.')
        paragraphs=body.findall(f'{{{W}}}p')
        texts=[''.join(t.text or '' for t in p.findall(f'.//{{{W}}}t')) for p in paragraphs]
        while texts and texts[-1]=='':texts.pop()
        if texts!=[plan['title'],*plan['paragraphs']]:raise ValueError('Saved document text changed or omitted requested content.')
        tables=body.findall(f'{{{W}}}tbl')
        if len(tables)!=(1 if plan['table'] else 0):raise ValueError('Saved table count disagrees with the plan.')
        if tables:
            rows=[[''.join(t.text or '' for t in cell.findall(f'.//{{{W}}}t')) for cell in row.findall(f'{{{W}}}tc')]
                  for row in tables[0].findall(f'{{{W}}}tr')]
            if rows!=plan['table']:raise ValueError('Saved table data changed.')
        return {'status':'artifact_verified','files':[package.file_record()],
                'paragraphs_checked':len(plan['paragraphs'])+1,'table_cells_checked':sum(map(len,plan['table'])),
                'scope':'Saved literal document/table content; typography and print appearance are not certified.'}
    finally:package.close()
