"""Streamlit UI for secure, read-only conversational SQL."""

from __future__ import annotations

import os

import mysql.connector
import streamlit as st
from dotenv import load_dotenv

from core import (
    ConfigurationError,
    LLMError,
    connect_database,
    execute_query,
    explain_result,
    generate_sql,
    load_schema,
)
from query_guard import UnsafeQueryError

load_dotenv()

st.set_page_config(page_title="Conversational SQL", page_icon=":speech_balloon:")
st.title("Conversational SQL")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{
        "role": "assistant",
        "content": "Hello! I can answer questions using your read-only database connection.",
    }]

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
            connection = connect_database(
                host=st.session_state.host,
                port=st.session_state.port,
                user=st.session_state.user,
                password=st.session_state.password,
                database=st.session_state.database,
            )
            schema = load_schema(connection, st.session_state.database)
            st.session_state.connection = connection
            st.session_state.schema = schema
            st.success("Connected. Schema loaded.")
        except (ConfigurationError, mysql.connector.Error) as exc:
            st.error(str(exc) if isinstance(exc, ConfigurationError) else "Could not connect. Check the database settings.")

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

user_query = st.chat_input("Ask a question about your data...")
if user_query and user_query.strip():
    st.session_state.chat_history.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        if "connection" not in st.session_state:
            answer = "Connect to a database before asking a question."
        else:
            try:
                with st.spinner("Generating and validating a read-only query..."):
                    query = generate_sql(user_query, st.session_state.schema, st.session_state.chat_history)
                    rows = execute_query(st.session_state.connection, query)
                    answer = explain_result(user_query, query, rows)
                with st.expander("SQL executed"):
                    st.code(query, language="sql")
                if rows:
                    st.dataframe(rows, use_container_width=True)
            except (UnsafeQueryError, ConfigurationError, LLMError) as exc:
                answer = str(exc)
            except mysql.connector.Error:
                answer = "The database query failed. Check the connection and generated SQL."
        st.markdown(answer)
    st.session_state.chat_history.append({"role": "assistant", "content": answer})
