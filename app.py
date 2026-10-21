"""
app.py - AI Data Analyst — Streamlit Frontend
============================================================
Powered by Groq. Supports CSV, Excel, and PDF uploads.
"""

from __future__ import annotations

import io
import json
import html
import logging
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from agent import run_agent
from backend_client import BackendApiClient, BackendApiError
from chart_builder import build_chart
from config import settings
from data_loader import (
    DataLoaderError,
    DatasetInfo,
    load_file,
    load_csv_from_path,
    load_records,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Data Analyst",
    page_icon=str(Path(__file__).parent / "assets" / "brand.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Base styles
# ---------------------------------------------------------------------------

st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Root Reset ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── Main Background ── */
.stApp {
    background-color: #f8fafc;
}

/* ── Hide Streamlit branding ── */
#MainMenu, footer, header { visibility: hidden; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.5rem;
}

/* ── Top header bar ── */
.app-header {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    padding: 2rem 2.5rem;
    border-radius: 16px;
    margin-bottom: 1.5rem;
    color: white;
}
.app-header h1 {
    color: white !important;
    font-size: 2rem;
    font-weight: 800;
    margin: 0 0 0.25rem 0;
    letter-spacing: -0.5px;
}
.app-header p {
    color: rgba(255,255,255,0.85);
    font-size: 1rem;
    margin: 0;
}

/* ── Cards ── */
.card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
    transition: box-shadow 0.2s ease;
}
.card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

