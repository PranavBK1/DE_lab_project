"""My ratings: rate a movie, and see / edit everything I have rated.

PER-USER DATA: read straight from queries.py, never through the shared cache.
"""
import math

import streamlit as st

import queries
from auth import require_login
from components import fmt_int, fmt_year, movie_picker, rating_control, selected_movie

PAGE_SIZE = 25

user = require_login()
st.title("My ratings")
st.caption("Users may change ratings only, and only their own: the database checks every "
           "write against the logged-in user (row-level security). Deleting a rating is not "
           "possible for users: their database role has no DELETE permission.")

# ----------------------------------------------------------------- rate a movie
st.subheader("Rate a movie")
movie_id = movie_picker("mine")
movie = selected_movie(movie_id) if movie_id is not None else None
if movie is None:
    st.caption("Search for a movie to rate it.")
else:
    title = f"{movie['title']}{fmt_year(movie['release_year'])}"
    if movie["rating_count"] == 0:
        st.markdown(f"**{title}** · no ratings yet")
    else:
        st.markdown(f"**{title}** · average {movie['avg_rating']:.3f} from "
                    f"{fmt_int(movie['rating_count'])} ratings")
    rating_control(user, movie_id, title, "mine_rate")

# ----------------------------------------------------------------- my ratings
st.subheader("Everything I have rated")
first = queries.my_ratings(user["user_id"], 1, 0)
total = 0 if first.empty else int(first["total"].iloc[0])
if total == 0:
    st.info("You have not rated any movies yet. Rate one above, or on page (d).")
    st.stop()

pages = math.ceil(total / PAGE_SIZE)
page = st.number_input(f"Page (of {pages}; {fmt_int(total)} ratings, newest first)",
                       min_value=1, max_value=pages, value=1, step=1, key="mine_page")
rows = queries.my_ratings(user["user_id"], PAGE_SIZE, (page - 1) * PAGE_SIZE)
table = rows.assign(
    movie=[f"{t}{fmt_year(y)}" for t, y in zip(rows["title"], rows["release_year"])],
)[["movie", "my_rating", "avg_rating", "rated_at", "movie_id"]]

st.caption("Select a row to change that rating.")
event = st.dataframe(
    table, hide_index=True, on_select="rerun", selection_mode="single-row", key=f"mine_table_{page}",
    column_order=["movie", "my_rating", "avg_rating", "rated_at"],
    column_config={
        "movie": st.column_config.TextColumn("Movie", width="large"),
        "my_rating": st.column_config.NumberColumn("My rating", format="%.1f ★"),
        "avg_rating": st.column_config.NumberColumn("Movie average", format="%.3f"),
        "rated_at": st.column_config.DatetimeColumn("Rated (UTC)", format="YYYY-MM-DD HH:mm"),
    },
)
selected = event.selection.rows
if selected:
    row = table.iloc[selected[0]]
    st.markdown(f"**Change your rating of {row['movie']}**")
    rating_control(user, int(row["movie_id"]), row["movie"], f"mine_edit_{int(row['movie_id'])}")
