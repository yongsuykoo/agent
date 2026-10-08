"""Bounded Office plans and an independent, non-executing formula evaluator."""
import ast
from decimal import Decimal, InvalidOperation
import json
import re
from .research import output_text

CELL = {'type':'object','additionalProperties':False,'properties':{
    'kind':{'type':'string','enum':['blank','text','number','formula']},
    'value':{'type':['string','number','null']}},'required':['kind','value']}
CHART = {'type':['object','null'],'additionalProperties':False,'properties':{
    'title':{'type':'string'},'kind':{'type':'string','enum':['column','line']},
    'categories':{'type':'string'},'values':{'type':'string'}},'required':['title','kind','categories','values']}
SHEET = {'type':'object','additionalProperties':False,'properties':{
    'name':{'type':'string'},'rows':{'type':'array','items':{'type':'array','items':CELL}},
    'formats':{'type':'array','items':{'type':'string','enum':['general','decimal','currency','percent','text']}},
    'chart':CHART},'required':['name','rows','formats','chart']}
WORKBOOK = {'type':'object','additionalProperties':False,'properties':{
    'sheets':{'type':'array','items':SHEET}},'required':['sheets']}
DOCUMENT = {'type':'object','additionalProperties':False,'properties':{
    'title':{'type':'string'},'paragraphs':{'type':'array','items':{'type':'string'}},
    'table':{'type':'array','items':{'type':'array','items':{'type':'string'}}}},'required':['title','paragraphs','table']}


def literal(value, limit=2000):
    if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('Office text must be bounded literal text without control characters.')
    return value


def address(value):
    match=re.fullmatch(r'([A-Z])([1-9][0-9]{0,2})',str(value))
    if not match or int(match[2])>200:
        raise ValueError('A cell must be inside A1:Z200.')
    return int(match[2])-1,ord(match[1])-65


def cell_name(row,column):
    return chr(65+column)+str(row+1)


def cell_range(value, rows, columns):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Z][1-9][0-9]{0,2}:[A-Z][1-9][0-9]{0,2}',value):
        raise ValueError('Chart/range references must be literal same-sheet cell ranges.')
    first,last=map(address,value.split(':'))
    if first[0]>last[0] or first[1]>last[1] or last[0]>=rows or last[1]>=columns:
        raise ValueError('Cell range is outside the planned worksheet.')
    return [(r,c) for r in range(first[0],last[0]+1) for c in range(first[1],last[1]+1)]


def number(value):
    if type(value) not in (int,float,Decimal):
        raise ValueError('Cell numbers must be finite numeric values, not booleans.')
    result=Decimal(str(value))
    if not result.is_finite() or abs(result)>Decimal('1e12') or len(result.normalize().as_tuple().digits)>15:
        raise ValueError('Input numbers must be finite, at most 1e12, with at most 15 significant digits.')
    return result


