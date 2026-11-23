"""원 단위 확정결산 분석. 표시 문자열 대신 원본 값과 셀 출처를 보존한다."""
from pathlib import Path
from decimal import Decimal
import json
import os
import tempfile
from openpyxl import load_workbook,Workbook
from openpyxl.utils import get_column_letter
from statement_analysis import parse_fund,normalize,optional_money
from statement_catalog import discover_years,discover_appendices
from finance_data import append_row,format_sheet,save_atomic

SCOPES=('전체','등록금','비등록금')
ANALYSIS_SHEETS={f'{kind}({scope})' for kind in ('자금계산서','재무상태표','운영계산서') for scope in SCOPES}
UNITS=('교비','대학원','평생교육원','생활관','국고','복지회')
ANALYSIS_HEADERS=['과목','결산','구성비(%)','선택 분모 대비(%)','직전연도 결산','증감','증감률(%)','확인사항']
DEFAULT_PRESET={'scope':'등록금','units':['교비','대학원'],'paths':[['등록금및수강료수입','등록금수입']]}


def parse_nonfund(sheet,rows,index,kind):
    section='자산' if kind=='재무상태표' else '수입'
    items={};totals={};sources={};path=['','','']
    for number,row in enumerate(rows,2):
        raw=str(row[0] or '');name=raw.strip();key=normalize(name).strip('[]')
        if not name:continue
        value=optional_money(row[index])
        if kind=='재무상태표':
            if key=='자산총계':totals['자산']=(None,value);continue
            if key in ('부채와기본금총계','부채및기본금총계'):totals['부채와기본금']=(None,value);continue
            if name.startswith(('[지출]','[부채')):section='부채와기본금';path=['','',''];continue
        else:
            if key=='운영수익총계':
                totals['수입']=(None,value);section='지출';path=['','',''];continue
            if key in ('비용총계','운영지출총계'):totals['지출']=(None,value);continue
            if key=='운영비용총계':continue
            if name.startswith('[지출]'):section='지출';path=['','',''];continue
        if name.startswith(('[','<','(')):continue
        indent=len(raw)-len(raw.lstrip(' '));level=0 if indent<5 else 1 if indent<10 else 2
        path[level]=name
        for j in range(level+1,3):path[j]=''
        if any(not part for part in path[:level]):raise ValueError(f'{sheet} {number}행: 관·항·목 순서를 확인하세요.')
        identity=(section,level,tuple(path[:level+1]))
        if identity in items:raise ValueError(f'{sheet} {number}행: 동일 과목 경로가 중복됩니다.')
        items[identity]={'key':identity,'section':section,'level':level,'path':identity[2],'budget':None,'actual':value}
        sources[identity]=number
    return {'items':items,'totals':totals,'sources':sources,'sheet':sheet}


def statement_view(year,kind):
    datasets=year.get('datasets',{}) if kind=='자금계산서' else year.get('statements',{}).get(kind,{})
    return dict(year,datasets=datasets)


def analysis_year(path,sheets):
    datasets={};basis=[];issues=[];statements={'자금계산서':datasets,'재무상태표':{},'운영계산서':{}}
    for title,rows,bad in sheets:
        name=normalize(title)
        headers=[normalize(v) for v in rows[0]]
        column='결산' if name.startswith('자금계산서') else '당기'
        if column not in headers:issues.append(f'{title}: {column} 열 없음');continue
        ci=headers.index(column)
        for rn,row in enumerate(rows[1:],2):
            if not row or not str(row[0] or '').strip():continue
            coordinate=f'{get_column_letter(ci+1)}{rn}'
            try:value=optional_money(row[ci])
            except ValueError: value=None;bad[coordinate]='금액 형식 확인 필요'
            basis.append([str(path),title,coordinate,str(row[0]).strip(),value,
                          bad.get(coordinate,'값 있음' if value is not None else '빈 값')])
        issues.extend(f'{title}!{cell}: {reason}' for cell,reason in bad.items())
        kind=name.split('(')[0]
        scope=next(scope for scope in SCOPES if name==f'{kind}({scope})')
        for unit in ['합계']+([u for u in UNITS if u in headers] if scope!='전체' else []):
            idx=ci if unit=='합계' else headers.index(unit)
            transformed=[list(row) for row in rows[1:]]
            for rn,row in enumerate(transformed,2):
                try:row[ci]=optional_money(row[idx])
                except ValueError:
                    row[ci]=None;issues.append(f'{title}!{get_column_letter(idx+1)}{rn}: 금액 형식 확인 필요')
            # 분석에 예산은 사용하지 않는다. 예산 셀 이상이 결산을 막지 않게 한다.
            copied_headers=list(rows[0])
            for i,h in enumerate(headers):
                if h=='예산':copied_headers[i]='참고예산'
            record={'sheets':[{'name':title,'headers':copied_headers,'rows':transformed}]}
            parsed=parse_fund(record,scope) if kind=='자금계산서' else parse_nonfund(title,transformed,ci,kind)
            for key,item in parsed['items'].items():
                item['source']=(str(path),title,f'{get_column_letter(idx+1)}{parsed["sources"][key]}')
            statements[kind][(scope,unit)]=parsed
    if ('전체','합계') not in datasets:raise ValueError('자금계산서(전체)의 결산 자료가 없습니다.')
    return {'datasets':datasets,'statements':statements,'basis':basis,'issues':issues,'source':path}


