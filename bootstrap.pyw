"""콘솔 없는 Windows 실행과 오류 안내."""
import os
import sys
import traceback
from pathlib import Path

base = Path(__file__).resolve().parent
os.chdir(base)
(base/'logs').mkdir(exist_ok=True)
log = (base/'logs'/'app.log').open('a', encoding='utf-8', buffering=1)
original_stdout, original_stderr = sys.stdout, sys.stderr
sys.stdout = sys.stderr = log


def show_error(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb, file=log)
    try:
        from qt_ui import messagebox
        messagebox.showerror('업무 도구 실행 오류',
            f'프로그램 실행 중 오류가 발생했습니다.\n{exc}\n\n오류 기록: {base / "logs" / "app.log"}')
    except Exception:
        traceback.print_exc(file=log)


try:
    import qt_ui as tk
    tk.Tk.report_callback_exception = lambda self, kind, value, tb: show_error(kind,value,tb)
    from app import main
    main()
except Exception:
    show_error(*sys.exc_info())
    raise SystemExit(1)
finally:
    sys.stdout, sys.stderr = original_stdout, original_stderr
    log.close()
