"""(b) Top-10 movies by average rating, overall and per release year."""
import streamlit as st

import charts
import data
from auth import require_login
from components import chart_with_table, fmt_int, fmt_year, page_header

user = require_login()
page_header("(b) Which movies have the highest average rating?",
            "Top 10 by average rating among movies with at least the chosen number of ratings, "
            "overall or for one release year. Ties: more ratings first, then title.")

min_ratings = st.slider(
    "Minimum number of ratings", 10, 1000, 50, step=10, key="b_min",
    help="Without a minimum, the top 10 is all obscure films with two or three 5-star ratings. "
         "Half of all movies have 5 ratings or fewer.")


def show(df, scope, key):
    if df.empty:
        st.info(f"No movie {scope} has at least {fmt_int(min_ratings)} ratings. Lower the minimum.")
        return
    if len(df) < 10:
        st.caption(f"Only {len(df)} movies {scope} have at least {fmt_int(min_ratings)} ratings.")
    labels = [f"{t}{fmt_year(y)}" for t, y in zip(df["title"], df["release_year"])]
    fig = charts.hbar(
        labels, df["avg_rating"],
        title=f"Top-rated movies {scope} (at least {fmt_int(min_ratings)} ratings)",
        value_title="Average rating (stars, axis from 0 to 5)", value_range=[0, 5.4],
        text=[f"{v:.3f}" for v in df["avg_rating"]],
        hover=[f"{l}<br>average {a:.3f} from {fmt_int(n)} ratings"
               for l, a, n in zip(labels, df["avg_rating"], df["rating_count"])],
    )
    chart_with_table(fig, df.drop(columns="movie_id"), key, column_config={
        "avg_rating": st.column_config.NumberColumn("avg_rating", format="%.3f"),
        "release_year": st.column_config.NumberColumn("release_year", format="%d"),
    })


overall, by_year = st.tabs(["Overall", "By year"])
with overall:
    show(data.top_movies(min_ratings), "overall", "b_overall")
with by_year:
    years = data.list_years()["release_year"].astype(int).tolist()
    year = st.selectbox("Release year", years, index=years.index(1995) if 1995 in years else 0, key="b_year")
    show(data.top_movies(min_ratings, year), f"from {year}", "b_year")
