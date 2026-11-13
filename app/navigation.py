"""Which pages each role sees (used by Home.py to build st.navigation).

Kept as plain data so it can be unit-tested without running Streamlit.
The menu is NOT the security boundary: every view also calls
require_login() / require_role("admin"), and the database roles enforce
what each connection may do.
"""
LOGIN = "login"

# (section, path relative to app/, menu title, icon)
ANALYSIS = [
    ("Explore", "views/overview.py",              "Overview",                  ":material/dashboard:"),
    ("Explore", "views/a_movie_tags.py",          "(a) Tags of a movie",       ":material/sell:"),
    ("Explore", "views/b_top_movies.py",          "(b) Top-rated movies",      ":material/trophy:"),
    ("Explore", "views/c_tags_by_genre.py",       "(c) Popular tags by genre", ":material/tag:"),
    ("Explore", "views/d_rating_distribution.py", "(d) Rating distribution",   ":material/bar_chart:"),
    ("Explore", "views/e_ratings_per_movie.py",   "(e) Ratings per movie",     ":material/stacked_bar_chart:"),
    ("Explore", "views/f_genre_by_year.py",       "(f) Top genre by year",     ":material/calendar_month:"),
    ("Explore", "views/g_genre_coverage.py",      "(g) Genre coverage",        ":material/category:"),
]
MY_RATINGS = [("You", "views/my_ratings.py", "My ratings", ":material/star:")]
ADMIN = [("Admin", "views/admin.py", "Admin", ":material/admin_panel_settings:")]


def pages_for(role):
    """role: None (logged out), 'user' or 'admin'. Returns the page specs in menu order."""
    if role is None:
        return [("", LOGIN, "Log in", ":material/login:")]
    pages = ANALYSIS + MY_RATINGS
    if role == "admin":
        pages = pages + ADMIN
    return pages
