"""MovieLens dashboard: login page.  Run with:  streamlit run app/Home.py"""
import streamlit as st

from auth import LOGIN_FAILED, current_user, login, logout

st.set_page_config(page_title="MovieLens Dashboard", page_icon="🎬")
st.title("MovieLens Dashboard")

user = current_user()

if user is None:
    with st.form("login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        user = login(username.strip(), password)
        if user is None:
            st.error(LOGIN_FAILED)
        else:
            st.session_state["user"] = user
            st.rerun()
else:
    st.success(f"Logged in as **{user['username']}** ({user['role']})")
    if st.button("Log out"):
        logout()
        st.rerun()
