"""드롭 및 파일 대화상자의 동일한 파일 검증."""
from pathlib import Path


def excel_paths(names,existing=()):
    seen={Path(p).resolve() for p in existing};valid=[];rejected=[]
    for name in names:
        p=Path(name)
        if not p.is_file() or p.suffix.lower() not in ('.xls','.xlsx','.xlsm') or p.name.startswith('~$'):
            rejected.append(p.name);continue
        resolved=p.resolve()
        if resolved not in seen:valid.append(p);seen.add(resolved)
    return valid,rejected
