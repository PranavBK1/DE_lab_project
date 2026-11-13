"""(e) Distribution of the number of ratings per movie."""
import streamlit as st

import charts
import data
from auth import require_login
from components import chart_with_table, fmt_int, metric_row, page_header

user = require_login()
page_header("(e) How many ratings does a movie get?",
            "All 62,423 movies grouped by their number of ratings (unrated movies count as 0). "
            "Each bucket is about 10× wider than the one before (a log scale), because the "
            "distribution is extremely skewed.")

s = data.ratings_per_movie_summary().iloc[0]
metric_row([
    ("Median ratings per movie", fmt_int(s["median"])),
    ("Mean ratings per movie", f"{s['mean']:,.1f}"),
    ("Most ratings for one movie", fmt_int(s["max"])),
    (f"Share of all ratings for the top 10% ({fmt_int(s['top10pct_movies'])} movies)",
     f"{s['top10pct_share_pct']:.1f}%"),
])
st.markdown(f"**A long tail:** half of all movies have {fmt_int(s['median'])} ratings or fewer, "
            f"while the most-rated 10% of movies received {s['top10pct_share_pct']:.1f}% of all ratings.")

hist = data.ratings_per_movie_distribution().sort_values("sort_order")
log_y = st.checkbox("Log scale (y axis)", key="e_log",
                    help="Makes the small buckets on the right easier to compare.")
fig = charts.vbar(
    hist["bucket"], hist["movie_count"],
    title="Most movies have only a handful of ratings",
    x_title="Number of ratings a movie has", y_title="Number of movies", log_y=log_y,
    text=[fmt_int(c) for c in hist["movie_count"]],
    hover=[f"{b} ratings: {fmt_int(c)} movies ({p:.2f}% of all movies)"
           for b, c, p in zip(hist["bucket"], hist["movie_count"], hist["pct"])],
)
chart_with_table(fig, hist.drop(columns="sort_order"), "e")