def analysis_sheets(workbook,formulas=None):
    for sheet in workbook:
        if normalize(sheet.title) not in ANALYSIS_SHEETS:continue
        rows=[];bad={}
        pairs=zip(sheet,formulas[sheet.title]) if formulas is not None else ((cells,cells) for cells in sheet)
        for cells,original in pairs:
            values=[]
            for cell,formula in zip(cells,original):
                value=cell.value
                if cell.data_type=='e' or (formula.data_type=='f' and value is None):
                    bad[cell.coordinate]='Excel 오류' if cell.data_type=='e' else '수식 계산값 없음'
                    value=None
                values.append(value)
            rows.append(values)
        yield sheet.title,rows,bad


def raw_year(path):
    """Keep blank rows so Excel cell coordinates remain stable."""
    path=Path(path)
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        formulas=load_workbook(path,read_only=True,data_only=False)
        try:return analysis_year(path,analysis_sheets(book,formulas))
        finally:formulas.close()
    finally:book.close()


def load_history(folder):
    paths=discover_years(folder);history={};issues=[]
    for year,path in paths.items():
        try:history[year]=raw_year(path)
        except Exception as e:issues.append(f'{year}: {e}')
    return history,issues,paths


def canonical_paths(paths):
    result=[]
    for path in paths:
        p=tuple(normalize(v) for v in path)
        if not p or len(p)>3 or any(not v for v in p):raise ValueError('수입 과목 경로를 확인하세요.')
        if any(p[:len(q)]==q for q in result):continue
        result=[q for q in result if q[:len(p)]!=p];result.append(p)
    return result


def validate_preset(preset):
    if not isinstance(preset,dict):raise ValueError('분모 설정 형식이 올바르지 않습니다.')
    scope=preset.get('scope');units=preset.get('units',[]);paths=preset.get('paths',[])
    if scope not in SCOPES or not isinstance(units,list) or not units:raise ValueError('분모 회계단위를 선택하세요.')
    if any(u not in ('합계',*UNITS) for u in units):raise ValueError('알 수 없는 회계단위입니다.')
    if ('합계' in units and len(units)>1) or (scope=='전체' and units!=['합계']):
        raise ValueError('전체와 세부 회계단위는 함께 합산할 수 없습니다.')
    if not isinstance(paths,list) or not paths or any(not isinstance(p,(list,tuple)) for p in paths):raise ValueError('수입 과목을 선택하세요.')
    canonical=canonical_paths(paths)
    return {'scope':scope,'units':list(dict.fromkeys(units)),'paths':[list(p) for p in canonical]}


def denominator(year,preset):
    preset=validate_preset(preset);amount=Decimal(0);details=[];missing=[]
    for unit in preset['units']:
        parsed=year['datasets'].get((preset['scope'],unit))
        for path in preset['paths']:
            found=[v for v in (parsed or {}).get('items',{}).values()
                   if v['section']=='수입' and tuple(map(normalize,v['path']))==tuple(path)]
            item=found[0] if len(found)==1 else None
            value=item['actual'] if item else None
            details.append([preset['scope'],unit,' / '.join(item['path'] if item else path),value,
                            *(item['source'] if item else ('','',''))])
            if value is None:missing.append(f'{unit}: {" / ".join(path)}')
            else:amount+=value
    if missing:return None,details,'자료 필요: '+', '.join(missing)
    return amount,details,('분모가 0 이하이므로 비율 계산 제외' if amount<=0 else '')


