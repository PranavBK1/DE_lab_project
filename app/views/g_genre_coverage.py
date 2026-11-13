"""(g) Count and share of movies (or ratings) per genre."""
import streamlit as st

import charts
import data
from auth import require_login
from components import chart_with_table, fmt_int, page_header

MOVIES, RATINGS = "Share of movies", "Share of ratings"

user = require_login()
page_header("(g) How many movies does each genre cover?",
            "Per genre, the share of ALL 62,423 movies (or of all ratings), plus a “(no genre)” row "
            "for the 5,062 movies listed without a genre.")

measure = st.radio("Show", [MOVIES, RATINGS], horizontal=True, key="g_measure")
df = data.genre_coverage()
if measure == MOVIES:
    pct, count, unit = "pct_of_all_movies", "movie_count", "movies"
else:
    pct, count, unit = "pct_of_all_ratings", "rating_count", "ratings"
df = df.sort_values(pct, ascending=False)

fig = charts.hbar(
    df["genre"], df[pct],
    title=f"{measure} per genre",
    value_title=f"% of all {unit}",
    highlight=[g != "(no genre)" for g in df["genre"]],
    text=[f"{v:.1f}%" for v in df[pct]],
    hover=[f"{g}: {v:.2f}% of all {unit} ({fmt_int(c)} {unit})"
           for g, v, c in zip(df["genre"], df[pct], df[count])],
)
chart_with_table(fig, df, "g")
st.caption(f"The shares add up to more than 100% ({df[pct].sum():.0f}% here), because many movies "
           "have several genres and count once in each.")
