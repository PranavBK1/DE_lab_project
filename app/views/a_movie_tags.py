"""(a) Top-5 genome tags for a movie."""
import streamlit as st

import charts
import data
from auth import require_login
from components import fmt_year, movie_picker, page_header, selected_movie, set_movie, chart_with_table

user = require_login()
page_header("(a) Which tags describe a movie best?",
            "The 5 Tag Genome tags with the highest relevance (0 = not at all, 1 = perfectly) for the "
            "movie. The genome scores 1,128 curated tags, but only for 13,816 of the 62,423 movies.")

movie_id = movie_picker("a")
movie = selected_movie(movie_id) if movie_id is not None else None
if movie is None:
    st.info("Search for a movie above to see the tags that describe it.")
    st.stop()

title = f"{movie['title']}{fmt_year(movie['release_year'])}"
st.subheader(title)
tags = data.top_tags_for_movie(movie_id)

if tags.empty:
    st.info("No tag-genome data for this movie (only 13,816 of 62,423 movies have it). "
            "Try one of these well-known movies:")
    for col, row in zip(st.columns(3), data.genome_suggestions(3).itertuples()):
        col.button(f"{row.title}{fmt_year(row.release_year)}", key=f"a_suggest_{row.movie_id}",
                   on_click=set_movie, args=(row.movie_id,), width="stretch")
    st.stop()

fig = charts.hbar(
    tags["tag"], tags["relevance"],
    title=f"What “{movie['title']}” is about: its top 5 genome tags",
    value_title="Relevance (0 to 1)", value_range=[0, 1.08],
    text=[f"{v:.3f}" for v in tags["relevance"]],
    hover=[f"{t}: relevance {v:.3f}" for t, v in zip(tags["tag"], tags["relevance"])],
)
chart_with_table(fig, tags, "a")