/* ── KPI metric cards ── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    text-align: center;
}
.kpi-icon {
    font-size: 1.75rem;
    margin-bottom: 0.5rem;
}
.kpi-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: #1e293b;
    line-height: 1.1;
}
.kpi-label {
    font-size: 0.78rem;
    color: #64748b;
    font-weight: 500;
    margin-top: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Status badges ── */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.3rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-green  { background: #dcfce7; color: #15803d; }
.badge-blue   { background: #dbeafe; color: #2563eb; }
.badge-orange { background: #ffedd5; color: #c2410c; }
.badge-purple { background: #ede9fe; color: #7c3aed; }
.badge-gray   { background: #f1f5f9; color: #475569; }

/* ── Chat container ── */
.chat-container {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.5rem;
    min-height: 300px;
    max-height: 600px;
    overflow-y: auto;
    margin-bottom: 1rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── User message bubble ── */
.msg-user {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1rem;
}
.msg-user-bubble {
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: white;
    padding: 0.85rem 1.25rem;
    border-radius: 18px 18px 4px 18px;
    max-width: 75%;
    font-size: 0.92rem;
    line-height: 1.5;
    box-shadow: 0 2px 8px rgba(79,70,229,0.3);
}

/* ── AI message bubble ── */
.msg-ai {
    display: flex;
    justify-content: flex-start;
    margin-bottom: 1rem;
}
.msg-ai-avatar {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    margin-right: 0.75rem;
    flex-shrink: 0;
    color: white;
}
.msg-ai-bubble {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    color: #1e293b;
    padding: 0.85rem 1.25rem;
    border-radius: 4px 18px 18px 18px;
    max-width: 80%;
    font-size: 0.92rem;
    line-height: 1.6;
}

/* ── Error message ── */
.msg-error {
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 10px;
    padding: 0.85rem 1.25rem;
    color: #dc2626;
    font-size: 0.9rem;
}

/* ── Sample question chips ── */
.sample-chip {
    display: inline-block;
    background: #ede9fe;
    color: #4f46e5;
    border: 1px solid #c4b5fd;
    padding: 0.35rem 0.85rem;
    border-radius: 9999px;
    font-size: 0.78rem;
    font-weight: 500;
    margin: 0.2rem;
    cursor: pointer;
    transition: background 0.15s;
}
.sample-chip:hover { background: #ddd6fe; }

/* ── Section titles ── */
.section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1e293b;
    margin: 1.25rem 0 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid #e2e8f0;
}

/* ── Streamlit widgets ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 10px !important;
    background: #ffffff !important;
    color: #1e293b !important;
    font-family: 'Inter', sans-serif !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 3px rgba(79,70,229,0.15) !important;
}

.stButton > button {
    background: linear-gradient(135deg, #4f46e5, #7c3aed) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    padding: 0.55rem 1.5rem !important;
    transition: opacity 0.2s, transform 0.1s !important;
}
.stButton > button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    border: 2px dashed #c4b5fd !important;
    border-radius: 14px !important;
    background: #faf5ff !important;
    padding: 1rem !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: #f1f5f9;
    border-radius: 10px;
    padding: 0.25rem;
    gap: 0.25rem;
}
[data-testid="stTabs"] [role="tab"] {
    border-radius: 8px !important;
    font-weight: 500 !important;
    color: #64748b !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background: #ffffff !important;
    color: #4f46e5 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1) !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
}

/* ── Sidebar styles ── */
.sidebar-section {
    background: #f8fafc;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
    border: 1px solid #e2e8f0;
}
.sidebar-logo {
    text-align: center;
    padding: 0.5rem 0 1rem;
}
.sidebar-logo .logo-icon {
    font-size: 2.5rem;
}
.sidebar-logo h2 {
    color: #1e293b;
    font-size: 1.15rem;
    font-weight: 700;
    margin: 0.25rem 0 0;
}
.sidebar-logo p {
    color: #64748b;
    font-size: 0.78rem;
    margin: 0;
}

/* ── Alert boxes ── */
.alert-info {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-left: 4px solid #3b82f6;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    color: #1e40af;
    font-size: 0.88rem;
    margin-bottom: 1rem;
}
.alert-success {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 4px solid #22c55e;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    color: #15803d;
    font-size: 0.88rem;
    margin-bottom: 1rem;
}
.alert-warning {
    background: #fffbeb;
    border: 1px solid #fde68a;
    border-left: 4px solid #f59e0b;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    color: #92400e;
    font-size: 0.88rem;
    margin-bottom: 1rem;
}

/* ── Format badge ── */
.format-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: #ede9fe;
    color: #5b21b6;
    border-radius: 8px;
    padding: 0.3rem 0.75rem;
    font-weight: 700;
    font-size: 0.8rem;
}

/* ── Plotly charts ── */
.js-plotly-plot .plotly {
    border-radius: 12px;
}

/* ── Tool call log ── */
.tool-log {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    font-family: 'Courier New', monospace;
    font-size: 0.8rem;
    color: #475569;
    margin-top: 0.5rem;
}
.tool-log-item {
    padding: 0.25rem 0;
    border-bottom: 1px solid #f1f5f9;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.tool-log-item:last-child { border-bottom: none; }
</style>
""", unsafe_allow_html=True)

if st.session_state.get("dark_mode", False):
    st.markdown("""
    <style>
    .stApp, [data-testid="stAppViewContainer"] {
        background: #0f172a !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stSidebar"] {
        background: #111827 !important;
        border-right-color: #334155 !important;
    }
    .card, .kpi-card, .sidebar-section, .chat-container, .tool-log,
    .msg-ai-bubble, [data-testid="stTabs"] [role="tablist"] {
        background: #1e293b !important;
        border-color: #334155 !important;
        color: #e2e8f0 !important;
    }
    .card div, .kpi-card div, .sidebar-section span {
        color: #e2e8f0 !important;
    }
    .section-title, .sidebar-logo h2, .msg-ai-bubble, .tool-log,
    .kpi-label, .kpi-value, .stApp [style*="color:#1e293b"],
    .stApp [style*="color: #1e293b"] {
        color: #e2e8f0 !important;
    }
    .stApp [style*="color:#64748b"], .stApp [style*="color: #64748b"],
    .sidebar-logo p {
        color: #cbd5e1 !important;
    }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    [data-testid="stNumberInput"] input,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
        background: #0f172a !important;
        color: #e2e8f0 !important;
        border-color: #475569 !important;
    }
    [data-baseweb="popover"], [data-baseweb="menu"],
    [data-baseweb="popover"] [role="option"] {
        background: #1e293b !important;
        color: #e2e8f0 !important;
    }
    [data-testid="stExpander"] {
        background: #1e293b !important;
        border-color: #334155 !important;
    }
    [data-testid="stFileUploader"] {
        background: #1e293b !important;
        border-color: #7c3aed !important;
    }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        background: #334155 !important;
        color: #c4b5fd !important;
    }
    .alert-info, .alert-success, .alert-warning {
        background: #1e293b !important;
        color: #e2e8f0 !important;
        border-color: #475569 !important;
    }
    .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stWidgetLabel"],
    .stApp [data-testid="stCheckbox"] label, .stApp [data-testid="stRadio"] label {
        color: #e2e8f0 !important;
    }
    .app-header p { color: rgba(255, 255, 255, .85) !important; }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        color-scheme: dark;
    }
    .st-key-auth-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 18px;
        padding: 2rem;
        box-shadow: 0 12px 35px rgba(0, 0, 0, .24);
    }
    .auth-title { color: #f8fafc; }
    .auth-subtitle { color: #cbd5e1; }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
    .stApp, [data-testid="stAppViewContainer"] {
        background: #f8fafc !important;
        color: #0f172a !important;
    }
    [data-testid="stSidebar"] {
        background: #ffffff !important;
        border-right-color: #e2e8f0 !important;
    }
    .stApp p, .stApp label, .stApp [data-testid="stMarkdownContainer"],
    .stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stWidgetLabel"],
    .stApp [data-testid="stCheckbox"] label, .stApp [data-testid="stRadio"] label,
    .stApp [data-testid="stExpander"] summary,
    .stApp [data-testid="stMetricLabel"], .stApp [data-testid="stMetricValue"] {
        color: #1e293b !important;
    }
    .app-header p { color: rgba(255, 255, 255, .85) !important; }
    .stApp [style*="color:#64748b"], .stApp [style*="color: #64748b"],
    .stApp [style*="color:#475569"], .stApp [style*="color: #475569"] {
        color: #475569 !important;
    }
    .stApp [style*="color:#94a3b8"], .stApp [style*="color: #94a3b8"] {
        color: #475569 !important;
    }
    .stApp [style*="color:#1e293b"], .stApp [style*="color: #1e293b"],
    .stApp [style*="color:#334155"], .stApp [style*="color: #334155"] {
        color: #0f172a !important;
    }
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    [data-testid="stNumberInput"] input,
    [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
    [data-testid="stMultiSelect"] div[data-baseweb="select"] > div {
        background: #ffffff !important;
        color: #0f172a !important;
        border-color: #cbd5e1 !important;
    }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
        color: #64748b !important;
        opacity: 1 !important;
    }
    [data-testid="stTabs"] [role="tablist"] { background: #e2e8f0 !important; }
    [data-testid="stTabs"] [role="tab"] { color: #334155 !important; }
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {
        background: #ffffff !important;
        color: #4338ca !important;
    }
    [data-baseweb="popover"], [data-baseweb="menu"],
    [data-baseweb="popover"] [role="option"] {
        background: #ffffff !important;
        color: #0f172a !important;
    }
    [data-testid="stAlert"] { color: #1e293b !important; }
    [data-testid="stExpander"] {
        background: #ffffff !important;
        border-color: #e2e8f0 !important;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
        color-scheme: light;
    }
    .st-key-auth-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        padding: 2rem;
        box-shadow: 0 12px 35px rgba(15, 23, 42, .08);
    }
    .auth-title { color: #0f172a; }
    .auth-subtitle { color: #475569; }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "dataset_info": None,
        "chat_history": [],
        "conversation_messages": [],
        "file_loaded": False,
        "dark_mode": False,
        "data_source": "upload",
        "db_connection": None,
        "db_tables": [],
        "auth_access_token": "",
        "auth_refresh_token": "",
        "auth_email": "",
        "auth_user_id": "",
        "auth_feedback": None,
        "saved_history": [],
        "account_page": "Home",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def _set_dataset(dataset_info: DatasetInfo, source: str) -> None:
    st.session_state.dataset_info = dataset_info
    st.session_state.file_loaded = True
    st.session_state.data_source = source
    st.session_state.chat_history = []
    st.session_state.conversation_messages = []
    st.session_state.latest_response = None


def _clear_account_state() -> None:
    st.session_state.auth_access_token = ""
    st.session_state.auth_refresh_token = ""
    st.session_state.auth_email = ""
    st.session_state.auth_user_id = ""
    st.session_state.saved_history = []
    st.session_state.db_connection = None
    st.session_state.db_tables = []
    st.session_state.dataset_info = None
    st.session_state.file_loaded = False
    st.session_state.data_source = "upload"
    st.session_state.chat_history = []
    st.session_state.conversation_messages = []
    st.session_state.latest_response = None
    st.session_state.pop("db_table", None)
    for key in (
        "db_host",
        "db_port",
        "db_name",
        "db_username",
        "db_password",
        "db_ssl",
        "db_uri",
        "db_supabase_key",
        "db_supabase_access_token",
        "db_supabase_url",
        "auth_email_input",
        "auth_password_input",
        "register_email_input",
        "register_password_input",
    ):
        st.session_state.pop(key, None)


def _disconnect_database() -> None:
    was_database_source = st.session_state.data_source == "database"
    st.session_state.db_connection = None
    st.session_state.db_tables = []
    st.session_state.pop("db_table", None)
    for key in (
        "db_host",
        "db_port",
        "db_name",
        "db_username",
        "db_password",
        "db_ssl",
        "db_uri",
        "db_supabase_key",
        "db_supabase_access_token",
        "db_supabase_url",
    ):
        st.session_state.pop(key, None)
    if was_database_source:
        st.session_state.dataset_info = None
        st.session_state.file_loaded = False
        st.session_state.data_source = "upload"
        st.session_state.chat_history = []
        st.session_state.conversation_messages = []
        st.session_state.latest_response = None


def _api_client() -> BackendApiClient:
    return BackendApiClient()


def _save_service_tokens(service: dict) -> None:
    st.session_state.auth_access_token = service["access_token"]
    st.session_state.auth_refresh_token = service.get(
        "refresh_token", st.session_state.auth_refresh_token
    )


def _authenticate(action: str) -> None:
    email = st.session_state.get("auth_email_input", "").strip().lower()
    password = st.session_state.get("auth_password_input", "")
    try:
        if not email or not password:
            raise BackendApiError("Enter both your email and password.")
        client = _api_client()
        if action == "Sign in":
            result = client.sign_in(email, password)
            user = result.get("user") or {}
            if not result.get("access_token"):
                raise BackendApiError("Sign-in did not return an active session.")
            st.session_state.auth_email = user.get("email", email)
            st.session_state.auth_user_id = user.get("id", "")
            st.session_state.saved_history = []
            _save_service_tokens(result)
            st.session_state.auth_feedback = {
                "type": "success",
                "message": "Signed in successfully.",
            }
            st.session_state.account_page = "Home"
        else:
            result = client.sign_up(email, password)
            user = result.get("user") or {}
            if result.get("access_token"):
                st.session_state.auth_email = user.get("email", email)
                st.session_state.auth_user_id = user.get("id", "")
                _save_service_tokens(result)
                st.session_state.auth_feedback = {
                    "type": "success",
                    "message": "Account created and signed in.",
                }
                st.session_state.account_page = "Home"
            else:
                st.session_state.auth_feedback = {
                    "type": "success",
                    "message": "Account created. Check your email to confirm it, then sign in.",
                }
                st.session_state.account_page = "Sign in"
    except BackendApiError as exc:
        st.session_state.auth_feedback = {"type": "error", "message": str(exc)}
    finally:
        st.session_state.auth_password_input = ""


def _render_auth_panel() -> None:
    st.markdown('<div class="section-title">👤 Account</div>', unsafe_allow_html=True)
    feedback = st.session_state.pop("auth_feedback", None)
    if feedback:
        if feedback["type"] == "error":
            st.error(feedback["message"])
        else:
            st.success(feedback["message"])

    if st.session_state.auth_access_token:
        st.caption(f"Signed in as {st.session_state.auth_email or 'user'}")
        if st.button("↪ Sign out", key="auth_sign_out", use_container_width=True):
            try:
                _api_client().sign_out(
                    st.session_state.auth_access_token,
                    st.session_state.auth_refresh_token,
                )
            except BackendApiError as exc:
                st.warning(f"Remote sign-out could not be confirmed: {exc}")
            _clear_account_state()
            st.rerun()

        if st.button("↻ Load saved history", key="history_refresh", use_container_width=True):
            try:
                result = _api_client().list_history(
                    st.session_state.auth_access_token,
                    st.session_state.auth_refresh_token,
                )
                st.session_state.saved_history = result["items"]
                _save_service_tokens(result)
            except BackendApiError as exc:
                st.error(str(exc))

        st.caption("History stores questions and answers, not dataset rows.")
        for entry in st.session_state.saved_history:
            title = str(entry.get("title") or entry.get("question") or "Analysis")
            with st.expander(title[:80], expanded=False):
                st.caption(str(entry.get("created_at", "")))
                st.text(str(entry.get("question", "")))
                st.text(str(entry.get("answer", "")))
        return

    account_service_configured = False
    if settings.app_api_key.strip():
        try:
            account_service_configured = _api_client().auth_status()
        except BackendApiError as exc:
            st.warning(str(exc))
    if not account_service_configured:
        st.caption("Optional sign-in and saved history are not configured.")

    if st.button(
        "Sign in or create account",
        key="sidebar_open_account",
        use_container_width=True,
    ):
        st.session_state.account_page = "Sign in"
        st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image(str(Path(__file__).parent / "assets" / "brand.svg"), width=62)
    st.markdown(
        '<div class="sidebar-logo"><h2>AI Data Analyst</h2>'
        '<p>Insights you can trust</p></div>',
        unsafe_allow_html=True,
    )

    st.toggle("🌙 Dark mode", key="dark_mode")
    _render_auth_panel()

    st.markdown('<div class="section-title">📁 Data source</div>', unsafe_allow_html=True)
    data_source_choice = st.radio(
        "Choose how to load data",
        ["Upload files", "Connect database"],
        horizontal=True,
        key="data_source_choice",
    )

    if data_source_choice == "Upload files":
        # File uploader — CSV, Excel, PDF
        uploaded_file = st.file_uploader(
            "Drop your file here",
            type=["csv", "xlsx", "xls", "pdf"],
            help="Supported formats: CSV, Excel (.xlsx/.xls), PDF",
            label_visibility="collapsed",
        )

        # Format labels
        st.markdown("""
        <div style="display:flex;gap:0.4rem;flex-wrap:wrap;margin:0.5rem 0;">
            <span class="badge badge-green">📄 CSV</span>
            <span class="badge badge-blue">📊 Excel</span>
            <span class="badge badge-purple">📕 PDF</span>
        </div>
        """, unsafe_allow_html=True)

        if uploaded_file:
            try:
                with st.spinner("Loading your file…"):
                    dataset_info = load_file(uploaded_file, uploaded_file.name)
                    _set_dataset(dataset_info, "upload")
            except DataLoaderError as e:
                st.error(f"❌ {e}")
                st.session_state.file_loaded = False

        # Sample dataset
        st.markdown('<div class="section-title">🎯 Quick Demo</div>', unsafe_allow_html=True)
        if st.button("▶ Load Sample Sales Data", use_container_width=True):
            sample_path = Path(__file__).parent / "sample_data" / "sample_sales.csv"
            try:
                dataset_info = load_csv_from_path(str(sample_path))
                _set_dataset(dataset_info, "upload")
                st.success("✅ Sample dataset loaded!")
            except Exception as e:
                st.error(f"❌ {e}")

    else:
        st.caption(
            "Imports are read-only and limited to the configured row/column caps. "
            "Use a database account with read-only privileges."
        )
        provider = st.selectbox(
            "Database type",
            ["PostgreSQL", "MySQL", "MongoDB", "Supabase"],
            key="db_provider",
        )
        with st.form("database_connection_form"):
            connection_config: dict = {"provider": provider}
            if provider in {"PostgreSQL", "MySQL"}:
                default_port = 5432 if provider == "PostgreSQL" else 3306
                connection_config.update({
                    "host": st.text_input("Host", key="db_host"),
                    "port": st.number_input(
                        "Port", min_value=1, max_value=65535, value=default_port,
                        key="db_port",
                    ),
                    "database": st.text_input("Database", key="db_name"),
                    "username": st.text_input("Username", key="db_username"),
                    "password": st.text_input(
                        "Password", type="password", key="db_password"
                    ),
                    "ssl": st.checkbox("Require TLS/SSL", value=True, key="db_ssl"),
                })
            elif provider == "MongoDB":
                connection_config.update({
                    "uri": st.text_input(
                        "MongoDB connection URI", type="password", key="db_uri",
                        help="Use a URI for a database you own. Credentials stay in this session.",
                    ),
                    "database": st.text_input("Database name", key="db_name"),
                    "ssl": st.checkbox("Require TLS/SSL", value=True, key="db_ssl"),
                })
            else:
                supabase_url = st.text_input(
                    "Supabase project URL", key="db_supabase_url"
                )
                connection_config.update({
                    "url": supabase_url,
                    "key": st.text_input(
                        "Anon/publishable key (not service-role)",
                        type="password",
                        key="db_supabase_key",
                    ),
                    "access_token": st.text_input(
                        "Optional user access token for RLS-protected rows",
                        type="password",
                        key="db_supabase_access_token",
                    ),
                })
            connect_clicked = st.form_submit_button(
                "Connect and list tables", use_container_width=True
            )

        if connect_clicked:
            st.session_state.db_connection = None
            st.session_state.db_tables = []
            st.session_state.pop("db_table", None)
            try:
                with st.spinner("Connecting and listing tables…"):
                    tables = _api_client().list_database_tables(connection_config)
                st.session_state.db_connection = connection_config
                st.session_state.db_tables = tables
                st.success(f"Connected. Found {len(tables)} accessible table(s)/collection(s).")
            except BackendApiError as exc:
                st.error(str(exc))

        if st.session_state.db_connection and st.session_state.db_tables:
            selected_table: dict = st.selectbox(
                "Table or collection",
                st.session_state.db_tables,
                format_func=lambda table: (
                    f"{table['schema']}.{table['name']}"
                    if table.get("schema") else table["name"]
                ),
                key="db_table",
            )
            if st.button("Import selected data", key="db_import", use_container_width=True):
                try:
                    with st.spinner("Importing a bounded read-only result…"):
                        imported = _api_client().import_database_table(
                            st.session_state.db_connection,
                            selected_table,
                        )
                        dataset_info = load_records(
                            imported["records"],
                            imported["filename"],
                            imported["file_format"],
                            imported.get("file_size_bytes", 0),
                            imported.get("warnings", []),
                        )
                    _set_dataset(dataset_info, "database")
                    st.success(f"Imported {dataset_info.row_count:,} row(s).")
                except (BackendApiError, DataLoaderError) as exc:
                    st.error(str(exc))
            st.button(
                "Disconnect and forget credentials",
                key="db_disconnect",
                on_click=_disconnect_database,
                use_container_width=True,
            )

    st.markdown("---")

    # Dataset info in sidebar
    if st.session_state.file_loaded and st.session_state.dataset_info:
        info = st.session_state.dataset_info
        fmt_icons = {"CSV": "📄", "Excel": "📊", "Excel (Legacy)": "📊", "PDF": "📕"}
        fmt_icon = fmt_icons.get(info.file_format, "📁")

        st.markdown(f"""
        <div class="sidebar-section">
            <div class="format-badge">{fmt_icon} {info.file_format}</div>
            <div style="margin-top:0.75rem;">
                <div style="display:flex;justify-content:space-between;margin-bottom:0.4rem;">
                    <span style="color:#64748b;font-size:0.82rem;">File</span>
                    <span style="color:#1e293b;font-size:0.82rem;font-weight:600;">{html.escape(info.filename[:22])}…</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-bottom:0.4rem;">
                    <span style="color:#64748b;font-size:0.82rem;">Rows</span>
                    <span style="color:#1e293b;font-size:0.82rem;font-weight:600;">{info.row_count:,}</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-bottom:0.4rem;">
                    <span style="color:#64748b;font-size:0.82rem;">Columns</span>
                    <span style="color:#1e293b;font-size:0.82rem;font-weight:600;">{info.column_count}</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-bottom:0.4rem;">
                    <span style="color:#64748b;font-size:0.82rem;">Missing</span>
                    <span style="color:#{'ea580c' if info.has_missing else '16a34a'};font-size:0.82rem;font-weight:600;">{info.total_missing:,}</span>
                </div>
                <div style="display:flex;justify-content:space-between;">
                    <span style="color:#64748b;font-size:0.82rem;">Duplicates</span>
                    <span style="color:#{'ea580c' if info.duplicate_row_count > 0 else '16a34a'};font-size:0.82rem;font-weight:600;">{info.duplicate_row_count:,}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Config info
    cfg = settings.safe_summary()
    key_status = "✅ Connected" if cfg["api_key_configured"] else "❌ Not configured"
    key_color = "#16a34a" if cfg["api_key_configured"] else "#dc2626"
    st.markdown(f"""
    <div class="sidebar-section">
        <div style="font-size:0.78rem;font-weight:700;color:#1e293b;margin-bottom:0.5rem;">⚙️ CONFIGURATION</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:0.3rem;">
            <span style="color:#64748b;font-size:0.78rem;">AI Model</span>
            <span style="color:#4f46e5;font-size:0.78rem;font-weight:600;">{html.escape(str(cfg['model']))}</span>
        </div>
        <div style="display:flex;justify-content:space-between;">
            <span style="color:#64748b;font-size:0.78rem;">API Key</span>
            <span style="color:{key_color};font-size:0.78rem;font-weight:600;">{key_status}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not cfg["api_key_configured"]:
        st.markdown("""
        <div class="alert-warning">
            Set <b>GROQ_API_KEY</b> in your .env file.<br>
            Get an API key: <a href="https://console.groq.com/keys" target="_blank">console.groq.com</a>
        </div>
        """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Main Content
# ---------------------------------------------------------------------------

# Header
header_logo, header_content, account_action = st.columns(
    [0.1, 0.78, 0.12], vertical_alignment="center"
)
with header_logo:
    st.image(str(Path(__file__).parent / "assets" / "brand.svg"), width=68)
with header_content:
    st.markdown("""
    <div class="app-header">
        <h1>AI Data Analyst</h1>
        <p>Explore your data with secure, AI-powered analysis</p>
    </div>
    """, unsafe_allow_html=True)
with account_action:
    if st.button(
        "👤",
        key="header_account_button",
        help="Open your account",
        use_container_width=True,
    ):
        st.session_state.account_page = (
            "Account" if st.session_state.auth_access_token else "Sign in"
        )
        st.rerun()

account_page = st.session_state.account_page
if account_page in {"Sign in", "Create account", "Account"}:
    if account_page == "Account":
        account_column = st.columns([1, 1.4, 1])[1]
        with account_column:
            with st.container(border=True, key="account-profile-card"):
                st.image(str(Path(__file__).parent / "assets" / "brand.svg"), width=72)
                st.markdown('<h2 class="auth-title">Your account</h2>', unsafe_allow_html=True)
                st.markdown(
                    f'<p class="auth-subtitle">{html.escape(st.session_state.auth_email or "Signed in")}</p>',
                    unsafe_allow_html=True,
                )
                if st.button("Sign out", key="account_page_sign_out", use_container_width=True):
                    try:
                        _api_client().sign_out(
                            st.session_state.auth_access_token,
                            st.session_state.auth_refresh_token,
                        )
                    except BackendApiError as exc:
                        st.warning(f"Remote sign-out could not be confirmed: {exc}")
                    _clear_account_state()
                    st.session_state.account_page = "Home"
                    st.rerun()
                if st.button("Back to analysis", key="account_back_home", use_container_width=True):
                    st.session_state.account_page = "Home"
                    st.rerun()
        st.stop()

    auth_feedback = st.session_state.pop("auth_feedback", None)
    auth_column = st.columns([1, 1.4, 1])[1]
    with auth_column:
        with st.container(border=True, key="auth-card"):
            st.image(str(Path(__file__).parent / "assets" / "brand.svg"), width=72)
            st.markdown(
                f'<h2 class="auth-title">'
                f'{"Welcome back" if account_page == "Sign in" else "Create your account"}'
                "</h2>"
                '<p class="auth-subtitle">Optional account for private analysis history</p>',
                unsafe_allow_html=True,
            )
            if auth_feedback:
                if auth_feedback["type"] == "error":
                    st.error(auth_feedback["message"])
                else:
                    st.success(auth_feedback["message"])
            if not settings.app_api_key.strip():
                st.warning(
                    "The API service is not configured. Set APP_API_URL and APP_API_KEY "
                    "to enable accounts."
                )
            if account_page == "Sign in":
                if st.button(
                    "Create an account",
                    key="open_create_account",
                    use_container_width=True,
                ):
                    st.session_state.account_page = "Create account"
                    st.rerun()
            with st.form("account_page_form"):
                st.text_input("Email", key="auth_email_input")
                st.text_input(
                    "Password",
                    type="password",
                    key="auth_password_input",
                    help="Use at least 8 characters when creating an account.",
                )
                st.form_submit_button(
                    "Sign in" if account_page == "Sign in" else "Create account",
                    use_container_width=True,
                    on_click=_authenticate,
                    args=(account_page,),
                )
            if account_page == "Create account":
                if st.button(
                    "Already have an account? Sign in",
                    key="open_sign_in",
                    use_container_width=True,
                ):
                    st.session_state.account_page = "Sign in"
                    st.rerun()
            if st.button("Continue as guest", key="auth_continue_guest"):
                st.session_state.account_page = "Home"
                st.rerun()
    st.stop()


# ── No file loaded state ──
if not st.session_state.file_loaded:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">📄</div>
            <div style="font-weight:700;color:#1e293b;margin-bottom:0.5rem;">CSV Files</div>
            <div style="color:#64748b;font-size:0.88rem;">Upload any comma-separated data file up to 50 MB</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">📊</div>
            <div style="font-weight:700;color:#1e293b;margin-bottom:0.5rem;">Excel Files</div>
            <div style="color:#64748b;font-size:0.88rem;">Upload .xlsx or .xls spreadsheets with multiple sheets</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">📕</div>
            <div style="font-weight:700;color:#1e293b;margin-bottom:0.5rem;">PDF Files</div>
            <div style="color:#64748b;font-size:0.88rem;">Extract tables from PDF reports and documents</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class="card" style="text-align:center;">
            <div style="font-size:2.5rem;margin-bottom:0.75rem;">🔌</div>
            <div style="font-weight:700;color:#1e293b;margin-bottom:0.5rem;">Databases</div>
            <div style="color:#64748b;font-size:0.88rem;">Connect PostgreSQL, MySQL, MongoDB, or Supabase</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="alert-info">
        👈 <b>Get started:</b> Upload a file, select <b>Connect database</b>, or click
        <b>"Load Sample Sales Data"</b> to try a demo.
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ── Dataset loaded ──
info: DatasetInfo = st.session_state.dataset_info

# Show warnings from file loading
for w in info.warnings:
    st.markdown(
        f'<div class="alert-warning">⚠️ {html.escape(w)}</div>',
        unsafe_allow_html=True,
    )

# KPI Cards
numeric_cols = info.df.select_dtypes(include="number").columns
missing_pct = round(info.total_missing / max(info.row_count * info.column_count, 1) * 100, 1)
quality = max(0, 100 - int(missing_pct * 2) - (10 if info.duplicate_row_count > 0 else 0))
fmt_icons = {"CSV": "📄", "Excel": "📊", "Excel (Legacy)": "📊", "PDF": "📕"}

st.markdown(f"""
<div class="kpi-grid">
    <div class="kpi-card">
        <div class="kpi-icon">📋</div>
        <div class="kpi-value">{info.row_count:,}</div>
        <div class="kpi-label">Total Rows</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-icon">🏛️</div>
        <div class="kpi-value">{info.column_count}</div>
        <div class="kpi-label">Columns</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-icon">{'🟠' if missing_pct > 5 else '🟢'}</div>
        <div class="kpi-value">{missing_pct}%</div>
        <div class="kpi-label">Missing Data</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-icon">⭐</div>
        <div class="kpi-value">{quality}</div>
        <div class="kpi-label">Quality Score</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──
tab_chat, tab_explore, tab_stats, tab_schema = st.tabs([
    "💬 AI Chat", "📂 Data Explorer", "📈 Column Stats", "🗂️ Schema"
])


# ══════════════════════════════════════════════════════════════════════════════
# Tab 1: AI Chat
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    # Sample questions
    sample_questions = [
        "What is the total revenue?",
        "Show top 5 products by revenue",
        "Are there missing values?",
        "Plot revenue by category as a bar chart",
        "Detect outliers in numeric columns",
        "Show a correlation heatmap",
        "Generate a data quality report",
        "What are the summary statistics?",
    ]

    st.markdown('<div class="section-title">💡 Sample Questions</div>', unsafe_allow_html=True)
    cols = st.columns(4)
    for i, q in enumerate(sample_questions):
        with cols[i % 4]:
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["prefill_question"] = q

    st.markdown("---")

    # Chat history
    st.markdown('<div class="section-title">💬 Conversation</div>', unsafe_allow_html=True)
    chat_html = '<div class="chat-container">'

    if not st.session_state.chat_history:
        chat_html += """
        <div style="text-align:center;padding:3rem 1rem;color:#94a3b8;">
            <div style="font-size:2.5rem;margin-bottom:0.5rem;">🤖</div>
            <div style="font-weight:600;color:#64748b;">Ask me anything about your dataset</div>
            <div style="font-size:0.85rem;margin-top:0.25rem;">I can calculate, filter, chart, and explain your data</div>
        </div>"""

    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            chat_html += f"""
            <div class="msg-user">
                <div class="msg-user-bubble">{html.escape(str(msg["content"]))}</div>
            </div>"""
        else:
            content = html.escape(str(msg["content"]))
            if msg.get("is_error"):
                chat_html += f'<div class="msg-error">❌ {content}</div>'
            else:
                chat_html += f"""
                <div class="msg-ai">
                    <div class="msg-ai-avatar">✨</div>
                    <div class="msg-ai-bubble">{content}</div>
                </div>"""

    chat_html += "</div>"
    st.markdown(chat_html, unsafe_allow_html=True)

    # Render tables and charts for the latest response
    if "latest_response" in st.session_state and st.session_state.latest_response:
        resp = st.session_state.latest_response

        if resp.tables:
            st.markdown('<div class="section-title">📋 Result Tables</div>', unsafe_allow_html=True)
            for tbl in resp.tables:
                st.markdown(f"**{tbl['title']}**")
                st.dataframe(pd.DataFrame(tbl["data"]), use_container_width=True, hide_index=True)

        if resp.charts:
            st.markdown('<div class="section-title">📈 Charts</div>', unsafe_allow_html=True)
            for chart_data in resp.charts:
                try:
                    fig = build_chart(chart_data)
                    fig.update_layout(
                        paper_bgcolor="#0f172a" if st.session_state.dark_mode else "#ffffff",
                        plot_bgcolor="#1e293b" if st.session_state.dark_mode else "#f8fafc",
                        font_color="#e2e8f0" if st.session_state.dark_mode else "#1e293b",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.warning(f"Could not render chart: {e}")

        if resp.total_tool_calls > 0:
            with st.expander(f"🔧 Tool Calls Used ({resp.total_tool_calls})", expanded=False):
                for tc in resp.tool_calls_made:
                    icon = "✅" if tc["success"] else "❌"
                    st.markdown(f"**{icon} `{tc['name']}`**  ")
                    if tc.get("arguments"):
                        st.json(tc["arguments"])
                    if not tc["success"]:
                        st.error(tc.get("error", "Unknown error"))

    # Question input
    prefill = st.session_state.pop("prefill_question", "")
    question = st.text_input(
        "Ask a question about your data",
        value=prefill,
        placeholder="e.g. What is the average revenue by region?",
        key="chat_input",
        label_visibility="collapsed",
    )

    col_send, col_clear = st.columns([5, 1])
    with col_send:
        send_clicked = st.button("✨ Ask Groq", use_container_width=True, key="send_btn")
    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True, key="clear_btn"):
            st.session_state.chat_history = []
            st.session_state.conversation_messages = []
            st.session_state.latest_response = None
            st.rerun()

    if send_clicked and question.strip():
        st.session_state.chat_history.append({"role": "user", "content": question})

        with st.spinner("🤖 Groq is analysing your data…"):
            try:
                agent_response = run_agent(
                    question=question,
                    dataset_info=info,
                    conversation_history=st.session_state.conversation_messages,
                )
            except Exception as e:
                agent_response = None
                st.error(f"Unexpected error: {e}")

        if agent_response:
            st.session_state.latest_response = agent_response
            st.session_state.conversation_messages.append(
                {"role": "user", "content": question}
            )

            if agent_response.error:
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": agent_response.error,
                    "is_error": True,
                })
            else:
                answer = agent_response.answer or "Analysis complete. See tables and charts below."
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": answer,
                })
                st.session_state.conversation_messages.append(
                    {"role": "assistant", "content": answer}
                )
                if st.session_state.auth_access_token:
                    try:
                        result = _api_client().save_history(
                            st.session_state.auth_access_token,
                            title=question.strip()[:120] or "Data analysis",
                            question=question,
                            answer=answer,
                            refresh_token=st.session_state.auth_refresh_token,
                        )
                        _save_service_tokens(result)
                    except BackendApiError as exc:
                        st.warning(f"Analysis completed, but history could not be saved: {exc}")

        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# Tab 2: Data Explorer
# ══════════════════════════════════════════════════════════════════════════════

with tab_explore:
    st.markdown('<div class="section-title">📋 Data Preview</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        n_rows = st.slider("Rows to display", 5, min(200, info.row_count), 25, key="preview_rows")
    with col2:
        search_col = st.selectbox("Filter column", ["— None —"] + info.column_names, key="search_col")

    df_display = info.df
    if search_col != "— None —":
        search_val = st.text_input(f"Search in '{search_col}'", key="search_val")
        if search_val:
            df_display = df_display[
                df_display[search_col].astype(str).str.contains(search_val, case=False, na=False)
            ]

    st.dataframe(df_display.head(n_rows), use_container_width=True, hide_index=False)

    st.markdown(f"""
    <div style="color:#64748b;font-size:0.82rem;text-align:right;">
        Showing {min(n_rows, len(df_display)):,} of {len(df_display):,} rows
    </div>
    """, unsafe_allow_html=True)

    # Download buttons
    st.markdown('<div class="section-title">⬇️ Download</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        csv_bytes = info.df.to_csv(index=False).encode()
        st.download_button(
            "📄 Download as CSV",
            data=csv_bytes,
            file_name=f"{info.filename.rsplit('.', 1)[0]}_export.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_b:
        schema_json = json.dumps(info.schema_summary(), indent=2, default=str)
        st.download_button(
            "🗂️ Download Schema JSON",
            data=schema_json.encode(),
            file_name="schema.json",
            mime="application/json",
            use_container_width=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tab 3: Column Statistics
# ══════════════════════════════════════════════════════════════════════════════

with tab_stats:
    st.markdown('<div class="section-title">📊 Numeric Column Statistics</div>', unsafe_allow_html=True)

    numeric_df = info.df.select_dtypes(include="number")
    if numeric_df.empty:
        st.info("No numeric columns found in this dataset.")
    else:
        desc = numeric_df.describe().T.round(3)
        desc.insert(0, "Column", desc.index)
        st.dataframe(desc, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">📝 Categorical Column Summary</div>', unsafe_allow_html=True)
    cat_df = info.df.select_dtypes(exclude="number")
    if cat_df.empty:
        st.info("No categorical columns found.")
    else:
        cat_summary = []
        for col in cat_df.columns:
            s = cat_df[col].dropna()
            cat_summary.append({
                "Column": col,
                "Unique Values": s.nunique(),
                "Most Common": s.mode().iloc[0] if not s.empty else "N/A",
                "Missing": int(info.df[col].isna().sum()),
                "Missing %": f"{info.df[col].isna().mean()*100:.1f}%",
            })
        st.dataframe(pd.DataFrame(cat_summary), use_container_width=True, hide_index=True)

    # Missing values chart
    missing_data = {
        col: cnt for col, cnt in info.missing_counts.items() if cnt > 0
    }
    if missing_data:
        st.markdown('<div class="section-title">🟡 Missing Values by Column</div>', unsafe_allow_html=True)
        fig = go.Figure(go.Bar(
            x=list(missing_data.keys()),
            y=list(missing_data.values()),
            marker_color="#f59e0b",
            text=list(missing_data.values()),
            textposition="outside",
        ))
        fig.update_layout(
            paper_bgcolor="#0f172a" if st.session_state.dark_mode else "#ffffff",
            plot_bgcolor="#1e293b" if st.session_state.dark_mode else "#f8fafc",
            font_color="#e2e8f0" if st.session_state.dark_mode else "#1e293b",
            title="Missing Value Counts",
            margin=dict(t=40, b=40),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# Tab 4: Schema
# ══════════════════════════════════════════════════════════════════════════════

with tab_schema:
    st.markdown('<div class="section-title">🗂️ Dataset Schema</div>', unsafe_allow_html=True)

    schema_rows = []
    for col in info.column_names:
        dtype = info.dtypes[col]
        missing = info.missing_counts.get(col, 0)
        missing_pct_col = round(missing / max(info.row_count, 1) * 100, 1)
        is_numeric = "number" in dtype

        schema_rows.append({
            "Column": col,
            "Type": dtype,
            "Category": "Numeric" if is_numeric else "Text/Other",
            "Missing": missing,
            "Missing %": f"{missing_pct_col}%",
        })

    st.dataframe(
        pd.DataFrame(schema_rows),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown('<div class="section-title">📋 Full Schema JSON</div>', unsafe_allow_html=True)
    with st.expander("View raw schema"):
        st.json(info.schema_summary())
