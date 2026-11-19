"""Admin: manage movies, app accounts and ratings (role admin only).

Every write goes through admin_ops (connection role movie_admin). After every
successful write: clear the shared cache, flash a message, rerun.
"""
import streamlit as st

import admin_ops as ops
import data
from auth import require_role
from components import flash, fmt_int, fmt_year, movie_picker, selected_movie
from ratings import VALID_RATINGS

RATING_STEPS = [float(r) for r in VALID_RATINGS]

admin = require_role("admin")          # defence in depth: the menu is not the boundary
st.title("Admin")
st.caption("Changes here are made as the database role movie_admin and take effect immediately.")

genres = data.list_genres()
genre_names = dict(zip(genres["genre_id"], genres["genre"]))


def done(message):
    """After a successful write: drop cached results, show the message after the rerun."""
    data.clear()
    flash(message)
    st.rerun()


def attempt(action, success_message):
    """Run one admin operation; AdminError becomes a friendly st.error."""
    try:
        result = action()
    except ops.AdminError as exc:
        st.error(str(exc))
        return None
    done(success_message(result) if callable(success_message) else success_message)


def genre_select(label, default_ids, key):
    return st.multiselect(label, list(genre_names), default=default_ids,
                          format_func=genre_names.get, key=key)


movies_tab, users_tab, ratings_tab = st.tabs(["Movies", "Users", "Ratings"])

# ================================================================= Movies
with movies_tab:
    st.subheader("Edit a movie")
    movie_id = movie_picker("admin")
    detail = ops.movie_detail(movie_id) if movie_id is not None else None
    if detail is None:
        st.caption("Search for a movie to edit or delete it.")
    else:
        shown = selected_movie(movie_id)
        st.markdown(f"**{shown['title']}{fmt_year(shown['release_year'])}** · movie_id {movie_id} · "
                    f"stored title: `{detail['title']}`")
        with st.form(f"edit_movie_{movie_id}"):
            title = st.text_input("Title (stored form, e.g. “Matrix, The”)", detail["title"])
            year = st.number_input("Release year (0 = unknown)", min_value=0, max_value=ops.MAX_YEAR,
                                   value=detail["release_year"] or 0, step=1)
            new_genres = genre_select("Genres", detail["genre_ids"], f"edit_genres_{movie_id}")
            if st.form_submit_button("Save changes", type="primary"):
                attempt(lambda: ops.update_movie(movie_id, title, year or None, new_genres),
                        f"Saved movie {movie_id}.")

        c = detail["counts"]
        with st.expander("Delete this movie"):
            st.markdown(
                f"Deleting also removes, by cascade: {c['movie_genres']} genre links, {c['links']} "
                f"external link, {fmt_int(c['genome_scores'])} genome scores and {c['movie_stats']} "
                f"stats row. It is **refused** if the movie has ratings or tags "
                f"(this one has {fmt_int(c['ratings'])} ratings and {fmt_int(c['tags'])} tags).")
            confirm = st.checkbox("Yes, delete this movie", key=f"del_movie_ok_{movie_id}")
            if st.button("Delete movie", disabled=not confirm, key=f"del_movie_{movie_id}"):
                st.session_state.pop("movie_id", None)
                attempt(lambda: ops.delete_movie(movie_id), f"Deleted movie {movie_id}.")

    st.subheader("Add a movie")
    with st.form("add_movie", clear_on_submit=True):
        title = st.text_input("Title (put a leading article at the end, e.g. “Matrix, The”)")
        year = st.number_input("Release year (0 = unknown)", min_value=0, max_value=ops.MAX_YEAR,
                               value=2026, step=1)
        new_genres = genre_select("Genres", [], "add_genres")
        if st.form_submit_button("Add movie", type="primary"):
            attempt(lambda: ops.add_movie(title, year or None, new_genres),
                    lambda new_id: f"Added “{title.strip()}” as movie {new_id}.")

