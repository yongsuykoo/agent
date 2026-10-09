"""Deterministic tool selection; unsupported goals retain the desktop route."""
import ntpath
import re
from .runner import exact_text_goal


def office_family(app):
    name=app.get('name','')
    executable=ntpath.basename(app.get('launch_executable','')).casefold()
    if re.search(r'\b(help|uninstall|update|manual|viewer)\b',name,re.I):return None
    if executable=='excel.exe' or re.search(r'\b(?:microsoft\s+)?excel\b',name,re.I):return 'excel'
    if executable=='winword.exe' or re.search(r'\b(?:microsoft\s+)?word\b',name,re.I):return 'word'
    return None


def select_office(apps,family):
    installations={}
    for app in apps:
        if office_family(app)!=family:continue
        path=app.get('launch_executable') or app.get('location') or app['id']
        key=ntpath.normcase(ntpath.normpath(path))
        rank=lambda a:(bool(a.get('launch_executable')),bool(a.get('version')))
        if key not in installations or rank(app)>rank(installations[key]):installations[key]=app
    return next(iter(installations.values())) if len(installations)==1 else None


def choose_tool(task,apps,selected_app=None):
    if exact_text_goal(task) is not None:return {'kind':'desktop'}
    from .file_tools import file_request
    request=file_request(task)
    if request and selected_app is None:return {'kind':'files','request':request}
    from .browser import browser_request
    request=browser_request(task)
    if request and selected_app is None:return {'kind':'browser','request':request}
    # A creation tool must not silently omit the rest of a compound goal.
    if re.search(r'\b(?:email|send|upload|publish|print|delete|attach|import|open|existing|replace|edit|modify|update|macro|image|photo|pivot)\b|[A-Za-z]:[\\/]|https?://',task,re.I):
        return {'kind':'desktop'}
    from .logo_design import logo_request
    if logo_request(task):return {'kind':'photoshop'}
    if not re.search(r'\b(?:create|make|build|generate|write)\b',task,re.I):return {'kind':'desktop'}
    mentions=[family for family,pattern in [('excel',r'\b(?:excel|xlsx|workbook|spreadsheet)\b'),('word',r'\b(?:word|docx)\b')] if re.search(pattern,task,re.I)]
    if len(mentions)!=1:return {'kind':'desktop'}
    family=mentions[0]
    if selected_app and office_family(selected_app)!=family:return {'kind':'desktop'}
    # Explicitly selected different apps (e.g. LibreOffice) must not be displaced.
    for app in apps:
        if office_family(app)==family:continue
        if any(re.search(r'\b(?:in|using|with)\s+(?:the\s+)?'+re.escape(name)+r'\b',task,re.I)
               for name in app.get('aliases',[app.get('name','')]) if name):return {'kind':'desktop'}
    app=selected_app or select_office(apps,family)
    return {'kind':'office','family':family,'app':app} if app else {'kind':'desktop'}
