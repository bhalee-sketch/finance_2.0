"""Reset only canonical downloaded tax-invoice inputs, using the recycle bin."""
from pathlib import Path
from verifier import KINDS


def reset_candidates(folder):
    folder = Path(folder)
    names = {source + kind for source in ('학사', '홈택스') for kind in KINDS}
    if not folder.exists():
        return []
    if folder.is_symlink():
        raise ValueError('연결된 폴더는 초기화할 수 없습니다.')
    return sorted((p for p in folder.iterdir() if p.is_file() and not p.is_symlink()
                   and p.stem in names and p.suffix.lower() in ('.xls', '.xlsx', '.xlsm')),
                  key=lambda p: p.name)


def recycle_inputs(folder, approved):
    from send2trash import send2trash
    allowed = set(reset_candidates(folder))
    moved, failed = [], []
    for path in approved:
        path = Path(path)
        if path not in allowed:
            failed.append(f'{path.name}: 파일이 변경되었거나 초기화 대상이 아닙니다.')
            continue
        try:
            send2trash(str(path.absolute()))
            moved.append(path)
        except OSError as exc:
            failed.append(f'{path.name}: {exc}')
    return moved, failed
