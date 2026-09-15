"""Streamlit UI for secure, read-only conversational SQL."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

import streamlit as st
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_groq import ChatGroq

from query_guard import UnsafeQueryError, validate_read_only_sql

load_dotenv()


def init_database(user: str, password: str, host: str, port: str, database: str) -> SQLDatabase:
    """Create a SQLAlchemy-backed database connection without logging credentials."""
    db_uri = (
        f"mysql+mysqlconnector://{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{quote_plus(database)}"
    )
    return SQLDatabase.from_uri(db_uri)


def _llm() -> ChatGroq:
    return ChatGroq(model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"), temperature=0)


def _history_text(chat_history: list) -> str:
    return "\n".join(f"{message.type}: {message.content}" for message in chat_history[-10:])


def get_sql_chain(db: SQLDatabase, schema: str | None = None):
    template = """
You generate safe, read-only MySQL for a data analyst.
Use only tables and columns present in the schema. Never invent identifiers.
Return exactly one SQL SELECT statement and no markdown.

<SCHEMA>{schema}</SCHEMA>
Conversation history:
{chat_history}
Question: {question}
SQL:
"""
    prompt = ChatPromptTemplate.from_template(template)

    def get_schema(_):
        return schema or db.get_table_info()

    return RunnablePassthrough.assign(schema=get_schema) | prompt | _llm() | StrOutputParser()


def generate_sql(question: str, db: SQLDatabase, chat_history: list, schema: str | None = None) -> str:
    raw_sql = get_sql_chain(db, schema).invoke({
        "question": question,
        "chat_history": _history_text(chat_history),
    })
    return validate_read_only_sql(raw_sql)


def get_response(user_query: str, db: SQLDatabase, chat_history: list, schema: str | None = None):
    """Generate, validate, execute, and explain one read-only query."""
    query = generate_sql(user_query, db, chat_history, schema)
    result = db.run(query)
    prompt = ChatPromptTemplate.from_template("""
You are a data analyst. Explain the result clearly and briefly.
Do not claim facts that are absent from the SQL response.
Question: {question}
SQL executed: {query}
SQL response: {response}
""")
    answer = prompt | _llm() | StrOutputParser()
    return query, answer.invoke({"question": user_query, "query": query, "response": result})


if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        AIMessage(content="Hello! I can answer questions using your read-only database connection."),
    ]

st.set_page_config(page_title="Conversational SQL", page_icon=":speech_balloon:")
st.title("Conversational SQL")

with st.sidebar:
    st.subheader("Database connection")
    st.caption("Use a database account with SELECT-only permissions.")
    st.text_input("Host", value=os.getenv("DB_HOST", "localhost"), key="host")
    st.text_input("Port", value=os.getenv("DB_PORT", "3306"), key="port")
    st.text_input("User", value=os.getenv("DB_USER", "readonly"), key="user")
    st.text_input("Password", value=os.getenv("DB_PASSWORD", ""), type="password", key="password")
    st.text_input("Database", value=os.getenv("DB_NAME", "college"), key="database")

    if st.button("Connect", type="primary"):
        try:
            st.session_state.db = init_database(
                st.session_state.user,
                st.session_state.password,
                st.session_state.host,
                st.session_state.port,
                st.session_state.database,
            )
            st.session_state.schema = st.session_state.db.get_table_info()
            st.success("Connected. Schema loaded.")
        except Exception:
            st.error("Could not connect. Check the host, credentials, and database name.")

for message in st.session_state.chat_history:
    role = "assistant" if isinstance(message, AIMessage) else "user"
    with st.chat_message(role):
        st.markdown(message.content)

user_query = st.chat_input("Ask a question about your data...")
if user_query and user_query.strip():
    st.session_state.chat_history.append(HumanMessage(content=user_query))
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        if "db" not in st.session_state:
            response = "Connect to a database before asking a question."
        else:
            try:
                with st.spinner("Generating and validating a read-only query..."):
                    query, response = get_response(
                        user_query,
                        st.session_state.db,
                        st.session_state.chat_history,
                        st.session_state.get("schema"),
                    )
                with st.expander("SQL executed"):
                    st.code(query, language="sql")
            except UnsafeQueryError as exc:
                response = f"I blocked the generated query for safety: {exc}"
            except Exception:
                response = "The query could not be completed. Check the connection and try again."
        st.markdown(response)
    st.session_state.chat_history.append(AIMessage(content=response))
