"""Adapt bundled databases to the reference analysis engines without PC source paths."""
from pathlib import Path
import hashlib,tempfile,threading
from contextlib import closing
from functools import lru_cache
from statement_database import DATABASE,StatementSource,read_workbook,connect,discover_statements,iter_analysis_sheets
from statement_catalog import discover_years

_lock=threading.Lock()
_audit_cache={}


def statement_databases():
    from appendix_view import SOURCES
    return [('재무제표',DATABASE),*SOURCES.items()]


def statement_signature():
    files=[]
    for _,database in statement_databases():
        stat=database.stat()
        files.append((database,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns))
    return tuple(files)


@lru_cache(maxsize=1)
def statement_cache_path(signature):
    digest=hashlib.sha256(b'analysis-db-adapter-v1')
    for database,*_ in signature:
        with database.open('rb') as stream:
            for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return Path(tempfile.gettempdir())/'WorkSpace-analysis'/digest.hexdigest()/'settings'/'finance statement'


def statement_folder(year=None):
    from finance_data import save_atomic
    folder=statement_cache_path(statement_signature())
    with _lock:
        folder.mkdir(parents=True,exist_ok=True)
        for category,database in statement_databases():
            with closing(connect(database)) as connection:
                years=[str(year) for year, in connection.execute('SELECT fiscal_year FROM workbooks ORDER BY fiscal_year DESC')]
            for selected in years:
                if year is not None and selected!=str(year):continue
                name=f'{selected}회계연도.xlsx' if category=='재무제표' else f'{selected}회계연도 대학 {category} 부속명세서.xlsx'
                if not (folder/name).is_file():
                    save_atomic(read_workbook(StatementSource(database,selected)),folder/name)
    return folder


def program_statement_paths(*,materialize=True):
    if materialize:return discover_years(statement_folder())
    folder=statement_cache_path(statement_signature())
    return {year:folder/f'{year}회계연도.xlsx' for year in discover_statements(DATABASE)}


@lru_cache(maxsize=1)
def cached_statement_order(signature):
    from audit_review import load_statement_history
    from statement_database import load_record
    folder=statement_cache_path(signature)
    sources=discover_statements(signature[0][0])
    paths={year:folder/f'{year}회계연도.xlsx' for year in sources}
    return load_statement_history(folder.parent,paths=paths,reader=lambda year,path:load_record(sources[year]))


def load_program_statement_history():
    return cached_statement_order(statement_signature())


@lru_cache(maxsize=1)
def cached_analysis_history(signature):
    from financial_analysis import ANALYSIS_SHEETS,analysis_year
    from statement_analysis import normalize
    history={};issues=[];paths={}
    folder=statement_cache_path(signature)
    for year,source in discover_statements(signature[0][0]).items():
        path=paths[year]=folder/f'{year}회계연도.xlsx'
        try:
            history[year]=analysis_year(path,iter_analysis_sheets(source,lambda title:normalize(title) in ANALYSIS_SHEETS))
        except Exception as error:issues.append(f'{year}: {error}')
    return history,issues,paths


def load_analysis_history(unused_folder=None,*,materialize_sources=True):
    if materialize_sources:statement_folder()
    return cached_analysis_history(statement_signature())


def program_ledger_paths(settings):
    from finance_data import discover_ledger_years
    from ledger_database import discover_years as database_years,registered_database
    external=discover_ledger_years(Path(settings)/'lodges')
    external.update(database_years())
    registered = registered_database(settings)
    if registered.is_file():
        external.update(database_years(registered))
    return dict(sorted(external.items(),reverse=True))


def load_program_ledger(path,year,*,subject=None):
    from ledger_database import iter_records
    from finance_data import load_ledger
    path=Path(path)
    if path.suffix!='.sqlite3':
        records=load_ledger(path,with_provenance=True)
        if subject is None:return records
        from statement_analysis import normalize
        return [record for record in records if normalize(record['목'])==subject]
    return list(iter_records(path,year,with_provenance=True,subject=subject))


def load_audit_sources(settings,year=None):
    from audit_review import AccountOrder,inspect_record
    paths=program_ledger_paths(settings)
    folder=statement_cache_path(statement_signature())
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
    history,notes,statement_paths=load_program_statement_history()
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
        return path,load_program_ledger(path,year,subject='등록금회계전입금')
    return load_reserves(settings,year,statement,ledger_loader=ledger,statement_record=statement_record)