class FormulaEngine:
    """Interpret a tiny arithmetic AST; never eval, execute code or resolve links."""
    def __init__(self, rows):
        self.rows,self.cache,self.visiting=rows,{},set()

    def value(self, ref):
        if ref in self.cache:return self.cache[ref]
        row,column=address(ref)
        if row>=len(self.rows) or column>=len(self.rows[0]):
            raise ValueError('Formula references an unplanned cell.')
        if ref in self.visiting or len(self.visiting)>=80:
            raise ValueError('Circular or excessively deep formula dependency.')
        self.visiting.add(ref)
        try:
            cell=self.rows[row][column]
            if cell['kind']=='blank':result=None
            elif cell['kind']=='text':result=cell['value']
            elif cell['kind']=='number':result=number(cell['value'])
            else:result=self.formula(cell['value'])
            if isinstance(result,Decimal) and (not result.is_finite() or abs(result)>Decimal('1e15')):
                raise ValueError('Formula result is outside the supported numeric range.')
            self.cache[ref]=result
            return result
        finally:
            self.visiting.remove(ref)

    def formula(self, value):
        if not isinstance(value,str) or not value.startswith('=') or len(value)>512:
            raise ValueError('Formulas must be bounded literal Excel expressions.')
        expression=value[1:].upper().replace('$','')
        if not re.fullmatch(r'[A-Z0-9.()+*/,:\s-]+',expression) or re.search(r'\bR\s*\(',expression):
            raise ValueError('Unsupported formula syntax; links, strings and executable expressions are excluded.')
        expression=re.sub(r'\b([A-Z][1-9][0-9]{0,2}):([A-Z][1-9][0-9]{0,2})\b',r'R("\1","\2")',expression)
        try:tree=ast.parse(expression,mode='eval')
        except (SyntaxError,RecursionError) as error:raise ValueError('Invalid formula syntax.') from error
        if len(list(ast.walk(tree)))>150:raise ValueError('Formula is too complex.')
        def numeric(result):
            if result is None:return Decimal(0)
            if not isinstance(result,Decimal):raise ValueError('Arithmetic requires numeric cells.')
            return result
        def visit(node):
            if isinstance(node,ast.Constant) and type(node.value) in (int,float):return number(node.value)
            if isinstance(node,ast.Name):return self.value(node.id)
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
                result=numeric(visit(node.operand));return -result if isinstance(node.op,ast.USub) else result
            if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                a,b=numeric(visit(node.left)),numeric(visit(node.right))
                if isinstance(node.op,ast.Add):return a+b
                if isinstance(node.op,ast.Sub):return a-b
                if isinstance(node.op,ast.Mult):return a*b
                if b==0:raise ValueError('Formula divides by zero.')
                return a/b
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
                name=node.func.id
                if name=='R' and len(node.args)==2 and all(isinstance(a,ast.Constant) and isinstance(a.value,str) for a in node.args):
                    refs=cell_range(':'.join(a.value for a in node.args),len(self.rows),len(self.rows[0]))
                    return [self.value(cell_name(r,c)) for r,c in refs]
                if name in ('SUM','AVERAGE','MIN','MAX','COUNT') and node.args:
                    values=[]
                    for argument in node.args:
                        result=visit(argument);values.extend(result if isinstance(result,list) else [result])
                    values=[v for v in values if isinstance(v,Decimal)]
                    if name=='COUNT':return Decimal(len(values))
                    if name=='SUM':return sum(values,Decimal(0))
                    if not values:raise ValueError('Aggregate formula has no numeric inputs.')
                    return sum(values)/len(values) if name=='AVERAGE' else min(values) if name=='MIN' else max(values)
            raise ValueError('Unsupported formula operation or function.')
        try:result=visit(tree.body)
        except (InvalidOperation,OverflowError,RecursionError) as error:raise ValueError('Invalid formula calculation.') from error
        if not isinstance(result,Decimal):raise ValueError('Formula must produce one numeric value.')
        return result


def validate_workbook(plan, task=''):
    if not isinstance(plan,dict) or set(plan)!={'sheets'} or not isinstance(plan['sheets'],list) or not 1<=len(plan['sheets'])<=3:
        raise ValueError('A workbook needs one to three declared worksheets.')
    names=set();total=0
    for sheet in plan['sheets']:
        if not isinstance(sheet,dict) or set(sheet)!=set(SHEET['properties']):raise ValueError('Invalid worksheet fields.')
        name=sheet['name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,30}',name) or name.casefold() in names:
            raise ValueError('Worksheet names must be unique simple names, up to 31 characters.')
        names.add(name.casefold());rows=sheet['rows']
        if not isinstance(rows,list) or not 1<=len(rows)<=200 or not isinstance(rows[0],list) or not 1<=len(rows[0])<=26:
            raise ValueError('Worksheet dimensions exceed A1:Z200.')
        width=len(rows[0]);total+=len(rows)*width
        if total>1500:raise ValueError('Workbook exceeds 1500 planned cells.')
        if not isinstance(sheet['formats'],list) or len(sheet['formats'])!=width or any(f not in ('general','decimal','currency','percent','text') for f in sheet['formats']):
            raise ValueError('Every column needs a declared supported format.')
        for row in rows:
            if not isinstance(row,list) or len(row)!=width:raise ValueError('Worksheet rows must have the same width.')
            for cell in row:
                if not isinstance(cell,dict) or set(cell)!={'kind','value'}:raise ValueError('Invalid cell fields.')
                kind,value=cell['kind'],cell['value']
                if kind=='blank' and value is None:continue
                if kind=='number':number(value)
                elif kind=='text':literal(value)
                elif kind=='formula' and isinstance(value,str):continue
                else:raise ValueError('Cell type and value disagree.')
        engine=FormulaEngine(rows)
        for r,row in enumerate(rows):
            for c in range(width):engine.value(cell_name(r,c))
        chart=sheet['chart']
        if chart is not None:
            if not isinstance(chart,dict) or set(chart)!=set(CHART['properties']) or chart['kind'] not in ('column','line'):
                raise ValueError('Unsupported chart.')
            if not literal(chart['title'],120).strip():raise ValueError('Chart needs a title.')
            categories=cell_range(chart['categories'],len(rows),width);values=cell_range(chart['values'],len(rows),width)
            if len(categories)!=len(values) or len(values)<2 or len({c for r,c in categories})!=1 or len({c for r,c in values})!=1:
                raise ValueError('A chart needs two equally sized, single-column ranges with at least two points.')
            if any(not isinstance(engine.value(cell_name(r,c)),Decimal) for r,c in values):raise ValueError('Chart values must be numeric.')
    # Literal cell assignments in a brief are independently binding constraints.
    first=plan['sheets'][0]['rows']
    for ref,value in re.findall(r'\b([A-Z][1-9][0-9]{0,2})\s*=\s*([-+]?\d+(?:\.\d+)?)(?![\w.])',task):
        r,c=address(ref)
        if r>=len(first) or c>=len(first[0]) or first[r][c]['kind']!='number' or number(first[r][c]['value'])!=Decimal(value):
            raise ValueError('Plan changed an explicitly requested cell value: '+ref)
    return plan


