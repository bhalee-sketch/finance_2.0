"""Persistent, per-task work records in the user's settings directory."""
from contextlib import closing, contextmanager
from pathlib import Path
import re
import sqlite3


CASHBOOK = '수입·지출'
SECTIONS = {
    CASHBOOK: ('거래일', '재원·입금 건', '입금처·사용처', '용도·내용', '거래 방식', '수입액', '지출액'),
    '서류 목록': ('서류명', '준비·발급처', '제출·보관처', '비고'),
    '업무 흐름': ('처리 단계', '처리 내용', '담당', '결과물'),
    '회계분개 규칙': ('적용 조건', '차변 계정', '대변 계정', '분개 예시·비고'),
    '일정': ('일자·주기', '할 일', '담당', '진행 상태'),
}
FIELDS = tuple(f'value{i+1}' for i in range(max(map(len, SECTIONS.values()))))


def _import_cell(value):
    if not value:
        return ''
    if re.match(r'=\s*SUM\b', value.lstrip(), re.I):
        def shift_row(match):
            row = int(match[2])
            return match[1] + str(row + 1) if row < 1048576 else match[0]
        return re.sub(r'(\$?[A-Z]{1,3}\$?)([1-9][0-9]{0,6})(?![0-9])', shift_row, value, flags=re.I)
    if value.lstrip().startswith('=') or value.startswith("'"):
        return "'" + value
    return value


class RecordBook:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)')
            db.execute("""CREATE TABLE IF NOT EXISTS grid_cells (
                task INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                row_num INTEGER NOT NULL, col_num INTEGER NOT NULL, value TEXT NOT NULL,
                PRIMARY KEY(task, row_num, col_num))""")
            db.execute("""CREATE TABLE IF NOT EXISTS grid_widths (
                task INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                col_num INTEGER NOT NULL, width INTEGER NOT NULL, PRIMARY KEY(task, col_num))""")
            if db.execute('PRAGMA user_version').fetchone()[0] == 0:
                self._import_previous_forms(db)
                db.execute('PRAGMA user_version=1')

    @staticmethod
    def _import_previous_forms(db):
        # Keep each original sheet's coordinate space separate, including references to blank cells.
        db.execute("UPDATE grid_cells SET value=? || value WHERE substr(value,1,1)=?", ("'", "'"))
        task_columns = {row[1] for row in db.execute('PRAGMA table_info(tasks)')}
        memo = 'memo' if 'memo' in task_columns else "''"
        fields = [row[1] for row in db.execute('PRAGMA table_info(entries)') if row[1] in FIELDS]
        for task, name, note in db.execute(f'SELECT id,name,{memo} FROM tasks').fetchall():
            occupies_sheet = db.execute('SELECT 1 FROM grid_cells WHERE task=? LIMIT 1', (task,)).fetchone()

            def write_sheet(title, rows):
                nonlocal occupies_sheet
                target = task
                if occupies_sheet:
                    base = f'{name} · {title}'
                    candidate = base
                    suffix = 2
                    while db.execute('SELECT 1 FROM tasks WHERE name=?', (candidate,)).fetchone():
                        candidate = f'{base} ({suffix})'
                        suffix += 1
                    target = db.execute('INSERT INTO tasks(name) VALUES(?)', (candidate,)).lastrowid
                db.executemany('INSERT INTO grid_cells VALUES(?,?,?,?)',
                               ((target, r, c, value) for r, row in enumerate(rows)
                                for c, value in enumerate(row) if value))
                occupies_sheet = True

            if note:
                memo_rows = [(("'" + line if line else ''),) for line in note.splitlines()]
                write_sheet('메모', memo_rows)
            for section, headers in SECTIONS.items():
                columns = [field for field in FIELDS[:len(headers)] if field in fields]
                if not columns:
                    continue
                records = db.execute(f"SELECT {', '.join(columns)} FROM entries WHERE task=? AND section=? "
                                     'ORDER BY position,id', (task, section)).fetchall()
                if records:
                    # Row 1 now contains editable headings. Move SUM references with their source rows.
                    rows = [headers]
                    for record in records:
                        rows.append([_import_cell(value) for value in record])
                    write_sheet(section, rows)

    @contextmanager
    def transaction(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            yield db

    def tasks(self):
        with self.transaction() as db:
            return db.execute('SELECT id, name FROM tasks ORDER BY name, id').fetchall()

    def name_task(self, name, task=None):
        name = name.strip()
        if not name:
            raise ValueError('업무명을 입력해 주세요.')
        with self.transaction() as db:
            try:
                if task is None:
                    return db.execute('INSERT INTO tasks(name) VALUES (?)', (name,)).lastrowid
                db.execute('UPDATE tasks SET name=? WHERE id=?', (name, task))
            except sqlite3.IntegrityError as error:
                raise ValueError('같은 이름의 업무가 있습니다.') from error
            return task

    def delete_task(self, task):
        with self.transaction() as db:
            db.execute('DELETE FROM tasks WHERE id=?', (task,))

    def grid_values(self, task):
        with self.transaction() as db:
            return {(r, c): value for r, c, value in db.execute(
                'SELECT row_num,col_num,value FROM grid_cells WHERE task=?', (task,))}

    def save_grid(self, task, changes):
        with self.transaction() as db:
            db.executemany('INSERT INTO grid_cells VALUES(?,?,?,?) ON CONFLICT(task,row_num,col_num) '
                           'DO UPDATE SET value=excluded.value',
                           ((task, r, c, value) for (r, c), value in changes.items() if value))
            db.executemany('DELETE FROM grid_cells WHERE task=? AND row_num=? AND col_num=?',
                           ((task, r, c) for (r, c), value in changes.items() if not value))

    def grid_widths(self, task):
        with self.transaction() as db:
            return dict(db.execute('SELECT col_num,width FROM grid_widths WHERE task=?', (task,)))

    def save_grid_widths(self, task, widths):
        with self.transaction() as db:
            db.executemany('INSERT OR REPLACE INTO grid_widths VALUES(?,?,?)',
                           ((task, col, width) for col, width in widths.items()))
