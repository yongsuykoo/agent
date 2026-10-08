"""Minimal OOXML byte fixtures; no Windows or model execution is implied."""
from decimal import Decimal
import zipfile
from xml.etree import ElementTree as ET
from app_agent.office_artifacts import S,W,C,A,R,P
from app_agent.office_plan import FormulaEngine,cell_name,cell_range

WORKBOOK={'sheets':[{'name':'Budget','rows':[
    [{'kind':'text','value':'Item'},{'kind':'text','value':'Amount'}],
    [{'kind':'text','value':'Paper'},{'kind':'number','value':12.5}],
    [{'kind':'text','value':'Ink'},{'kind':'number','value':7.5}],
    [{'kind':'text','value':'Total'},{'kind':'formula','value':'=SUM(B2:B3)'}]],
    'formats':['general','currency'],'chart':{'title':'Costs','kind':'column','categories':'A2:A3','values':'B2:B3'}}]}
DOCUMENT={'title':'Project brief','paragraphs':['Hello from my agent.','Next steps.'],'table':[['Item','Owner'],['Logo','Artist']]}


def element(tag,namespace,**attributes):return ET.Element('{'+namespace+'}'+tag,attributes)
def sub(parent,tag,namespace,text=None,**attributes):
    node=ET.SubElement(parent,'{'+namespace+'}'+tag,attributes);node.text=text;return node
def xml(node):return ET.tostring(node,encoding='utf-8',xml_declaration=True)
def relationship(identity,target,kind):return {'Id':identity,'Target':target,'Type':R+'/'+kind}
def rels(items):
    root=element('Relationships',P)
    for item in items:sub(root,'Relationship',P,**item)
    return xml(root)

def package_metadata(part,kind):
    root=element('Types','http://schemas.openxmlformats.org/package/2006/content-types')
    sub(root,'Override','http://schemas.openxmlformats.org/package/2006/content-types',PartName='/'+part,
        ContentType='application/vnd.openxmlformats-officedocument.'+kind+'.main+xml')
    return {'[Content_Types].xml':xml(root),'_rels/.rels':rels([relationship('main',part,'officeDocument')])}


def workbook_parts(plan=WORKBOOK):
    book=element('workbook',S);sheets=sub(book,'sheets',S);relationships=[]
    style=element('styleSheet',S);formats=sub(style,'numFmts',S,count='1');sub(formats,'numFmt',S,numFmtId='164',formatCode='$#,##0.00')
    xfs=sub(style,'cellXfs',S,count='5')
    for number in (0,2,164,10,49):sub(xfs,'xf',S,numFmtId=str(number))
    parts={**package_metadata('xl/workbook.xml','spreadsheetml.sheet'),'xl/styles.xml':xml(style)}
    styles={'general':'0','decimal':'1','currency':'2','percent':'3','text':'4'}
    for index,design in enumerate(plan['sheets'],1):
        sub(sheets,'sheet',S,name=design['name'],sheetId=str(index),**{'{'+R+'}id':'sheet'+str(index)})
        relationships.append(relationship('sheet'+str(index),'worksheets/sheet'+str(index)+'.xml','worksheet'))
        root=element('worksheet',S);data=sub(root,'sheetData',S);engine=FormulaEngine(design['rows'])
        for r,row in enumerate(design['rows']):
            saved_row=sub(data,'row',S,r=str(r+1))
            for c,cell in enumerate(row):
                node=sub(saved_row,'c',S,r=cell_name(r,c),s=styles[design['formats'][c]])
                value=engine.value(cell_name(r,c))
                if cell['kind']=='text':
                    node.set('t','inlineStr');sub(sub(node,'is',S),'t',S,text=value)
                else:
                    if cell['kind']=='formula':sub(node,'f',S,text=cell['value'][1:])
                    if value is not None:sub(node,'v',S,text=str(value))
        chart=design['chart']
        if chart:
            sub(root,'drawing',S,**{'{'+R+'}id':'drawing'})
            drawing=element('wsDr','http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing')
            sub(drawing,'chart',C,**{'{'+R+'}id':'chart'})
            parts[f'xl/worksheets/_rels/sheet{index}.xml.rels']=rels([relationship('drawing',f'../drawings/drawing{index}.xml','drawing')])
            parts[f'xl/drawings/drawing{index}.xml']=xml(drawing)
            parts[f'xl/drawings/_rels/drawing{index}.xml.rels']=rels([relationship('chart',f'../charts/chart{index}.xml','chart')])
            chart_root=element('chartSpace',C);graph=sub(chart_root,'chart',C)
            sub(sub(sub(sub(graph,'title',C),'tx',C),'rich',C),'t',A,text=chart['title'])
            plot=sub(sub(graph,'plotArea',C),'barChart' if chart['kind']=='column' else 'lineChart',C)
            if chart['kind']=='column':sub(plot,'barDir',C,val='col')
            series=sub(plot,'ser',C)
            for field,key in [('cat','categories'),('val','values')]:
                source=sub(sub(series,field,C),'strRef' if field=='cat' else 'numRef',C)
                sub(source,'f',C,text="'"+design['name']+"'!"+chart[key])
                cache=sub(source,'strCache' if field=='cat' else 'numCache',C)
                refs=cell_range(chart[key],len(design['rows']),len(design['rows'][0]));sub(cache,'ptCount',C,val=str(len(refs)))
                for point,(r,c) in enumerate(refs):sub(sub(cache,'pt',C,idx=str(point)),'v',C,text=str(engine.value(cell_name(r,c))))
            parts[f'xl/charts/chart{index}.xml']=xml(chart_root)
        parts[f'xl/worksheets/sheet{index}.xml']=xml(root)
    parts['xl/workbook.xml']=xml(book)
    parts['xl/_rels/workbook.xml.rels']=rels(relationships)
    return parts


def document_parts(plan=DOCUMENT):
    root=element('document',W);body=sub(root,'body',W)
    for text in [plan['title'],*plan['paragraphs']]:sub(sub(sub(body,'p',W),'r',W),'t',W,text=text)
    if plan['table']:
        table=sub(body,'tbl',W)
        for row in plan['table']:
            tr=sub(table,'tr',W)
            for text in row:sub(sub(sub(sub(tr,'tc',W),'p',W),'r',W),'t',W,text=text)
    sub(body,'sectPr',W)
    return {**package_metadata('word/document.xml','wordprocessingml.document'),'word/document.xml':xml(root)}


def save(path,parts):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in parts.items():archive.writestr(name,data)
