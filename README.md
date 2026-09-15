# Conversational SQL

Secure natural-language analytics for MySQL. Ask questions in plain English; the application generates a read-only SQL query, validates it, executes it with a row limit, and explains the result.

## Safety model

- Only one SQL statement is accepted.
- Only `SELECT`-style queries are accepted.
- Mutating operations such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, and `ALTER` are rejected.
- Queries without a limit receive `LIMIT 100`.
- Connection failures and query failures are shown without exposing credentials or stack traces.
- Use a database account with `SELECT` permissions only.

## Run locally

1. Create an environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set `GROQ_API_KEY` plus database settings. Never commit `.env`.

3. Start the application:

   ```bash
   streamlit run app.py
   ```

4. Run tests:

   ```bash
   pytest -q
   ```

## Configuration

| Variable | Purpose |
| --- | --- |
| `GROQ_API_KEY` | LLM provider key |
| `GROQ_MODEL` | Groq model name |
| `DB_HOST` | MySQL host |
| `DB_PORT` | MySQL port |
| `DB_USER` | Read-only MySQL user |
| `DB_PASSWORD` | Local secret; do not commit |
| `DB_NAME` | Database name |

## Architecture

`app.py` owns the UI and orchestration. `query_guard.py` is the policy boundary between model output and the database. The guard parses generated SQL with SQLGlot before execution, making the safety rule independently testable.

## Limitations

This is a local Streamlit application. A production deployment should add authentication, per-user database permissions, audit logging, rate limits, query cost checks, and an API layer.