def ratio(n,d):return n/d*100 if n is not None and d is not None and d>0 else None


def analysis_rows(current,previous,scope,unit,section,path,denom):
    """선택 경로의 바로 아래 계층만 구성비로 비교한다. 현재 원본 순서 유지."""
    parsed=current['datasets'].get((scope,unit));prior=(previous or {}).get('datasets',{}).get((scope,unit))
    if parsed is None:return [],None
    path=tuple(map(normalize,path));level=min(len(path),2)
    def selected(item):
        p=tuple(map(normalize,item['path']))
        return item['section']==section and item['level']==level and p[:len(path)]==path
    current_items=[v for v in parsed['items'].values() if selected(v)]
    prior_items=[v for v in (prior or {}).get('items',{}).values() if selected(v)]
    key=lambda item:tuple(map(normalize,item['path']))
    before={key(v):v for v in prior_items};now={key(v):v for v in current_items}
    items=current_items+[v for v in prior_items if key(v) not in now]
    if path:
        parents=[v for v in parsed['items'].values() if v['section']==section and key(v)==path]
        base=parents[0]['actual'] if len(parents)==1 else None
    else:base=parsed['totals'].get(section,(None,None))[1]
    result=[]
    for item in items:
        curr=now.get(key(item));old=before.get(key(item));a=curr['actual'] if curr else None;b=old['actual'] if old else None
        delta=None if a is None or b is None else a-b
        notes=[]
        if a is None:notes.append('당기 자료 없음')
        if b is None:notes.append('직전연도 자료 없음')
        if base is None or base<=0:notes.append('구성비 기준 없음/0 이하')
        if denom is None or denom<=0:notes.append('분모 없음/0 이하')
        if b is not None and b<=0:notes.append('증감률 기준 0 이하')
        result.append({'item':curr or item,'values':[' / '.join(item['path']),a,ratio(a,base),ratio(a,denom),b,delta,ratio(delta,b),' · '.join(notes)]})
    return result,base


def save_preset(folder,name,preset):
    name=name.strip()
    if not name:raise ValueError('조합 이름을 입력하세요.')
    preset=validate_preset(preset);path=Path(folder)/'분석설정.json';existing=load_presets(folder);existing[name]=preset
    path.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=path.parent,suffix='.json');os.close(fd)
    try:
        Path(tmp).write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def load_presets(folder):
    path=Path(folder)/'분석설정.json'
    if not path.exists():return {}
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('분석설정.json 형식 확인이 필요합니다.')
    return {name:validate_preset(value) for name,value in data.items()}


def trend_rows(history,scope,unit,section,path,preset,years=()):
    """연도 중간의 누락/읽기 실패도 공란 행으로 보존한다."""
    all_years=set(history)|set(years)
    if not all_years:return []
    result=[]
    for number in range(min(map(int,all_years)),max(map(int,all_years))+1):
        year=str(number);data=history.get(year)
        if data is None:result.append([year,None,None,None]);continue
        denom,_,_=denominator(data,preset)
        _,value=analysis_rows(data,None,scope,unit,section,path,denom)
        result.append([year,value,denom,ratio(value,denom)])
    return result


def appendix_check(source):
    from statement_appendix import run_statement_appendix_verification
    attached=discover_appendices(source)
    if not any(attached.values()):return [],['부속명세서 없음']
    result=run_statement_appendix_verification('.',str(source),*(str(attached[k]) if attached[k] else None for k in ('재무상태표','운영계산서')))
    rows=[]
    for item in result['items']:
        missing=item['fs_amount'] is None or item['supp_amount'] is None
        rows.append([item['category'],item['account'],item['fs_amount'],item['supp_amount'],None if missing else item['diff'],
                     '자료 필요' if missing else ('일치' if item['is_match'] else '차이'),item['supp_sheet']])
    notes=[f'{k} 부속명세서 없음' for k,v in attached.items() if v is None]
    notes+=['기존 매핑 기반 대사: 감가상각/사용수익권 절댓값 비교, 1원 미만 차이 일치, 양쪽 0 항목 생략. 전체 결산 적정성 판정 아님.']
    notes += [f'{k}: {v}' for k,v in attached.items() if v]
    return rows,notes


