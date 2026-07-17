"""CSV formula-injection neutralization (SECURITY M-3).

Spreadsheet apps (Excel, Sheets, LibreOffice) execute cells that start with
= + - @ or a tab/CR as formulas when a CSV is opened. Any cell built from
user-controlled text (titles, results, names) must be passed through
neutralize() before being written to an export.
"""

_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def neutralize(value) -> str:
    """Prefix values that a spreadsheet would treat as formulas with `'`.

    Non-string values (numbers, None already handled by callers) pass through
    str() untouched unless their rendering starts with a trigger character.
    """
    s = value if isinstance(value, str) else str(value)
    if s.startswith(_FORMULA_TRIGGERS):
        return "'" + s
    return s
