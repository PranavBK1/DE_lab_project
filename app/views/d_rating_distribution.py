"""(d) Rating distribution for a movie, and rate it yourself (the live-demo moment)."""
import streamlit as st

import charts
import data
import queries
from auth import require_login
from components import (chart_with_table, fmt_int, fmt_year, metric_row, movie_picker,
                        page_header, rating_control, selected_movie)

user = require_login()
page_header("(d) How are a movie's ratings spread over the stars?",
            "Number of ratings at each of the 10 values from 0.5 to 5.0 stars, including values "
            "nobody chose (0). The percentage is the share of this movie's ratings.")

movie_id = movie_picker("d")
movie = selected_movie(movie_id) if movie_id is not None else None
if movie is None:
    st.info("Search for a movie above to see how its ratings are distributed.")
    st.stop()

title = f"{movie['title']}{fmt_year(movie['release_year'])}"
st.subheader(title)
mine = queries.my_rating_for_movie(user["user_id"], movie_id)          # per-user: not cached
metric_row([
    ("Average rating", "–" if movie["rating_count"] == 0 else f"{movie['avg_rating']:.3f} ★"),
    ("Number of ratings", fmt_int(movie["rating_count"])),
    ("Your rating", "not rated" if mine is None else f"{mine:.1f} ★"),
])

dist = data.rating_distribution(movie_id)
if movie["rating_count"] == 0:
    st.info("Nobody has rated this movie yet: every value is 0. Be the first, below.")
fig = charts.vbar(
    [f"{r:.1f}" for r in dist["rating"]], dist["count"],
    title=f"How {fmt_int(movie['rating_count'])} people rated “{movie['title']}”",
    x_title="Rating (stars)", y_title="Number of ratings",
    text=[fmt_int(c) for c in dist["count"]],
    hover=[f"{r:.1f} stars: {fmt_int(c)} ratings ({p:.2f}%)"
           for r, c, p in zip(dist["rating"], dist["count"], dist["pct"])],
)
chart_with_table(fig, dist, "d")

st.subheader("Rate this movie")
rating_control(user, movie_id, title, "d_rate")
