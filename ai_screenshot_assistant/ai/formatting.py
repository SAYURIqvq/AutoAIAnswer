from __future__ import annotations

import re

SQL_KEYWORDS = (
    "SELECT",
    "FROM",
    "WHERE",
    "GROUP BY",
    "ORDER BY",
    "HAVING",
    "LIMIT",
    "OFFSET",
    "INSERT INTO",
    "VALUES",
    "UPDATE",
    "SET",
    "DELETE FROM",
    "CREATE TABLE",
    "ALTER TABLE",
    "DROP TABLE",
    "INNER JOIN",
    "LEFT JOIN",
    "RIGHT JOIN",
    "FULL JOIN",
    "JOIN",
    "ON",
)

_SQL_START = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)\b",
    re.IGNORECASE,
)
_SQL_FENCE = re.compile(r"```sql\s*\n?([\s\S]*?)```", re.IGNORECASE)
_ANSWER_PREFIX = re.compile(r"^(答案[:：]\s*)(.+?)(\s+解析[:：].*)?$", re.MULTILINE | re.DOTALL)
_CLAUSE_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(keyword).replace(r"\ ", r"\s+") for keyword in sorted(SQL_KEYWORDS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def format_ai_output(text: str) -> str:
    text = _normalize_answer_fence_spacing(_format_sql_fences(text))
    if "```sql" in text.lower() or not _SQL_START.search(text):
        return text
    return _wrap_answer_sql(text)


def format_sql(sql: str) -> str:
    sql = _normalize_sql(sql)
    if not sql:
        return sql

    matches = list(_CLAUSE_PATTERN.finditer(sql))
    if not matches:
        return sql

    lines: list[str] = []
    for index, match in enumerate(matches):
        keyword = _keyword_label(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(sql)
        body = sql[start:end].strip()
        if keyword == "SELECT":
            lines.append("SELECT")
            lines.extend(f"    {part}" for part in _split_select_items(body))
        else:
            lines.append(keyword)
            if body:
                lines.append(f"    {body}")
    return "\n".join(line for line in lines if line.strip())


def _format_sql_fences(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return "```sql\n" + format_sql(match.group(1)) + "\n```"

    return _SQL_FENCE.sub(replace, text)


def _normalize_answer_fence_spacing(text: str) -> str:
    return re.sub(r"(答案[:：])\s*(```sql)", r"\1\n\2", text, flags=re.IGNORECASE)


def _wrap_answer_sql(text: str) -> str:
    match = _ANSWER_PREFIX.match(text.strip())
    if not match:
        return text

    prefix, answer, reason = match.groups()
    if not _SQL_START.search(answer):
        return text
    sql, suffix = _split_sql_and_suffix(answer)
    formatted = f"{prefix}\n```sql\n{format_sql(sql)}\n```"
    if suffix:
        formatted += "\n" + suffix.strip()
    if reason:
        formatted += "\n" + reason.strip()
    return formatted


def _split_sql_and_suffix(value: str) -> tuple[str, str]:
    semicolon = value.find(";")
    if semicolon >= 0:
        return value[: semicolon + 1].strip(), value[semicolon + 1 :].strip()
    return value.strip(), ""


def _normalize_sql(sql: str) -> str:
    sql = sql.strip().strip("`")
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"\s*,\s*", ", ", sql)
    sql = re.sub(r"\s*;\s*$", ";", sql)
    return sql


def _keyword_label(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword).upper()


def _split_select_items(body: str) -> list[str]:
    if not body:
        return []
    pieces = [piece.strip() for piece in body.split(",")]
    return [piece + ("," if index < len(pieces) - 1 else "") for index, piece in enumerate(pieces) if piece]
