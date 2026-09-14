from ai_screenshot_assistant.ai.formatting import format_ai_output, format_sql


def test_format_select_with_join_group_having_limit() -> None:
    sql = (
        "SELECT u.id, u.name, COUNT(o.id) AS order_count FROM users u "
        "LEFT JOIN orders o ON o.user_id = u.id WHERE u.status = 'active' "
        "GROUP BY u.id, u.name HAVING COUNT(o.id) > 0 ORDER BY order_count DESC LIMIT 10;"
    )

    assert format_sql(sql) == (
        "SELECT\n"
        "    u.id,\n"
        "    u.name,\n"
        "    COUNT(o.id) AS order_count\n"
        "FROM\n"
        "    users u\n"
        "LEFT JOIN\n"
        "    orders o\n"
        "ON\n"
        "    o.user_id = u.id\n"
        "WHERE\n"
        "    u.status = 'active'\n"
        "GROUP BY\n"
        "    u.id, u.name\n"
        "HAVING\n"
        "    COUNT(o.id) > 0\n"
        "ORDER BY\n"
        "    order_count DESC\n"
        "LIMIT\n"
        "    10;"
    )


def test_format_select_preserves_commas_inside_functions() -> None:
    sql = "SELECT CONCAT(last_name, ', ', first_name) AS full_name, age FROM users WHERE id = 1;"

    assert format_sql(sql) == (
        "SELECT\n"
        "    CONCAT(last_name, ', ', first_name) AS full_name,\n"
        "    age\n"
        "FROM\n"
        "    users\n"
        "WHERE\n"
        "    id = 1;"
    )


def test_format_alter_table_mysql_subclauses() -> None:
    sql = (
        "ALTER TABLE user_info ADD COLUMN school VARCHAR(15) AFTER level, "
        "CHANGE COLUMN job profession VARCHAR(10) NULL DEFAULT NULL COMMENT '职业方向', "
        "MODIFY COLUMN achievement INT(11) NULL DEFAULT 0 COMMENT '成就值';"
    )

    assert format_sql(sql) == (
        "ALTER TABLE user_info\n"
        "    ADD COLUMN school VARCHAR(15) AFTER level,\n"
        "    CHANGE COLUMN job profession VARCHAR(10) NULL DEFAULT NULL COMMENT '职业方向',\n"
        "    MODIFY COLUMN achievement INT(11) NULL DEFAULT 0 COMMENT '成就值';"
    )


def test_format_alter_table_preserves_commas_inside_types_and_strings() -> None:
    sql = (
        "ALTER TABLE orders ADD COLUMN amount DECIMAL(10,2) NULL DEFAULT 0 COMMENT '金额, 元', "
        "DROP COLUMN legacy_amount;"
    )

    assert format_sql(sql) == (
        "ALTER TABLE orders\n"
        "    ADD COLUMN amount DECIMAL(10,2) NULL DEFAULT 0 COMMENT '金额, 元',\n"
        "    DROP COLUMN legacy_amount;"
    )


def test_format_ai_output_wraps_single_line_alter_table_answer() -> None:
    text = (
        "答案：ALTER TABLE user_info ADD COLUMN school VARCHAR(15) AFTER level, "
        "CHANGE COLUMN job profession VARCHAR(10) NULL DEFAULT NULL COMMENT '职业方向', "
        "MODIFY COLUMN achievement INT(11) NULL DEFAULT 0 COMMENT '成就值';\n"
        "解析：按题目要求新增、重命名并修改字段。"
    )

    formatted = format_ai_output(text)

    assert "```sql" in formatted
    assert "ALTER TABLE user_info\n" in formatted
    assert "    ADD COLUMN school VARCHAR(15) AFTER level,\n" in formatted
    assert "    CHANGE COLUMN job profession VARCHAR(10) NULL DEFAULT NULL COMMENT '职业方向',\n" in formatted
    assert "    MODIFY COLUMN achievement INT(11) NULL DEFAULT 0 COMMENT '成就值';" in formatted
    assert "解析：按题目要求新增、重命名并修改字段。" in formatted


def test_format_multiple_alter_table_statements_from_fullscreen_answer() -> None:
    text = (
        "答案：ALTER TABLE user_info ADD COLUMN school VARCHAR(15) AFTER level; "
        "ALTER TABLE user_info CHANGE COLUMN job profession VARCHAR(10); "
        "ALTER TABLE user_info ALTER COLUMN achievement SET DEFAULT 0;\n"
        "解析：按题目要求分别新增、修改字段名和设置默认值。"
    )

    formatted = format_ai_output(text)

    assert formatted == (
        "答案：\n"
        "```sql\n"
        "ALTER TABLE user_info\n"
        "    ADD COLUMN school VARCHAR(15) AFTER level;\n"
        "ALTER TABLE user_info\n"
        "    CHANGE COLUMN job profession VARCHAR(10);\n"
        "ALTER TABLE user_info\n"
        "    ALTER COLUMN achievement SET DEFAULT 0;\n"
        "```\n"
        "解析：按题目要求分别新增、修改字段名和设置默认值。"
    )


def test_format_multiple_statement_answer_keeps_semicolon_inside_string() -> None:
    text = (
        "答案：UPDATE user_info SET remark = 'a;b', profession = 'dev' WHERE id = 1; "
        "DELETE FROM logs WHERE message = 'x;y';\n"
        "解析：先更新用户，再删除日志。"
    )

    formatted = format_ai_output(text)

    assert formatted == (
        "答案：\n"
        "```sql\n"
        "UPDATE\n"
        "    user_info\n"
        "SET\n"
        "    remark = 'a;b',\n"
        "    profession = 'dev'\n"
        "WHERE\n"
        "    id = 1;\n"
        "DELETE FROM\n"
        "    logs\n"
        "WHERE\n"
        "    message = 'x;y';\n"
        "```\n"
        "解析：先更新用户，再删除日志。"
    )


def test_format_insert_values_does_not_split_value_commas() -> None:
    sql = "INSERT INTO users (name, remark) VALUES ('张三', 'a,b,c');"

    assert format_sql(sql) == (
        "INSERT INTO\n"
        "    users (name, remark)\n"
        "VALUES\n"
        "    ('张三', 'a,b,c');"
    )


def test_format_existing_sql_fence_with_multiple_alter_statements() -> None:
    text = (
        "答案：\n"
        "```sql\n"
        "ALTER TABLE user_info ADD COLUMN school VARCHAR(15) AFTER level; "
        "ALTER TABLE user_info ALTER COLUMN achievement SET DEFAULT 0;\n"
        "```\n"
        "解析：字段调整。"
    )

    assert format_ai_output(text) == (
        "答案：\n"
        "```sql\n"
        "ALTER TABLE user_info\n"
        "    ADD COLUMN school VARCHAR(15) AFTER level;\n"
        "ALTER TABLE user_info\n"
        "    ALTER COLUMN achievement SET DEFAULT 0;\n"
        "```\n"
        "解析：字段调整。"
    )


def test_format_create_table_keeps_column_list_readable() -> None:
    sql = (
        "CREATE TABLE user_info (id INT PRIMARY KEY, name VARCHAR(20) NOT NULL, "
        "amount DECIMAL(10,2) DEFAULT 0 COMMENT '金额, 元');"
    )

    assert format_sql(sql) == (
        "CREATE TABLE user_info (\n"
        "    id INT PRIMARY KEY,\n"
        "    name VARCHAR(20) NOT NULL,\n"
        "    amount DECIMAL(10,2) DEFAULT 0 COMMENT '金额, 元'\n"
        ");"
    )
