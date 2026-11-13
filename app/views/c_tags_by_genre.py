"""(c) Most popular user tags per genre."""
import streamlit as st

import charts
import data
from auth import require_login
from components import chart_with_table, fmt_int, page_header

ALL = "All genres"

user = require_login()
page_header("(c) What are the most popular user tags in each genre?",
            "Popularity = number of distinct users who used the tag on movies of that genre "
            "(so one prolific tagger cannot dominate); junk tags such as “in netflix queue” or "
            "“dvd” are filtered by a stop list.")

left, right = st.columns([2, 3])
genre = left.selectbox("Genre", [ALL] + data.list_genres()["genre"].tolist(), key="c_genre")
top_n = right.slider("Tags per genre", 3, 15, 5, key="c_top_n")

df = data.popular_tags_by_genre(top_n, None if genre == ALL else genre)
if df.empty:
    st.info("No tags found for this genre.")
    st.stop()

if genre != ALL:
    fig = charts.hbar(
        df["tag"], df["users"],
        title=f"Most popular tags on {genre} movies",
        value_title="Distinct users who used the tag",
        text=[fmt_int(u) for u in df["users"]],
        hover=[f"{t}: {fmt_int(u)} users, {fmt_int(a)} times"
               for t, u, a in zip(df["tag"], df["users"], df["applications"])],
    )
    chart_with_table(fig, df, "c_one")
else:
    st.caption(f"Top {top_n} tags in each of the 19 genres (distinct users).")
    genres = df["genre"].unique().tolist()
    for start in range(0, len(genres), 3):
        for col, g in zip(st.columns(3), genres[start:start + 3]):
            with col:
                st.markdown(f"**{g}**")
                st.dataframe(df.loc[df.genre == g, ["rank", "tag", "users"]], hide_index=True)
    if st.toggle("Show data table", key="c_all_table"):
        st.dataframe(df, hide_index=True)
