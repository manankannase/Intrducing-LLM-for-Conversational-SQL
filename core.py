"""Database and LLM services for Conversational SQL."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import mysql.connector

from query_guard import validate_read_only_sql

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class ConfigurationError(RuntimeError):
    """Raised when required local configuration is missing."""


class LLMError(RuntimeError):
    """Raised when the model provider cannot return a valid response."""


def connect_database(*, host: str, port: str, user: str, password: str, database: str):
    """Connect to MySQL with a short timeout and autocommit enabled."""
    try:
        port_number = int(port)
    except ValueError as exc:
        raise ConfigurationError("Database port must be a number.") from exc
    if not 1 <= port_number <= 65535:
        raise ConfigurationError("Database port must be between 1 and 65535.")
    return mysql.connector.connect(
        host=host,
        port=port_number,
        user=user,
        password=password,
        database=database,
        connection_timeout=5,
        autocommit=True,
    )


def load_schema(connection, database: str) -> str:
    """Return a compact schema description for the selected database."""
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (database,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
    if not rows:
        raise ConfigurationError("No tables were found in the selected database.")
    return "\n".join(f"{table}.{column} ({data_type})" for table, column, data_type in rows)


def call_groq(messages: list[dict[str, str]]) -> str:
    """Call Groq's OpenAI-compatible chat completion endpoint."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ConfigurationError("GROQ_API_KEY is missing from .env.")
    payload = json.dumps({
        "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "messages": messages,
        "temperature": 0,
    }).encode()
    request = Request(
        GROQ_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
        return body["choices"][0]["message"]["content"].strip()
    except (HTTPError, URLError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMError("The language model service could not complete the request.") from exc


def history_text(history: list[dict[str, str]]) -> str:
    """Format only the latest conversation turns for the model."""
    return "\n".join(f"{item['role']}: {item['content']}" for item in history[-10:])


def generate_sql(question: str, schema: str, history: list[dict[str, str]]) -> str:
    """Generate and validate one read-only MySQL query."""
    prompt = f"""Database schema:
{schema}

Recent conversation:
{history_text(history)}

Question: {question}
Return exactly one MySQL SELECT query. Use only listed tables and columns. No markdown."""
    raw_sql = call_groq([
        {
            "role": "system",
            "content": "You generate safe, read-only SQL. Never generate data-changing or administrative statements.",
        },
        {"role": "user", "content": prompt},
    ])
    return validate_read_only_sql(raw_sql)


def execute_query(connection, query: str) -> list[dict]:
    """Execute validated SQL and return at most 100 rows."""
    safe_query = validate_read_only_sql(query)
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute(safe_query)
        return cursor.fetchmany(100)
    finally:
        cursor.close()


def explain_result(question: str, query: str, rows: list[dict]) -> str:
    """Explain database results without adding unsupported facts."""
    result_json = json.dumps(rows, default=str, ensure_ascii=False)
    return call_groq([
        {
            "role": "system",
            "content": "Explain SQL results clearly and briefly. Do not invent facts absent from the result.",
        },
        {
            "role": "user",
            "content": f"Question: {question}\nSQL: {query}\nResult: {result_json}",
        },
    ])
