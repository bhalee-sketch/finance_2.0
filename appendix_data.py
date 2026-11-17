"""Read appendix records directly from SQLite, without an Excel workbook object."""
import json
import re
from openpyxl.utils.cell import range_boundaries
from statement_database import connect,decode


def load_sheet(database,name,year='2025'):
    with connect(database) as connection:
        sheet=connection.execute('SELECT s.id,s.merged_ranges_json FROM sheets s JOIN workbooks w ON w.id=s.workbook_id WHERE w.fiscal_year=? AND s.name=?',(year,name)).fetchone()
        if sheet is None:raise ValueError('저장된 부속명세서가 없습니다.')
        cells={(r,c):decode(value) for r,c,value in connection.execute(
            'SELECT row_number,column_number,cached_value_json FROM cells WHERE sheet_id=? ORDER BY row_number,column_number',(sheet[0],))}
        merged=[range_boundaries(bounds) for bounds in json.loads(sheet[1])]
    populated={row for (row,column),value in cells.items() if value is not None and str(value).strip()}
    header_start=next((row for row in sorted(populated) if sum(r==row and v is not None and str(v).strip()!='' for (r,c),v in cells.items())>=2),None)
    if header_start is None:raise ValueError('표의 열 제목을 찾지 못했습니다: '+name)
    header_end=max([header_start]+[r2 for c1,r1,c2,r2 in merged if r1<=header_start<=r2 and r2<=header_start+5])
    source_columns=sorted({c for (r,c),v in cells.items() if r>=header_start and v is not None and str(v).strip()})
    expanded=dict(cells)
    for c1,r1,c2,r2 in merged:
        value=cells.get((r1,c1))
        if value is None:continue
        if r1<=header_end:
            for row in range(r1,min(r2,header_end)+1):
                for column in range(c1,c2+1):expanded.setdefault((row,column),value)
        elif isinstance(value,str) and c1==c2:
            # Repeat merged category labels as record fields, never numeric totals.
            for row in range(r1,r2+1):expanded.setdefault((row,c1),value)
    headers=[]
    for column in source_columns:
        parts=[]
        for row in range(header_start,header_end+1):
            value=expanded.get((row,column))
            if value is not None:
                label=re.sub(r'\s+','',str(value))
                if label and label not in parts:parts.append(label)
        headers.append(' / '.join(parts) or '항목')
    records=[{'source_row':row,'values':[expanded.get((row,column)) for column in source_columns]}
             for row in sorted(populated) if row>header_end]
    totals={};spans=[]
    for index,record in enumerate(records):
        values=record['values']
        for column,value in enumerate(values):
            if not isinstance(value,str):continue
            compact=re.sub(r'\s+','',value)
            if compact!='계' and not re.search(r'(합계|소계|총계)$',compact):continue
            totals[index]='subtotal' if compact.endswith('소계') else 'total'
            # Span only empty label cells; never cover money or another field.
            start=column;end=column
            while start>0 and values[start-1] in (None,''):start-=1
            while end+1<len(values) and values[end+1] in (None,''):end+=1
            if end>start:spans.append((index,start,end-start+1,column))
            break
    return {'name':name,'headers':headers,'records':records,'source_columns':source_columns,
            'totals':totals,'spans':spans,
            'header_start':header_start,'header_end':header_end}
