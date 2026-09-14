from ai_screenshot_assistant.ai.formatting import format_ai_output, format_sql


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
