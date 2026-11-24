"""Compatibility command and XML helpers for file links; never transform material text."""
if __name__=='__main__' and not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import io
import re
from xml.etree import ElementTree as E

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
Q=lambda name:'{'+NS+'}'+name
E.register_namespace('',NS)
E.register_namespace('r',REL)

_prefixes={}
COMPAT_PREFIXES={
    'mc':'http://schemas.openxmlformats.org/markup-compatibility/2006',
    'x14ac':'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac',
    'x14':'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main',
    'x15':'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main',
    'x15ac':'http://schemas.microsoft.com/office/spreadsheetml/2010/11/ac',
    'x16r2':'http://schemas.microsoft.com/office/spreadsheetml/2015/02/main',
    'xr':'http://schemas.microsoft.com/office/spreadsheetml/2014/revision',
    'xr2':'http://schemas.microsoft.com/office/spreadsheetml/2015/revision2',
    'xr3':'http://schemas.microsoft.com/office/spreadsheetml/2016/revision3',
    'xr6':'http://schemas.microsoft.com/office/spreadsheetml/2016/revision6',
    'xr10':'http://schemas.microsoft.com/office/spreadsheetml/2016/revision10',
}


def xml(raw):
    prefixes={}
    for event,item in E.iterparse(io.BytesIO(raw),events=('start-ns','start')):
        if event=='start': break
        prefixes[item[0]]=item[1]
    node=E.fromstring(raw); _prefixes[id(node)]=prefixes
    return node


def encoded(node):
    # Preserve namespace declarations used inside Excel compatibility attributes.
    # ElementTree discards otherwise-unused prefixes, making native Excel reject a file.
    prefixes={**COMPAT_PREFIXES,**_prefixes.get(id(node),{})}
    for prefix,uri in prefixes.items():
        if not re.fullmatch(r'ns\d+',prefix): E.register_namespace(prefix,uri)
    raw=E.tostring(node,encoding='utf-8',xml_declaration=True)
    start=raw.index(b'<',raw.index(b'?>')+2); end=raw.index(b'>',start)
    header=raw[start:end]
    declarations=[]
    for prefix,uri in prefixes.items():
        key=('xmlns:'+prefix if prefix else 'xmlns').encode()
        if not re.search(rb'\s'+re.escape(key)+rb'=',header):
            declarations.append(b' '+key+b'="'+uri.encode()+b'"')
    return raw[:end]+b''.join(declarations)+raw[end:]



def run(argv=None):
    from material_preparation.review_material_links import run as file_links
    return file_links(argv)


if __name__=='__main__':
    import sys
    from shared import common as c
    try: sys.exit(run())
    except Exception as error: print(c.safe_error_message(error),file=sys.stderr); sys.exit(2)
