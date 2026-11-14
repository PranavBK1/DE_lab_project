"""MovieLens dashboard: entrypoint.  Run with:  streamlit run app/Home.py

- page config and the login gate
- navigation built from the logged-in role (st.navigation, see navigation.py):
      logged out -> only the login page
      user       -> Overview, questions (a)-(g), My ratings
      admin      -> the same + Admin
  The page modules live in app/views/, NOT app/pages/: Streamlit would list
  every file in pages/ for everybody. The menu is not the security boundary:
  every view also calls require_login() / require_role("admin") itself, and
  the database roles enforce what each user can do.
- logout in the sidebar
- if the database is unreachable: one friendly message, details in the console
"""
import logging

import psycopg
import streamlit as st

from auth import current_user, list_accounts, login_as, logout
from components import show_flash
from db import DB_UNAVAILABLE, reset_pools
from navigation import LOGIN, pages_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("movielens.app")

st.set_page_config(page_title="MovieLens Dashboard", page_icon="🎬", layout="wide")


def login_page():
    st.title("MovieLens Dashboard")
    st.caption("DS5003 Data Engineering Lab: the MovieLens 25M dataset in PostgreSQL. "
               "Choose an account to log in (no password needed for this demo).")
    with st.form("login"):
        username = st.selectbox("Account", list_accounts())
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        user = login_as(username)
        if user is None:                 # the account was deleted after the list was shown
            st.error("That account no longer exists. Refresh the page and choose another.")
        else:
            st.session_state["user"] = user
            st.rerun()


def build_navigation(user):
    """{section: [st.Page, ...]} for this user's role."""
    sections = {}
    for i, (section, path, title, icon) in enumerate(pages_for(user["role"] if user else None)):
        target = login_page if path == LOGIN else path
        sections.setdefault(section, []).append(st.Page(target, title=title, icon=icon, default=(i == 0)))
    return sections.get("") or sections          # logged out: a plain list, no section header


user = current_user()
page = st.navigation(build_navigation(user))

if user is not None:
    with st.sidebar:
        st.caption(f"Logged in as **{user['username']}** ({user['role']})")
        if st.button("Log out", icon=":material/logout:"):
            logout()
            st.rerun()

show_flash()
try:
    page.run()
except DB_UNAVAILABLE as exc:
    log.error("database unavailable: %r", exc)
    st.error("Database unavailable, please try again.")
except psycopg.Error as exc:
    # Any other database error, e.g. a table missing or changed because the
    # database is being reloaded or migrated. Never show a traceback; drop the
    # pooled connections and cached results so the next try starts clean.
    log.error("database error on page %s: %r", page.title, exc)
    reset_pools()
    st.cache_data.clear()
    st.error("The database returned an error. If it is being reloaded or updated, "
             "wait a minute and refresh the page.")
