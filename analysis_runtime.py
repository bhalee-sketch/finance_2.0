"""Adapt bundled databases to the reference analysis engines without PC source paths."""
from pathlib import Path
import hashlib,json,tempfile,threading
from statement_database import DATABASE,StatementSource,read_workbook,connect
from statement_catalog import discover_years

_lock=threading.Lock()
_audit_cache={}


def statement_folder():
    from appendix_view import SOURCES
    databases=[DATABASE,*SOURCES.values()]
    digest=hashlib.sha256(b'analysis-db-adapter-v1')
    for database in databases:digest.update(database.read_bytes())
    folder=Path(tempfile.gettempdir())/'WorkSpace-analysis'/digest.hexdigest()/'settings'/'finance statement'
    with _lock:
        marker=folder/'ready.json'
        if marker.exists():
            names=json.loads(marker.read_text())
            if all((folder/name).is_file() for name in names):return folder
        folder.mkdir(parents=True,exist_ok=True)
        names=[]
        for category,database in [('재무제표',DATABASE),*SOURCES.items()]:
            with connect(database) as connection:
                years=[str(year) for year, in connection.execute('SELECT fiscal_year FROM workbooks ORDER BY fiscal_year DESC')]
            for year in years:
                name=f'{year}회계연도.xlsx' if category=='재무제표' else f'{year}회계연도 대학 {category} 부속명세서.xlsx'
                book=read_workbook(StatementSource(database,year))
                try:book.save(folder/name)
                finally:book.close()
                names.append(name)
        marker.write_text(json.dumps(names,ensure_ascii=False))
    return folder


def program_statement_paths():return discover_years(statement_folder())


def load_analysis_history(unused_folder=None):
    from financial_analysis import load_history
    return load_history(statement_folder())


def program_ledger_paths(settings):
    from finance_data import discover_ledger_years
    from ledger_database import discover_years as database_years
    external=discover_ledger_years(Path(settings)/'lodges')
    external.update(database_years())
    return dict(sorted(external.items(),reverse=True))


def load_program_ledger(path,year):
    from ledger_database import load_records
    from finance_data import load_ledger
    path=Path(path)
    if path.suffix!='.sqlite3':return load_ledger(path,with_provenance=True)
    records=load_records(path,year)
    with connect(path) as connection:
        source_rows=[row for row, in connection.execute('SELECT source_row FROM entries WHERE fiscal_year=? ORDER BY source_row',(str(year),))]
    for record,row in zip(records,source_rows):
        record.update(_source_file=str(path),_source_row=row)
    return records


def load_audit_sources(settings,year=None):
    from audit_review import load_statement_history,AccountOrder,inspect_record
    paths=program_ledger_paths(settings)
    folder=statement_folder()
    selected=[str(year)] if year is not None and str(year) in paths else list(paths) if year is None else []
    signature=(tuple((y,str(paths[y]),paths[y].stat().st_mtime_ns) for y in selected),tuple(paths),str(folder))
    if signature in _audit_cache:return _audit_cache[signature]
    records=[];issues=[]
    for requested in selected:
        try:
            data=load_program_ledger(paths[requested],requested)
            for record in data:record['_file_year']=requested
            records.extend(data)
        except Exception as error:issues.append(f'{requested} 원장: {error}')
    history,notes,statement_paths=load_statement_history(folder.parent)
    issues.extend(notes)
    if not selected:issues.append('선택연도의 원장 자료가 없습니다.')
    order=AccountOrder(history,records);records.sort(key=order.key)
    result={'reviews':[inspect_record(record) for record in records],'history':history,'order':order,'issues':issues,
            'ledger_years':list(paths),'sources':[str(p) for p in [*paths.values(),*statement_paths.values()]]}
    _audit_cache.clear();_audit_cache[signature]=result
    return result


def load_program_reserves(settings,year,statement,*,statement_record=None):
    from reserve_review import load_reserves
    def ledger(settings,year):
        path=program_ledger_paths(settings).get(str(year))
        if path is None:raise ValueError('선택연도 원장 자료가 없습니다.')
        return path,load_program_ledger(path,year)
    return load_reserves(settings,year,statement,ledger_loader=ledger,statement_record=statement_record)
