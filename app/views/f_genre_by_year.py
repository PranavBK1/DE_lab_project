"""(f) Genre with the most releases in a selected year (ties shown)."""
import streamlit as st

import charts
import data
from auth import require_login
from components import chart_with_table, fmt_int, page_header

user = require_login()
page_header("(f) Which genre had the most releases in a given year?",
            "Movies released that year in each genre; a movie with several genres counts in each. "
            "All 19 genres are shown, and every genre tied for first place is marked as top.")

years = data.list_years()
year_list = years["release_year"].astype(int).tolist()
default = 1995 if 1995 in year_list else int(years.loc[years.movie_count.idxmax(), "release_year"])
year = st.selectbox("Release year", year_list, index=year_list.index(default), key="f_year")

df = data.top_genre_for_year(year)
top = df[df["is_top"]]
if top.empty:
    st.info(f"No movies with a genre were released in {year}.")
    st.stop()

n = fmt_int(top["movie_count"].iloc[0])
if len(top) == 1:
    st.markdown(f"### In {year} the top genre was **{top['genre'].iloc[0]}** ({n} movies)")
else:
    names = ", ".join(top["genre"].iloc[:-1]) + " and " + top["genre"].iloc[-1]
    st.markdown(f"### In {year} there was a tie for the top genre: **{names}** ({n} movies each)")

fig = charts.hbar(
    df["genre"], df["movie_count"],
    title=f"Movies released in {year}, per genre",
    value_title="Number of movies", highlight=df["is_top"].tolist(),
    text=[fmt_int(c) for c in df["movie_count"]],
    hover=[f"{g}: {fmt_int(c)} movies (rank {r})"
           for g, c, r in zip(df["genre"], df["movie_count"], df["rank"])],
)
chart_with_table(fig, df, "f")
