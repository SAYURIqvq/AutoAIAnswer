from __future__ import annotations

import json
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
_ALTER_TABLE_PATTERN = re.compile(
    r"^ALTER\s+TABLE\s+(`[^`]+`|\"[^\"]+\"|[\w.]+)\s+(.+?);?$",
    re.IGNORECASE | re.DOTALL,
)
_ANSWER_LABEL = re.compile(r"答案\s*[:：]")
_REASON_LABEL = re.compile(r"解析\s*[:：]")
_CHOICE_IN_REASON = re.compile(r"(?:选|选择|应选|答案是)\s*([A-H](?:\s*[、,/]\s*[A-H])*)", re.IGNORECASE)


def format_ai_output(text: str) -> str:
    text = ensure_answer_first(text)
    text = _normalize_answer_fence_spacing(_format_sql_fences(text))
    if "```sql" in text.lower() or not _SQL_START.search(text):
        return text
    return _wrap_answer_sql(text)


def ensure_answer_first(text: str) -> str:
    """Guarantee a visible answer line before any explanation text."""
    value = (text or "").strip()
    if not value:
        return "答案：无法确定\n解析：未能从截图中识别出可确认的答案。"

    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and "answer" in payload:
        answer = str(payload.get("answer") or "无法确定").strip()
        reason = str(payload.get("reason") or "未提供解析。").strip()
        return f"答案：{answer}\n解析：{reason}"
    if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
        lines: list[str] = []
        for index, item in enumerate(payload["questions"], start=1):
            if not isinstance(item, dict):
                continue
            answer = str(item.get("answer") or "无法确定").strip()
            reason = str(item.get("reason") or "未提供解析。").strip()
            lines.append(f"【第{index}题】\n答案：{answer}\n解析：{reason}")
        if lines:
            return "\n\n".join(lines)

    answer_match = _ANSWER_LABEL.search(value)
    reason_match = _REASON_LABEL.search(value)
    if answer_match and (reason_match is None or answer_match.start() < reason_match.start()):
        return value

    if reason_match is not None:
        reason = value[reason_match.end():].strip()
        candidate = _CHOICE_IN_REASON.search(reason)
        answer = candidate.group(1).replace(" ", "") if candidate else "无法确定"
        prefix = value[:reason_match.start()].strip()
        if prefix:
            reason = f"{prefix}\n{reason}" if reason else prefix
        return f"答案：{answer}\n解析：{reason or '未提供解析。'}"

    candidate = _CHOICE_IN_REASON.search(value)
    if candidate:
        answer = candidate.group(1).replace(" ", "")
        return f"答案：{answer}\n解析：{value}"
    return f"答案：无法确定\n解析：{value}"


def format_sql(sql: str) -> str:
    sql = _normalize_sql(sql)
    if not sql:
        return sql
    statements = _split_sql_statements(sql)
    if len(statements) > 1:
        return "\n".join(format_sql(statement) for statement in statements)
    if re.match(r"^ALTER\s+TABLE\b", sql, re.IGNORECASE):
        return _format_alter_table(sql)
    if re.match(r"^CREATE\s+TABLE\b", sql, re.IGNORECASE):
        return _format_create_table(sql)

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
        elif keyword == "SET":
            lines.append("SET")
            lines.extend(f"    {part}" for part in _split_assignment_items(body))
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
    sql = answer.strip()
    formatted = f"{prefix}\n```sql\n{format_sql(sql)}\n```"
    if reason:
        formatted += "\n" + reason.strip()
    return formatted


def _normalize_sql(sql: str) -> str:
    sql = sql.strip().strip("`")
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"\s*;\s*$", ";", sql)
    return sql


def _keyword_label(keyword: str) -> str:
    return re.sub(r"\s+", " ", keyword).upper()


def _split_select_items(body: str) -> list[str]:
    if not body:
        return []
    pieces = _split_top_level_commas(body)
    if len(pieces) == 1:
        return pieces
    return [piece + ("," if index < len(pieces) - 1 else "") for index, piece in enumerate(pieces) if piece]


def _split_assignment_items(body: str) -> list[str]:
    pieces = _split_top_level_commas(body)
    if len(pieces) == 1:
        return pieces
    return [piece + ("," if index < len(pieces) - 1 else "") for index, piece in enumerate(pieces) if piece]


def _format_create_table(sql: str) -> str:
    match = re.match(
        r"^CREATE\s+TABLE\s+(`[^`]+`|\"[^\"]+\"|[\w.]+)\s*\((.+)\);?$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return _format_keyword_clauses(sql)

    table_name, body = match.groups()
    has_semicolon = sql.endswith(";")
    columns = _split_top_level_commas(body)
    lines = [f"CREATE TABLE {table_name} ("]
    for index, column in enumerate(columns):
        suffix = "," if index < len(columns) - 1 else ""
        lines.append(f"    {column}{suffix}")
    lines.append(")" + (";" if has_semicolon else ""))
    return "\n".join(lines)


def _format_keyword_clauses(sql: str) -> str:
    matches = list(_CLAUSE_PATTERN.finditer(sql))
    if not matches:
        return sql
    lines: list[str] = []
    for index, match in enumerate(matches):
        keyword = _keyword_label(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(sql)
        body = sql[start:end].strip()
        lines.append(keyword)
        if body:
            lines.append(f"    {body}")
    return "\n".join(line for line in lines if line.strip())


def _format_alter_table(sql: str) -> str:
    match = _ALTER_TABLE_PATTERN.match(sql)
    if not match:
        return sql

    table_name, actions = match.groups()
    has_semicolon = sql.endswith(";")
    actions = actions[:-1].strip() if has_semicolon and actions.endswith(";") else actions.strip()
    action_parts = _split_top_level_commas(actions)
    if not action_parts:
        return sql

    lines = [f"ALTER TABLE {table_name}"]
    for index, action in enumerate(action_parts):
        suffix = "," if index < len(action_parts) - 1 else (";" if has_semicolon else "")
        lines.append(f"    {_format_alter_action(action)}{suffix}")
    return "\n".join(lines)


def _format_alter_action(action: str) -> str:
    action = action.strip()
    action = re.sub(
        r"\b(ADD|ALTER|CHANGE|MODIFY|DROP)\s+COLUMN\b",
        lambda m: m.group(0).upper(),
        action,
        flags=re.IGNORECASE,
    )
    action = re.sub(
        r"\b(AFTER|FIRST|NOT\s+NULL|NULL|SET\s+DEFAULT|DEFAULT|COMMENT)\b",
        lambda m: re.sub(r"\s+", " ", m.group(0).upper()),
        action,
        flags=re.IGNORECASE,
    )
    return action


def _split_sql_statements(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == quote:
                quote = None
            elif char == "\\":
                index += 1
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == ";":
            statement = value[start : index + 1].strip()
            if statement:
                parts.append(statement)
            start = index + 1
        index += 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _split_top_level_commas(value: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == quote:
                quote = None
            elif char == "\\":
                index += 1
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
        index += 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return parts