# ================================================================= Users
with users_tab:
    st.subheader("App accounts")
    accounts = ops.list_accounts()
    st.dataframe(accounts, hide_index=True, column_config={
        "created_at": st.column_config.DatetimeColumn("created (UTC)", format="YYYY-MM-DD HH:mm")})

    by_id = {a["user_id"]: a for a in accounts}
    chosen = st.selectbox("Manage account", list(by_id), index=None, placeholder="Choose an account",
                          format_func=lambda i: f"{by_id[i]['username']} ({by_id[i]['role']}, id {i})",
                          key="admin_account")
    if chosen is not None:
        acc = by_id[chosen]
        is_me = chosen == admin["user_id"]
        if is_me:
            st.info("This is your own account: you cannot delete it or remove its admin role.")
        left, right = st.columns(2)
        with left.form(f"role_{chosen}"):
            role = st.radio("Role", ops.ROLES, index=ops.ROLES.index(acc["role"]), horizontal=True,
                            disabled=is_me)
            if st.form_submit_button("Change role", disabled=is_me):
                attempt(lambda: ops.set_role(chosen, role, admin["user_id"]),
                        f"{acc['username']} is now {role}.")
        with right.form(f"password_{chosen}", clear_on_submit=True):
            password = st.text_input("New password (at least 8 characters)", type="password")
            if st.form_submit_button("Reset password"):
                attempt(lambda: ops.reset_password(chosen, password),
                        f"Password reset for {acc['username']}.")

        if not is_me:
            with st.expander("Delete this account"):
                if chosen < ops.APP_USER_ID_START:
                    st.warning(f"This account is linked to MovieLens user {chosen}: deleting it removes "
                               "that MovieLens user too.")
                key = f"del_user_{chosen}"
                if st.button("Delete account", key=key):
                    try:
                        ops.delete_account(chosen, admin["user_id"])
                        done(f"Deleted account {acc['username']}.")
                    except ops.HasActivity as exc:
                        st.session_state[f"{key}_activity"] = (exc.ratings, exc.tags)
                    except ops.AdminError as exc:
                        st.error(str(exc))
                if f"{key}_activity" in st.session_state:
                    n_ratings, n_tags = st.session_state[f"{key}_activity"]
                    st.error(f"This user has {fmt_int(n_ratings)} ratings and {fmt_int(n_tags)} tags. "
                             "Delete them first?")
                    ok = st.checkbox(f"Yes, delete their {fmt_int(n_ratings)} ratings, {fmt_int(n_tags)} "
                                     "tags and the account, in one transaction", key=f"{key}_ok")
                    if st.button("Delete everything", disabled=not ok, key=f"{key}_all"):
                        st.session_state.pop(f"{key}_activity")
                        attempt(lambda: ops.delete_account(chosen, admin["user_id"], delete_activity=True),
                                f"Deleted {acc['username']} with their ratings and tags.")

    st.subheader("Create an account")
    with st.form("create_account", clear_on_submit=True):
        username = st.text_input("Username")
        password = st.text_input("Password (at least 8 characters)", type="password")
        role = st.radio("Role", ops.ROLES, horizontal=True)
        if st.form_submit_button("Create account", type="primary"):
            attempt(lambda: ops.create_account(username, password, role),
                    lambda new_id: f"Created {username.strip()} ({role}) with user_id {new_id}.")

# ================================================================= Ratings
with ratings_tab:
    st.subheader("Look up a user's ratings")
    st.caption(f"Only ratings made in this app are listed (from "
               f"{ops.APP_RATINGS_SINCE:%d %b %Y}). The dataset's 1995–2019 ratings are not shown.")
    # Default: the app's own accounts. Any MovieLens user can be looked up by id too,
    # but only the ratings they were given in the app (2026 onwards) are listed.
    source = st.radio("Whose ratings", ["App account", "MovieLens user (by id)"], horizontal=True,
                      key="admin_ratings_source")
    if source == "App account":
        ids = list(by_id)
        first_user = next((i for i in ids if by_id[i]["role"] == "user"), ids[0])
        user_id = st.selectbox("Account", ids, index=ids.index(first_user),
                               format_func=lambda i: f"{by_id[i]['username']} (id {i})",
                               key="admin_ratings_account")
    else:
        user_id = st.number_input("MovieLens user_id (1 to 162,541)", min_value=1,
                                  max_value=ops.APP_USER_ID_START - 1, value=1, step=1,
                                  key="admin_ratings_user")
    rows = ops.user_ratings(int(user_id))
    if not rows:
        st.info(f"User {user_id} has no ratings made in the app.")
    else:
        st.caption(f"{len(rows)} most recent app ratings of user {user_id}." if len(rows) == 200
                   else f"{len(rows)} app ratings of user {user_id}, newest first.")
        st.dataframe(rows, hide_index=True, column_config={
            "rated_at": st.column_config.DatetimeColumn("rated (UTC)", format="YYYY-MM-DD HH:mm")})
        labels = {r["movie_id"]: f"{r['title']}{fmt_year(r['release_year'])}: {float(r['rating']):.1f}"
                  for r in rows}
        movie = st.selectbox("Rating to change", list(labels), format_func=labels.get, key="admin_rating_movie")
        current = next(float(r["rating"]) for r in rows if r["movie_id"] == movie)
        left, right = st.columns(2)
        with left.form(f"admin_rate_{user_id}_{movie}"):
            value = st.select_slider("New rating", RATING_STEPS, value=current, format_func=lambda v: f"{v:.1f}")
            if st.form_submit_button("Update rating", type="primary"):
                attempt(lambda: ops.update_rating(int(user_id), movie, value),
                        f"Rating of user {user_id} for movie {movie} is now {value:.1f}.")
        with right:
            ok = st.checkbox("Yes, delete this rating", key=f"admin_del_ok_{user_id}_{movie}")
            if st.button("Delete rating", disabled=not ok, key=f"admin_del_{user_id}_{movie}"):
                attempt(lambda: ops.delete_rating(int(user_id), movie),
                        f"Deleted the rating of user {user_id} for movie {movie}.")
