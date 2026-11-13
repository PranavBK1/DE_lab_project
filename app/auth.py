"""Login, logout and page guards.

Login flow:
  1. auth_get_user(username) (a SECURITY DEFINER function) returns the user's
     id, bcrypt hash and role. The app role cannot read users.password_hash
     directly.
  2. bcrypt.checkpw compares the typed password with the hash, in Python.
  3. On success, st.session_state["user"] holds {user_id, username, role}.
Every failure (unknown user, wrong password, MovieLens user with no password)
gets the same generic message, so a login form cannot be used to find out
which usernames exist.
"""
import bcrypt
import streamlit as st

from db import user_conn

LOGIN_FAILED = "Invalid username or password."

# Checked against when the username is unknown, so a failed login takes about
# as long either way (bcrypt is deliberately slow).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


def check_password(row, password):
    """row = (user_id, password_hash, role) from auth_get_user, or None.
    Returns {user_id, role} if the password matches, else None."""
    if row is None or row[1] is None:            # unknown user, or no password set
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        return None
    user_id, password_hash, role = row
    if not bcrypt.checkpw(password.encode(), password_hash.encode()):
        return None
    return {"user_id": user_id, "role": role}


def login(username, password, conn=None):
    """Return {user_id, username, role} on success, None on any failure.
    `conn` lets the tests run the lookup inside a transaction they roll back."""
    if not username or not password:
        return None
    query = "SELECT user_id, password_hash, role FROM auth_get_user(%s)"
    if conn is None:
        with user_conn() as own:
            row = own.execute(query, (username,)).fetchone()
    else:
        row = conn.execute(query, (username,)).fetchone()
    user = check_password(row, password)
    if user is None:
        return None
    return {**user, "username": username}


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
