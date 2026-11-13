"""Overview: headline numbers of the dataset, and links to every question."""
import streamlit as st

import data
from auth import require_login
from components import fmt_int, metric_row

user = require_login()

st.title("MovieLens 25M at a glance")
st.caption("Ratings and tags from MovieLens users, loaded into PostgreSQL. "
           "Counts of movies, users and ratings are live; tags, genome data and the "
           "rating period describe the dataset as loaded.")

m = data.overview_metrics().iloc[0]
metric_row([
    ("Movies", fmt_int(m["movies"])),
    ("Users", fmt_int(m["users"]), "MovieLens users plus the app's own accounts"),
    ("Ratings", fmt_int(m["ratings"]), "0.5 to 5.0 stars; includes ratings made in this app"),
    ("Tags", fmt_int(m["tags"]), "free-text tags that users applied to movies"),
])
metric_row([
    ("Movies with genome data", f"{fmt_int(m['genome_movies'])} ({m['genome_pct']:.1f}%)",
     "The Tag Genome scores 1,128 tags for each of these movies"),
    ("Ratings from", f"{m['first_rated_at']:%d %b %Y}"),
    ("Ratings until", f"{m['last_rated_at']:%d %b %Y}", "Last rating in the MovieLens data"),
])

st.subheader("What you can explore")
LINKS = [
    ("views/a_movie_tags.py",          "(a) Which tags describe a movie best?"),
    ("views/b_top_movies.py",          "(b) Which movies have the highest average rating?"),
    ("views/c_tags_by_genre.py",       "(c) What are the most popular user tags in each genre?"),
    ("views/d_rating_distribution.py", "(d) How are a movie's ratings spread over the stars? You can rate it too."),
    ("views/e_ratings_per_movie.py",   "(e) How many ratings does a movie get?"),
    ("views/f_genre_by_year.py",       "(f) Which genre had the most releases in a given year?"),
    ("views/g_genre_coverage.py",      "(g) How many movies and ratings does each genre cover?"),
    ("views/my_ratings.py",            "My ratings: everything you have rated, and edit it"),
]
for path, label in LINKS:
    st.page_link(path, label=label)