def validate_document(plan,task=''):
    if not isinstance(plan,dict) or set(plan)!=set(DOCUMENT['properties']):raise ValueError('Invalid document fields.')
    if not literal(plan['title'],200).strip():raise ValueError('Document needs a literal title.')
    paragraphs=plan['paragraphs'];table=plan['table']
    if not isinstance(paragraphs,list) or not 1<=len(paragraphs)<=100 or any(not literal(p).strip() for p in paragraphs):
        raise ValueError('Document needs 1–100 nonempty literal paragraphs.')
    if not isinstance(table,list) or len(table)>50:raise ValueError('Table is too large.')
    if table:
        width=len(table[0]) if isinstance(table[0],list) else 0
        if not 1<=width<=10 or any(not isinstance(row,list) or len(row)!=width for row in table):raise ValueError('Invalid document table dimensions.')
        for row in table:
            for cell in row:literal(cell,500)
    if len(json.dumps(plan))>150000:raise ValueError('Document exceeds its content limit.')
    title=re.search(r'\btitle(?:d)?\s*[:=]?\s*["“]([^"”]+)["”]',task,re.I)
    if title and plan['title']!=title[1]:raise ValueError('Plan changed the requested document title.')
    return plan


def plan_office(task,family,cloud,cancel):
    if family not in ('excel','word'):raise ValueError('Unknown Office tool family.')
    schema=WORKBOOK if family=='excel' else DOCUMENT
    validate=validate_workbook if family=='excel' else validate_document
    feedback=None
    for attempt in range(3):
        if cancel.is_set():raise RuntimeError('Office task cancelled.')
        result=cloud.request(max_output_tokens=6000,text={'format':{'type':'json_schema','name':'office_'+family,'strict':True,'schema':schema}},
            instructions='Return only a declarative plan for the exact user goal, never executable code, commands, URLs or file paths. Do not invent user data or claim execution. Worksheets: at most three, total 1500 cells, rectangular rows, column formats general/decimal/currency/percent/text. Formula cells support only same-sheet A1 references, + - * / and SUM AVERAGE MIN MAX COUNT with bounded ranges; no strings, external links, cross-sheet references, scripts or macros. At most one column/line chart per sheet, with same-length single-column categories/values. Documents: title, 1–100 plain paragraphs, optional rectangular literal-text table. Preserve all supplied numbers and literal titles. This tool creates new xlsx/docx files in a fresh task folder; editing existing files, importing unprovided data, images, email, printing, external delivery and arbitrary formatting require other tools. If the goal cannot be represented faithfully, return an empty sheets/paragraphs array so validation rejects it. Repair validation_feedback without changing the goal.',
            input=json.dumps({'task':task,'family':family,'validation_feedback':feedback}))
        try:return validate(json.loads(output_text(result)),task)
        except (ValueError,TypeError,KeyError) as error:feedback=str(error)
    raise ValueError('Office plan failed validation after three attempts: '+str(feedback))
