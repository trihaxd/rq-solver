"""Export a solved (r, Q) exercise to a real Excel workbook (.xlsx).

Uses artifact_tool rather than Excel automation. The server and terminal
call the same exporter; all numerical cells retain full computational precision
and Excel displays three decimal places. The first three iterations have a
separate, explanatory Worked 0-2 sheet.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path


_NUM = '0.000'
_NAVY = '#15384F'
_TEAL = '#087E83'
_PALE = '#E7F2F5'


def _sheet(wb, name, headers, rows, widths=None):
    sh = wb.worksheets.add(name)
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, (int, float, str, bool)) or value is None:
            return value
        return str(value)
    matrix = [[clean(v) for v in headers]]
    matrix.extend([clean(v) for v in row] for row in rows)
    if not matrix:
        return sh
    # Excel cannot exceed 1,048,576 rows; cap here to avoid freezing the UI.
    if len(matrix) > 10001:
        raise ValueError('Excel export is limited to 10,000 rows per sheet.')
    end_col = _col(len(headers))
    sh.get_range(f'A1:{end_col}{len(matrix)}').values = matrix
    title = sh.get_range(f'A1:{end_col}1')
    title.format = {'fill': _NAVY, 'font': {'bold': True, 'color': '#FFFFFF'},
                    'row_height': 26, 'vertical_alignment': 'center'}
    if len(matrix) > 1:
        rng = sh.get_range(f'A2:{end_col}{len(matrix)}')
        rng.format.number_format = _NUM
        rng.format.row_height = 20
    for i, width in enumerate(widths or [20] * len(headers)):
        sh.get_range(f'{_col(i+1)}:{_col(i+1)}').format.column_width = width
    return sh


def _col(index):
    chars = ''
    while index:
        index, digit = divmod(index - 1, 26)
        chars = chr(65 + digit) + chars
    return chars


def _parse_display(text):
    if isinstance(text, (float, int)): return text
    if not isinstance(text, str): return text
    try:
        return float(text.replace(',', '').replace(' %', '')) if '%' not in text else text
    except ValueError:
        return text


def create_workbook(payload: dict):
    """Build workbook from the same raw data used by the GUI and CLI.

    The iteration history is *unrounded* numeric data, number format = 0.000.
    Never feed previously rounded HTML strings into the trace.
    """
    from artifact_tool import Workbook
    wb = Workbook.create()
    settings = payload.get('settings') or {}
    control = [
        ('Method', '(r, Q) — continuous review, fixed lead time'),
        ('Tolerance', settings.get('tolerance', '')), 
        ('Max iterations', settings.get('max_iter', '')),
        ('Iterations', len(payload.get('iterations', []))),
        ('Interpretation', 'Iteration t: Q_t enters; r_t and n(r_t) are calculated; Q_(t+1) exits.'),
        ('Final Q (full precision)', payload.get('answer', {}).get('Q')),
        ('Final r (full precision)', payload.get('answer', {}).get('r')),
    ]
    _sheet(wb, 'Guide', ['Setting', 'Value'], control, [35, 100])
    summary = [[r.get('name') or r.get('label'), _parse_display(r.get('value')), r.get('unit', ''), r.get('formula', '')]
               for r in payload.get('summary', [])]
    _sheet(wb, 'Answer', ['Quantity', 'Value', 'Meaning', 'Formula'], summary, [36, 20, 58, 35])
    inputs = [[r['label'], r['value']] for r in payload.get('inputs', [])]
    _sheet(wb, 'Inputs', ['Parameter', 'Entered / converted value'], inputs, [38, 72])
    headers = ['Iteration t', 'Q_t (input)', '1 - G(r_t)', 'G(r_t)',
               'r_t', 'Expected shortage n(r_t)', 'Q_(t+1) (output)', '|change in r|']
    records = [[it.get('index'), it.get('Q'), it.get('tail'), it.get('G'),
                it.get('r'), it.get('n_r'), it.get('Q_next'), it.get('delta_r')]
               for it in payload.get('iterations', [])]
    _sheet(wb, 'Iterations', headers, records, [17, 21, 18, 18, 18, 30, 25, 20])
    steps = []
    for block in payload.get('steps_by_iteration', []):
        for index, line in enumerate(block['steps'], 1):
            steps.append([block['index'], index, line['label'], line['plain']])
        steps.append(['', '', '', ''])
    _sheet(wb, 'Worked 0-2', ['Iteration', 'Step', 'Calculation', 'Substitution and result'],
           steps, [18, 13, 48, 110])
    costs = [[r.get('name') or r.get('label'), _parse_display(r.get('value')), r.get('formula', '')]
             for r in payload.get('cost', [])]
    _sheet(wb, 'Costs', ['Component', 'Cost per base unit', 'Formula'], costs, [33, 28, 40])
    if payload.get('policy2'):
        r2 = payload['policy2']
        rows = [[r.get('name') or r.get('label'), _parse_display(r.get('value')), r.get('unit', '')]
                for r in r2.get('summary', [])]
        _sheet(wb, 'Periodic policy', ['Metric', 'Value', 'Explanation'], rows, [39, 25, 65])
    if payload.get('comparison'):
        rows = [[r.get('name') or r.get('label'), _parse_display(r.get('value')), r.get('unit', '')]
                for r in payload['comparison'].get('rows', [])]
        _sheet(wb, 'Comparison', ['Metric', 'Value', 'Explanation'], rows, [38, 25, 63])
    return wb


def export_bytes(payload: dict) -> bytes:
    """Use artifact_tool when installed, otherwise a stdlib OOXML writer.

    The fallback makes GUI and terminal Excel export work even on an ordinary
    offline Python installation with no third-party spreadsheet dependency.
    """
    try:
        from artifact_tool import SpreadsheetFile
    except ImportError:
        return _stdlib_xlsx(payload)
    wb = create_workbook(payload)
    with tempfile.TemporaryDirectory(prefix='rq_excel_') as directory:
        path = Path(directory) / 'rq_results.xlsx'
        SpreadsheetFile.export_xlsx(wb).save(str(path))
        return path.read_bytes()


def save_payload(payload: dict, filename: str) -> Path:
    path = Path(filename).expanduser().resolve()
    if path.suffix.lower() != '.xlsx':
        raise ValueError('Excel output path must end in .xlsx')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(export_bytes(payload))
    return path


# A dependency-free OOXML export for computers without artifact_tool.
# This is a minimal standard XLSX writer, not a second solver and not another
# spreadsheet library. All eight iteration columns remain numeric and retain
# full precision; Excel applies a three-decimal number format to their display.
def _stdlib_xlsx(payload: dict) -> bytes:
    from io import BytesIO
    from zipfile import ZipFile, ZIP_DEFLATED
    from xml.sax.saxutils import escape
    from xml.etree import ElementTree as ET

    def safe(v):
        if v is None or isinstance(v, float) and not math.isfinite(v):
            return None
        return v

    settings = payload.get('settings', {})
    sheets = [
      ('Guide', [['Setting', 'Value'],
                 ['Tolerance', settings.get('tolerance')],
                 ['Max iterations', settings.get('max_iter')],
                 ['Iteration rule', 'Q_t -> r_t -> n(r_t) -> Q_(t+1)']]),
      ('Answer', [['Quantity','Value','Meaning','Formula']] +
                  [[r.get('name') or r.get('label'), _parse_display(r.get('value')),
                    r.get('unit',''),r.get('formula','')]
                   for r in payload.get('summary', [])]),
      ('Inputs', [['Parameter','Entered / converted value']] +
                  [[r['label'],r['value']] for r in payload.get('inputs', [])]),
      ('Iterations', [['Iteration t','Q_t (input)','1 - G(r_t)','G(r_t)',
                       'r_t','Expected shortage n(r_t)','Q_(t+1) (output)','|change in r|']] +
                       [[it.get(k) for k in ('index','Q','tail','G','r','n_r','Q_next','delta_r')]
                        for it in payload.get('iterations', [])]),
      ('Worked 0-2', [['Iteration','Step','Calculation','Substitution and result']] +
                     [[block['index'], n+1, step['label'],step['plain']]
                      for block in payload.get('steps_by_iteration', [])
                      for n, step in enumerate(block['steps'])]),
      ('Costs', [['Component','Cost per base unit','Formula']] +
                 [[r.get('name') or r.get('label'),_parse_display(r.get('value')),
                   r.get('formula','')] for r in payload.get('cost', [])])]
    if payload.get('policy2'):
        sheets.append(('Periodic policy', [['Metric','Value','Explanation']] +
              [[r.get('name') or r.get('label'),_parse_display(r.get('value')),
                r.get('unit','')] for r in payload['policy2'].get('summary', [])]))
    if payload.get('comparison'):
        sheets.append(('Comparison', [['Metric','Value','Explanation']] +
              [[r.get('name') or r.get('label'),_parse_display(r.get('value')),
                r.get('unit','')] for r in payload['comparison'].get('rows', [])]))
    for name, table in sheets:
        if len(table) > 10001:
            raise ValueError(f'Excel sheet {name} exceeds 10,000 rows')

    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    package = 'http://schemas.openxmlformats.org/package/2006/relationships'
    ct = 'http://schemas.openxmlformats.org/package/2006/content-types'
    ET.register_namespace('x', ns)
    ET.register_namespace('r', rel)
    mem = BytesIO()
    with ZipFile(mem, 'w', ZIP_DEFLATED) as z:
        # Content types, workbook relationships, spreadsheet and minimal styles.
        types = ET.Element(f'{{{ct}}}Types')
        ET.SubElement(types, f'{{{ct}}}Default', Extension='rels',
                      ContentType='application/vnd.openxmlformats-package.relationships+xml')
        ET.SubElement(types, f'{{{ct}}}Default', Extension='xml', ContentType='application/xml')
        for part, content in [('/xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),
            ('/xl/styles.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')]:
            ET.SubElement(types,f'{{{ct}}}Override',PartName=part,ContentType=content)
        for i in range(1,len(sheets)+1):
            ET.SubElement(types,f'{{{ct}}}Override',PartName=f'/xl/worksheets/sheet{i}.xml',
                ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        z.writestr('[Content_Types].xml',ET.tostring(types,encoding='utf-8',xml_declaration=True))
        relation = ET.Element(f'{{{package}}}Relationships')
        ET.SubElement(relation,f'{{{package}}}Relationship',Id='rId1',
                     Type=rel+'/officeDocument',Target='xl/workbook.xml')
        z.writestr('_rels/.rels',ET.tostring(relation,encoding='utf-8',xml_declaration=True))
        wb=ET.Element(f'{{{ns}}}workbook')
        wbs=ET.SubElement(wb,f'{{{ns}}}sheets')
        for i,(name,_) in enumerate(sheets,1):
            ET.SubElement(wbs,f'{{{ns}}}sheet',{'name':name,'sheetId':str(i),f'{{{rel}}}id':f'rId{i}'})
        z.writestr('xl/workbook.xml',ET.tostring(wb,encoding='utf-8',xml_declaration=True))
        wrels = ET.Element(f'{{{package}}}Relationships')
        for i in range(1,len(sheets)+1):
            ET.SubElement(wrels,f'{{{package}}}Relationship',Id=f'rId{i}',
                Type=rel+'/worksheet',Target=f'worksheets/sheet{i}.xml')
        ET.SubElement(wrels,f'{{{package}}}Relationship',Id=f'rId{len(sheets)+1}',
                      Type=rel+'/styles',Target='styles.xml')
        z.writestr('xl/_rels/workbook.xml.rels', ET.tostring(wrels,encoding='utf-8',xml_declaration=True))
        styles=ET.Element(f'{{{ns}}}styleSheet')
        fmts=ET.SubElement(styles,f'{{{ns}}}numFmts',count='1')
        ET.SubElement(fmts,f'{{{ns}}}numFmt',numFmtId='164',formatCode='0.000')
        fonts=ET.SubElement(styles,f'{{{ns}}}fonts',count='2')
        ET.SubElement(ET.SubElement(fonts,f'{{{ns}}}font'),f'{{{ns}}}sz',val='11')
        font=ET.SubElement(fonts,f'{{{ns}}}font')
        ET.SubElement(font,f'{{{ns}}}b')
        ET.SubElement(font,f'{{{ns}}}sz',val='11')
        fills=ET.SubElement(styles,f'{{{ns}}}fills',count='2')
        for pattern in ('none','gray125'):
            ET.SubElement(fills,f'{{{ns}}}fill').append(ET.Element(f'{{{ns}}}patternFill',patternType=pattern))
        ET.SubElement(styles,f'{{{ns}}}borders',count='1').append(ET.Element(f'{{{ns}}}border'))
        base_xfs=ET.SubElement(styles,f'{{{ns}}}cellStyleXfs',count='1')
        ET.SubElement(base_xfs,f'{{{ns}}}xf',numFmtId='0',fontId='0',fillId='0',borderId='0')
        xfs=ET.SubElement(styles,f'{{{ns}}}cellXfs',count='3')
        ET.SubElement(xfs,f'{{{ns}}}xf',numFmtId='0',fontId='0',fillId='0',borderId='0',xfId='0')
        ET.SubElement(xfs,f'{{{ns}}}xf',numFmtId='164',fontId='0',fillId='0',borderId='0',xfId='0',applyNumberFormat='1')
        ET.SubElement(xfs,f'{{{ns}}}xf',numFmtId='0',fontId='1',fillId='0',borderId='0',xfId='0')
        z.writestr('xl/styles.xml',ET.tostring(styles,encoding='utf-8',xml_declaration=True))
        for i,(_,data) in enumerate(sheets,1):
            ws=ET.Element(f'{{{ns}}}worksheet')
            views=ET.SubElement(ws,f'{{{ns}}}sheetViews')
            view=ET.SubElement(views,f'{{{ns}}}sheetView',workbookViewId='0')
            ET.SubElement(view,f'{{{ns}}}pane',ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
            cols=ET.SubElement(ws,f'{{{ns}}}cols')
            for idx in range(1, len(data[0])+1):
                ET.SubElement(cols,f'{{{ns}}}col',min=str(idx),max=str(idx),width=str(17 if idx != len(data[0]) else 42),customWidth='1')
            body=ET.SubElement(ws,f'{{{ns}}}sheetData')
            for rix,row in enumerate(data,1):
                r=ET.SubElement(body,f'{{{ns}}}row',r=str(rix))
                for cix,val in enumerate(row,1):
                    val=safe(val)
                    if val is None: continue
                    c=ET.SubElement(r,f'{{{ns}}}c',r=f'{_col(cix)}{rix}',s='2' if rix==1 else '1')
                    if isinstance(val, (int,float)) and not isinstance(val, bool):
                        ET.SubElement(c,f'{{{ns}}}v').text=str(val)
                    else:
                        c.set('t','inlineStr')
                        ET.SubElement(ET.SubElement(c,f'{{{ns}}}is'),f'{{{ns}}}t').text=str(val)
            z.writestr(f'xl/worksheets/sheet{i}.xml',ET.tostring(ws,encoding='utf-8',xml_declaration=True))
    return mem.getvalue()
