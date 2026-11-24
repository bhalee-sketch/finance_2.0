"""SUM references are local to the visible task sheet, using A1 coordinates."""
from decimal import Decimal
from graphlib import CycleError, TopologicalSorter
import re

_AMOUNT = re.compile(r'([+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?)\s*원?')
_SUM = re.compile(r'=\s*SUM\b', re.I)
_ARGUMENTS = re.compile(r'=\s*SUM\s*\(([^()]*)\)', re.I)
_CELL = re.compile(r'\$?([A-Z])\$?([1-9][0-9]{0,6})', re.I)


def _address(text, columns):
    match = _CELL.fullmatch(text.strip())
    if not match:
        raise ValueError('#REF!')
    column = ord(match[1].upper()) - ord('A')
    row = int(match[2])
    if column >= columns or row > 1048576:
        raise ValueError('#REF!')
    return row - 1, column


def _ranges(formula, height, columns):
    match = _ARGUMENTS.fullmatch(formula)
    if not match or not match[1].strip():
        raise ValueError('#VALUE!')
    for argument in match[1].split(','):
        first, separator, last = argument.partition(':')
        row, column = _address(first, columns)
        end_row, end_col = _address(last, columns) if separator else (row, column)
        yield (min(row, end_row), min(height, max(row, end_row) + 1),
               min(column, end_col), max(column, end_col) + 1)


def _references(ranges):
    for top, bottom, left, right in ranges:
        for row in range(top, bottom):
            for column in range(left, right):
                yield row, column


def sheet_values(rows):
    """Return numeric cells and formula errors. All other text is ignored by SUM."""
    values = {}
    formulas = {}
    for row, cells in enumerate(rows):
        for column, raw in enumerate(cells):
            text = raw.strip()
            key = (row, column)
            if _SUM.match(text):
                try:
                    formulas[key] = list(_ranges(text, len(rows), len(cells)))
                except ValueError as error:
                    values[key] = str(error)
            else:
                match = _AMOUNT.fullmatch(text)
                if match:
                    values[key] = Decimal(match[1].replace(',', ''))

    order = TopologicalSorter()
    for key, ranges in formulas.items():
        order.add(key, *(ref for ref in _references(ranges) if ref in formulas))
    try:
        order.prepare()
    except CycleError:
        pass  # Unrelated formulas can still be calculated.
    while order.is_active():
        for key in order.get_ready():
            total = Decimal(0)
            for ref in _references(formulas[key]):
                value = values.get(ref)
                if isinstance(value, str):
                    total = value
                    break
                if value is not None:
                    total += value
            values[key] = total
            order.done(key)
    for key in formulas.keys() - values.keys():
        values[key] = '#순환참조!'
    return values
