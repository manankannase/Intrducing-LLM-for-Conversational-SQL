import pytest

from query_guard import UnsafeQueryError, validate_read_only_sql


def test_select_is_normalized_with_a_limit():
    sql = validate_read_only_sql("SELECT name FROM users")
    assert sql.upper().startswith("SELECT NAME FROM USERS")
    assert "LIMIT 100" in sql.upper()


def test_existing_limit_is_preserved():
    assert validate_read_only_sql("SELECT * FROM users LIMIT 5").upper().endswith("LIMIT 5")


def test_large_limits_are_capped():
    assert validate_read_only_sql("SELECT * FROM users LIMIT 1000").upper().endswith("LIMIT 100")


@pytest.mark.parametrize("sql", [
    "DROP TABLE users",
    "DELETE FROM users",
    "UPDATE users SET name = 'x'",
    "SELECT 1; DROP TABLE users",
    "SELECT SLEEP(10)",
    "SELECT * FROM users INTO OUTFILE '/tmp/users.csv'",
])
def test_mutating_or_multiple_statements_are_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only_sql(sql)


def test_markdown_fences_are_removed():
    assert validate_read_only_sql("```sql\nSELECT 1\n```").upper().startswith("SELECT 1")
