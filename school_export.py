"""Calibrated, foreground-only school export; no application launch or login."""
import threading
import time
from tempfile import TemporaryDirectory
from pathlib import Path

KINDS = ('매입세금계산서', '매입계산서', '매출세금계산서', '매출계산서')
POINTS = ('매입', '매출', '세금계산서', '계산서', '조회', '상단 합계표')
RUN_LOCK = threading.Lock()
DEFAULT_POINTS = {'매입': [865, 211], '매출': [920, 209],
                  '세금계산서': [1042, 206], '계산서': [1128, 210],
                  '조회': [1139, 174], '상단 합계표': [851, 333]}
DEFAULT_MENU_POINT = [100, 152]


def default_profile(size, dpi):
    profile = {'version': 1, 'size': list(size), 'dpi': dpi,
               'points': {name: list(point) for name, point in DEFAULT_POINTS.items()},
               'excel_menu': {'point': list(DEFAULT_MENU_POINT)}}
    validate_profile(profile)
    return profile



class ExportError(Exception):
    pass


def validate_profile(profile):
    try:
        if profile.get('version') != 1 or set(profile.get('points', {})) != set(POINTS):
            raise ValueError()
        width, height = profile['size']
        if width <= 0 or height <= 0 or profile['dpi'] <= 0:
            raise ValueError()
        for x, y in profile['points'].values():
            if not (0 <= x < width and 0 <= y < height):
                raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ExportError('버튼 위치 6개를 학사 창 안에서 다시 지정하세요.') from None


def validate_export(path):
    from verifier import open_legacy_workbook
    book = open_legacy_workbook(path)
    try:
        sheet = book.sheet_by_index(0)
        headers = {str(v).replace(' ', '').strip() for r in range(min(10, sheet.nrows)) for v in sheet.row_values(r)}
        if not {'거래처명', '공급가액'}.issubset(headers) or not headers.intersection({'사업자번호', '사업자등록번호'}):
            raise ExportError('상단 합계표 형식이 아닙니다. 상단 합계표 위치를 다시 지정하세요.')
    finally:
        book.release_resources()


class ExportRunner:
    def __init__(self, backend, stop, progress, validator=validate_export):
        self.backend, self.stop, self.progress, self.validator = backend, stop, progress, validator

    def check(self):
        if self.stop.is_set() or self.backend.escape_pressed():
            raise ExportError('사용자가 중단했습니다.')
        self.backend.check()

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check()
            self.stop.wait(min(.1, max(0, deadline - time.monotonic())))
        self.check()

    def run(self, folder, kinds, delay=.3):
        if not kinds or any(k not in KINDS for k in kinds):
            raise ExportError('자료 종류를 확인하세요.')
        if not .3 <= delay <= 30:
            raise ExportError('조회 대기는 0.3~30초로 지정하세요.')
        folder = Path(folder).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        # Reject before any clicks, including differently suffixed existing source files.
        for kind in kinds:
            if list(folder.glob(f'학사{kind}.*')):
                raise ExportError(f'학사{kind} 파일이 이미 있습니다. 기존 파일을 다른 폴더로 옮긴 후 실행하세요.')
        with TemporaryDirectory(prefix='workspace_school_',ignore_cleanup_errors=True) as staging:
            return self._run_staged(folder,kinds,delay,Path(staging))

    def _run_staged(self,folder,kinds,delay,staging):
        saved = []
        for kind in kinds:
            self.check()
            self.progress(kind, '조회 중', '')
            self.backend.click('매입' if kind.startswith('매입') else '매출')
            self.wait(.3)
            self.backend.click('세금계산서' if '세금' in kind else '계산서')
            self.wait(.3)
            self.backend.click('조회')
            self.wait(delay)
            self.backend.ready()
            self.backend.open_excel(self.check)
            self.progress(kind, '저장 중', '')
            temporary = staging / f'학사{kind}.xls'
            self.backend.save_as(temporary, self.check)
            deadline = time.monotonic() + 45
            previous = None
            stable = 0
            while time.monotonic() < deadline:
                self.wait(.1)
                if not temporary.exists():
                    continue
                stat = temporary.stat()
                current = (stat.st_size, stat.st_mtime_ns)
                stable = stable + 1 if current == previous and stat.st_size else 0
                previous = current
                if stable >= 2:
                    try:
                        self.validator(temporary)
                        verified = temporary.stat()
                        if (verified.st_size, verified.st_mtime_ns) != current:
                            stable = 0
                            continue
                        break
                    except ExportError:
                        raise
                    except (OSError, ValueError):
                        continue
            else:
                raise ExportError(f'{kind}: 45초 안에 정상 XLS 저장을 확인하지 못했습니다. 학사 창과 월 폴더의 저장 결과를 확인하세요.')
            self.check()
            destination = folder / temporary.name
            # Exclusive publication prevents overwriting files created during the run.
            created = False
            try:
                with destination.open('xb') as out:
                    created = True
                    with temporary.open('rb') as source:
                        import shutil
                        shutil.copyfileobj(source, out)
            except FileExistsError:
                raise ExportError(f'{destination.name}: 기존 파일이 있어 중단했습니다.') from None
            except OSError:
                if created:
                    destination.unlink(missing_ok=True)
                raise
            temporary.unlink()
            saved.append(destination)
            self.progress(kind, '저장 완료', str(destination))
        return saved
