"""Persistent, per-task work records in the user's settings directory."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


SECTIONS = {
    '서류 목록': ('서류명', '준비·발급처', '제출·보관처', '비고'),
    '업무 흐름': ('처리 단계', '처리 내용', '담당', '결과물'),
    '회계분개 규칙': ('적용 조건', '차변 계정', '대변 계정', '분개 예시·비고'),
    '일정': ('일자·주기', '할 일', '담당', '진행 상태'),
}
FIELDS = ('value1', 'value2', 'value3', 'value4')


class RecordBook:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)')
            db.execute("""CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                section TEXT NOT NULL, position INTEGER NOT NULL, value1 TEXT NOT NULL DEFAULT '',
                value2 TEXT NOT NULL DEFAULT '', value3 TEXT NOT NULL DEFAULT '', value4 TEXT NOT NULL DEFAULT ''
            )""")
            db.execute('CREATE INDEX IF NOT EXISTS entry_order ON entries(task, section, position)')

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

    def rows(self, task, section):
        with self.transaction() as db:
            return db.execute('SELECT id, value1, value2, value3, value4 FROM entries '
                              'WHERE task=? AND section=? ORDER BY position, id', (task, section)).fetchall()

    def write_cells(self, task, section, row_ids, column, values):
        """Commit one edit or pasted rectangle together, appending missing rows."""
        row_id = None
        with self.transaction() as db:
            for index, cells in enumerate(values):
                if column < 0 or not cells or column + len(cells) > len(FIELDS):
                    raise ValueError('표의 열 개수에 맞춰 붙여넣어 주세요.')
                if index < len(row_ids):
                    row_id = row_ids[index]
                else:
                    row_id = db.execute(
                        'INSERT INTO entries(task,section,position) SELECT ?,?,COALESCE(MAX(position),0)+1 '
                        'FROM entries WHERE task=? AND section=?', (task, section, task, section)).lastrowid
                fields = ', '.join(field + '=?' for field in FIELDS[column:column + len(cells)])
                changed = db.execute(f'UPDATE entries SET {fields} WHERE id=? AND task=? AND section=?',
                                     (*cells, row_id, task, section))
                if not changed.rowcount:
                    raise ValueError('다른 창에서 삭제된 행입니다. 현재 목록을 다시 확인해 주세요.')
        return row_id

    def delete_row(self, row_id):
        with self.transaction() as db:
            db.execute('DELETE FROM entries WHERE id=?', (row_id,))

    def move_row(self, task, section, row_id, direction):
        with self.transaction() as db:
            db.execute('BEGIN IMMEDIATE')
            order = db.execute('SELECT id, position FROM entries WHERE task=? AND section=? ORDER BY position, id',
                               (task, section)).fetchall()
            ids = [entry[0] for entry in order]
            if row_id not in ids:
                return
            index = ids.index(row_id)
            target = index + direction
            if 0 <= target < len(order):
                other_id, other_position = order[target]
                db.executemany('UPDATE entries SET position=? WHERE id=?',
                               [(other_position, row_id), (order[index][1], other_id)])
