"""Login, logout and page guards.

Current login (local demo, used by app/Home.py): NO password.
  list_accounts() gives the app accounts (admin, demo_user1..3); the visitor picks
  one and login_as(username) returns {user_id, username, role}. Anyone who can open
  the page can pick any account, so this is for a demo on one machine only. What
  an account may see and do is still decided by its role and by PostgreSQL
  (grants + row-level security).

Password login (kept, tested, not used by the login page):
  1. login() connects as movie_app_user and calls auth_login(username, password),
     a SECURITY DEFINER function (sql/roles.sql).
  2. PostgreSQL checks the password with pgcrypto's bcrypt:
         password_hash = crypt(password, password_hash)
     The hash never leaves the database; the app never sees it.
  3. A correct password returns one row (user_id, username, role); anything
     else returns no row.
  4. On success, st.session_state["user"] holds {user_id, username, role}.
Every failure (unknown user, wrong password, MovieLens user with no password)
gets the same generic message, so the login form cannot be used to find out
which usernames exist.
"""
import streamlit as st

from db import user_conn

LOGIN_FAILED = "Invalid username or password."


def login(username, password, conn=None):
    """Return {user_id, username, role} on success, None on any failure.
    `conn` lets the tests run the check inside a transaction they roll back."""
    if not username or not password:
        return None
    query = "SELECT user_id, username, role FROM auth_login(%s, %s)"
    if conn is None:
        with user_conn() as own:
            row = own.execute(query, (username, password)).fetchone()
    else:
        row = conn.execute(query, (username, password)).fetchone()
    if row is None:
        return None
    user_id, name, role = row
    return {"user_id": user_id, "username": name, "role": role}


def list_accounts():
    """App accounts that can log in (MovieLens users have no username)."""
    with user_conn() as conn:
        return [r[0] for r in conn.execute(
            "SELECT username FROM users WHERE username IS NOT NULL "
            "ORDER BY role = 'admin' DESC, username").fetchall()]


def login_as(username):
    """Password-free login for the local demo: pick an account, get its role.
    Roles, row-level security and the admin/user split still apply."""
    with user_conn() as conn:
        row = conn.execute("SELECT user_id, username, role FROM users WHERE username = %s",
                           (username,)).fetchone()
    if row is None:
        return None
    user_id, name, role = row
    return {"user_id": user_id, "username": name, "role": role}


def logout():
    st.session_state.clear()


def current_user():
    return st.session_state.get("user")


def require_login():
    """Call at the top of every page: stops the page if nobody is logged in."""
    user = current_user()
    if user is None:
        st.warning("Please log in on the Home page first.")
        st.stop()
    return user


def require_role(role):
    """Stops the page unless the logged-in user has this role (e.g. 'admin')."""
    user = require_login()
    if user["role"] != role:
        st.error("You do not have permission to view this page.")
        st.stop()
    return user