def ledger_matches(record,scope,unit,path):
    name=normalize(record['회계단위']);non='비등록금' in name
    if scope=='등록금' and non:return False
    if scope=='비등록금' and not non:return False
    if unit!='합계' and name.replace('비등록금','').replace('등록금','')!=unit:return False
    return all(normalize(record[k])==normalize(v) for k,v in zip(('관','항','목'),path))


def export_report(target,rows,basis,denom_details,trend,checks,notes,base=None,denom=None,series=None,statement='자금계산서',source_summary=None):
    from analysis_presentation import analysis_total,trend_total,complete_sum,pie_values,unit_label
    wb=Workbook();wb.remove(wb.active)
    amount_label='결산' if statement=='자금계산서' else '당기'
    total_row=analysis_total(rows,base,denom)
    if source_summary is not None:
        label,value,percent,delta=source_summary
        prior=value-delta if value is not None and delta is not None else None
        total_row=[label,value,percent,ratio(value,denom),prior,delta,ratio(delta,prior),'원본 총계']
    sections=[('과목별 분석',[h.replace('결산',amount_label) for h in ANALYSIS_HEADERS],[v['values'] for v in rows]+[total_row]),
              ('원본 금액', ['원본 파일','시트','셀','과목','금액','상태'],basis),
              ('분모 근거',['구분','회계단위','과목','금액','원본 파일','시트','셀'],
               [[r[0],unit_label(r[1]),*r[2:]] for r in denom_details]+[['합계','','',complete_sum(r[3] for r in denom_details),'','','']]),
              ('연도별 비교',['연도',f'선택 과목 {amount_label}','선택 분모','분모 대비(%)'],trend+[trend_total(trend)]),
              ('부속명세서 대사',['구분','과목','재무제표','부속명세서','차이','결과','부속 시트'],checks),
              ('분석 기준',['항목','내용'],[[str(i+1),n] for i,n in enumerate(notes)])]
    for title,headers,values in sections:
        ws=wb.create_sheet(title);append_row(ws,headers)
        for row in values:append_row(ws,row)
        format_sheet(ws)
    from openpyxl.chart import PieChart,LineChart,Reference
    from openpyxl.chart.label import DataLabelList
    graph=wb.create_sheet('그래프');append_row(graph,['과목 (양수 결산만 · 0/음수/누락 제외)','결산'])
    slices=pie_values(rows)
    for label,value in slices:append_row(graph,[label,value])
    if slices:
        chart=PieChart();chart.title=f'{statement} 양수 {amount_label} 구성비';chart.width=26;chart.height=15
        chart.dataLabels=DataLabelList();chart.dataLabels.showCatName=True;chart.dataLabels.showVal=True;chart.dataLabels.showPercent=True;chart.dataLabels.numFmt='#,##0,,"백만원"'
        chart.add_data(Reference(graph,min_col=2,min_row=1,max_row=len(slices)+1),titles_from_data=True)
        chart.set_categories(Reference(graph,min_col=1,min_row=2,max_row=len(slices)+1));graph.add_chart(chart,'D2')
    if trend:
        chart=LineChart();chart.title=f'{statement} {amount_label} 추이 (백만원)';chart.display_blanks='gap';chart.width=26;chart.height=12
        chart.y_axis.numFmt='#,##0,,';chart.y_axis.title='백만원'
        chart.dataLabels=DataLabelList();chart.dataLabels.showVal=True;chart.dataLabels.numFmt='#,##0,,'
        if series and len(series[0])>1:
            headers,values=series;ws=wb.create_sheet('선택 과목 연도별 비교');append_row(ws,headers)
            for row in values:append_row(ws,row)
            append_row(ws,['조회 연도 합계']+[complete_sum(r[i] for r in values) for i in range(1,len(headers))])
            format_sheet(ws);count=len(values);last_col=len(headers)
        else:ws=wb['연도별 비교'];count=len(trend);last_col=2
        chart.add_data(Reference(ws,min_col=2,max_col=last_col,min_row=1,max_row=count+1),titles_from_data=True)
        chart.set_categories(Reference(ws,min_col=1,min_row=2,max_row=count+1));graph.add_chart(chart,'D32')
    for title,columns in [('과목별 분석',(3,4,7)),('연도별 비교',(4,))]:
        for row in wb[title].iter_rows(min_row=2):
            for column in columns:row[column-1].number_format='0.00"%"'
    format_sheet(graph)
    return save_atomic(wb,target)
