"""Phase 7: the Streamlit app, driven by streamlit.testing.v1.AppTest.

Covers role-based navigation, the access checks inside the views, every page
running without exceptions, the (d) rating flow, and the admin operations'
safety rules. Tests that commit data restore the original state in teardown
(as the superuser), so the database is left unchanged.
"""
import os

import psycopg
import pytest
from streamlit.testing.v1 import AppTest

import admin_ops as ops
from db import ROOT
from navigation import pages_for

HOME = str(ROOT / "app" / "Home.py")
USER = {"user_id": 1, "username": "demo_user1", "role": "user"}
TIMEOUT = 60

ANALYSIS_VIEWS = ["overview", "a_movie_tags", "b_top_movies", "c_tags_by_genre",
                  "d_rating_distribution", "e_ratings_per_movie", "f_genre_by_year",
                  "g_genre_coverage", "my_ratings"]


def superuser():
    return psycopg.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"],
                           dbname=os.environ["PG_DB"], user=os.environ["PG_SUPERUSER"],
                           password=os.environ["PG_SUPERPASSWORD"])


@pytest.fixture(scope="module")
def admin_user():
    with superuser() as conn:
        user_id = conn.execute("SELECT user_id FROM users WHERE username = %s",
                               (os.environ["DEMO_ADMIN_USERNAME"],)).fetchone()[0]
    return {"user_id": user_id, "username": os.environ["DEMO_ADMIN_USERNAME"], "role": "admin"}


@pytest.fixture(scope="module")
def small_movie():
    """A movie with genome data and few ratings (fast pages), not rated by demo_user1."""
    with superuser() as conn:
        return conn.execute("""
            SELECT s.movie_id FROM movie_stats s
             WHERE s.rating_count BETWEEN 100 AND 300
               AND EXISTS (SELECT 1 FROM genome_scores g WHERE g.movie_id = s.movie_id)
               AND NOT EXISTS (SELECT 1 FROM ratings r WHERE r.user_id = 1 AND r.movie_id = s.movie_id)
             ORDER BY s.movie_id LIMIT 1""").fetchone()[0]


def app_as(user, page=None, movie_id=None):
    at = AppTest.from_file(HOME, default_timeout=TIMEOUT)
    if user is not None:
        at.session_state["user"] = user
    if movie_id is not None:
        at.session_state["movie_id"] = movie_id
    at.run()
    if page is not None:
        at.switch_page(f"views/{page}.py")
        at.run()
    return at


def titles(at):
    return [t.value for t in at.title]


# ----------------------------------------------------------------- navigation by role
def test_navigation_lists_by_role():
    logged_out = [p[1] for p in pages_for(None)]
    user = [p[1] for p in pages_for("user")]
    admin = [p[1] for p in pages_for("admin")]
    assert logged_out == ["login"]
    assert "views/admin.py" not in user and "views/my_ratings.py" in user
    assert admin == user + ["views/admin.py"]
    assert len(user) == 9                         # overview + (a)-(g) + my ratings


def test_logged_out_sees_only_login():
    at = app_as(None)
    assert titles(at) == ["MovieLens Dashboard"]
    assert [b.label for b in at.button] == ["Log in"]
    assert not at.exception


# ----------------------------------------------------------------- login form (username + password)
def submit_login(username, password):
    """Fill in the login form the way a visitor does and press Log in."""
    at = app_as(None)
    at.text_input[0].input(username)
    at.text_input[1].input(password)
    at.button[0].click().run()
    return at


def test_login_page_asks_for_username_and_password_and_lists_no_accounts():
    """The form has a username box and a masked password box, and offers no list of
    accounts: the page must not reveal which usernames exist."""
    at = app_as(None)
    assert [t.label for t in at.text_input] == ["Username", "Password"]
    username_box, password_box = at.text_input[0].proto, at.text_input[1].proto
    password_type = type(password_box).Type.Value("PASSWORD")
    assert password_box.type == password_type        # what is typed is masked
    assert username_box.type != password_type
    assert not at.selectbox


@pytest.mark.parametrize("username, role, has_admin", [
    ("demo_user1", "user", False),
    ("demo_user2", "user", False),
    ("demo_user3", "user", False),
    ("admin", "admin", True)])
def test_correct_password_logs_in_with_the_accounts_role(username, role, has_admin, demo_password):
    at = submit_login(username, demo_password(username))
    user = at.session_state["user"]
    assert user["username"] == username and user["role"] == role
    assert "password_hash" not in user and "password" not in user   # nothing secret kept in the session
    assert titles(at) == ["MovieLens 25M at a glance"]              # landed on the Overview
    assert not at.exception
    # the role decides the menu: only an admin gets the Admin page
    reached = try_switch(user, "admin")
    assert (reached is not None and "Admin" in " ".join(titles(reached))) == has_admin


@pytest.mark.parametrize("username, password", [
    ("demo_user1", "not-the-password"),      # wrong password
    ("admin", "not-the-password"),           # wrong password for the admin
    ("no_such_user", "not-the-password"),    # unknown username
    ("demo_user1", ""),                      # empty password
    ("", "not-the-password"),                # empty username
])
def test_wrong_login_is_refused_with_one_generic_message(username, password):
    at = submit_login(username, password)
    assert "user" not in at.session_state                           # not logged in
    assert [e.value for e in at.error] == ["Invalid username or password."]
    assert titles(at) == ["MovieLens Dashboard"]                    # still on the login page


def test_admin_password_does_not_open_a_user_account(demo_password):
    """Each account needs its own password."""
    at = submit_login("demo_user1", demo_password("admin"))
    assert "user" not in at.session_state


def test_login_page_shows_no_passwords():
    """Nothing on the login page lists the logins or their passwords: no table, and
    no text mentions a password (the only "Password" is the masked input's label)."""
    at = app_as(None)
    assert not at.table and not at.dataframe
    page_text = " ".join(str(e.value) for kind in (at.markdown, at.caption, at.title, at.text, at.info)
                         for e in kind)
    assert "password" not in page_text.lower()
    assert "demo_user" not in page_text


def test_there_is_no_password_free_login_left():
    """The demo-only account picker is gone: the only way in is auth.login with a password."""
    import auth
    assert not hasattr(auth, "login_as") and not hasattr(auth, "list_accounts")


def try_switch(user, page):
    """Try to open a page that is NOT in this user's navigation.
    Streamlit <= 1.5x lands on the default page; newer versions refuse the switch
    with ValueError ("Could not find a navigation page"). Both mean: no access.
    Returns the AppTest, or None when the switch was refused."""
    at = app_as(user)
    try:
        at.switch_page(f"views/{page}.py")
    except ValueError as exc:
        assert "Could not find a navigation page" in str(exc)
        return None
    return at.run()


def test_logged_out_cannot_switch_to_a_page():
    at = try_switch(None, "admin")
    if at is not None:
        assert titles(at) == ["MovieLens Dashboard"]      # still the login page
        assert not at.tabs


def test_user_has_no_admin_page():
    at = try_switch(USER, "admin")                # not in the user's navigation
    if at is not None:
        assert "Admin" not in titles(at)
        assert titles(at) == ["MovieLens 25M at a glance"]
        assert not at.exception


def test_admin_view_run_directly_as_user_is_denied():
    """Defence in depth: even if the admin page were reached, the view itself refuses."""
    at = AppTest.from_file(str(ROOT / "app" / "views" / "admin.py"), default_timeout=TIMEOUT)
    at.session_state["user"] = USER
    at.run()
    assert [e.value for e in at.error] == ["You do not have permission to view this page."]
    assert not at.tabs and not at.dataframe


def test_view_run_directly_logged_out_asks_to_log_in():
    at = AppTest.from_file(str(ROOT / "app" / "views" / "b_top_movies.py"), default_timeout=TIMEOUT)
    at.run()
    assert [w.value for w in at.warning] == ["Please log in on the Home page first."]
    assert not at.dataframe


def test_admin_has_admin_page(admin_user):
    at = app_as(admin_user, page="admin")
    assert titles(at) == ["Admin"]
    assert [t.label for t in at.tabs] == ["Movies", "Users", "Ratings"]
    assert not at.exception


# ----------------------------------------------------------------- every page runs
@pytest.mark.parametrize("view", ANALYSIS_VIEWS)
def test_view_runs_with_defaults(view):
    at = app_as(USER, page=view)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert titles(at)


@pytest.mark.parametrize("view", ["a_movie_tags", "d_rating_distribution", "my_ratings"])
def test_movie_views_run_with_a_movie(view, small_movie):
    at = app_as(USER, page=view, movie_id=small_movie)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error


def test_a_movie_without_genome_data_suggests_others():
    with superuser() as conn:
        movie_id = conn.execute("""SELECT m.movie_id FROM movies m WHERE NOT EXISTS
                                   (SELECT 1 FROM genome_scores g WHERE g.movie_id = m.movie_id)
                                   ORDER BY m.movie_id LIMIT 1""").fetchone()[0]
    at = app_as(USER, page="a_movie_tags", movie_id=movie_id)
    assert any("No tag-genome data" in i.value for i in at.info)
    assert len([b for b in at.button if b.key and b.key.startswith("a_suggest_")]) == 3


def test_admin_page_tabs_run(admin_user, small_movie):
    at = app_as(admin_user, page="admin", movie_id=small_movie)
    assert not at.exception and not at.error


# ----------------------------------------------------------------- (d) rating flow
def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_overview_separates_user_tags_from_genome_tags():
    """'User tags applied' (rows of tags) and 'Genome tags' (the genome vocabulary)
    are different things; the Overview labels and counts them separately."""
    with superuser() as conn:
        user_tags, genome_tags = conn.execute(
            "SELECT (SELECT count(*) FROM tags), (SELECT count(*) FROM genome_tags)").fetchone()
    at = app_as({"user_id": 1, "username": "demo_user1", "role": "user"})
    assert metric(at, "User tags applied") == f"{user_tags:,}"
    assert metric(at, "Genome tags") == f"{genome_tags:,}"
    assert "Tags" not in [m.label for m in at.metric]     # the ambiguous old label is gone


def test_d_rating_flow_updates_the_average(small_movie):
    """Save a rating on page (d): the shown count and average change.
    Teardown deletes the rating as superuser; the trigger restores movie_stats."""
    with superuser() as conn:
        before = conn.execute("SELECT rating_count, rating_sum FROM movie_stats WHERE movie_id = %s",
                              (small_movie,)).fetchone()
    try:
        at = app_as(USER, page="d_rating_distribution", movie_id=small_movie)
        count_before, avg_before = metric(at, "Number of ratings"), metric(at, "Average rating")
        assert metric(at, "Your rating") == "not rated"

        at.select_slider(key="d_rate_value").set_value(5.0)
        next(b for b in at.button if b.label == "Save rating").click()
        at.run()

        assert not at.exception, [e.value for e in at.exception]
        assert any("Saved 5.0 stars" in s.value and "New average" in s.value for s in at.success)
        assert int(metric(at, "Number of ratings").replace(",", "")) == int(count_before.replace(",", "")) + 1
        assert metric(at, "Average rating") != avg_before
        assert metric(at, "Your rating") == "5.0 ★"
    finally:
        with superuser() as conn:
            conn.execute("DELETE FROM ratings WHERE user_id = %s AND movie_id = %s", (USER["user_id"], small_movie))
            after = conn.execute("SELECT rating_count, rating_sum FROM movie_stats WHERE movie_id = %s",
                                 (small_movie,)).fetchone()
        assert after == before


# ----------------------------------------------------------------- admin safety rules
def test_admin_cannot_delete_or_demote_self(admin_user):
    with pytest.raises(ops.AdminError, match="own account"):
        ops.delete_account(admin_user["user_id"], admin_user["user_id"])
    with pytest.raises(ops.AdminError, match="own account"):
        ops.set_role(admin_user["user_id"], "user", admin_user["user_id"])


def test_deleting_a_user_with_ratings_is_blocked(admin_user):
    with superuser() as conn:
        n = conn.execute("SELECT count(*) FROM ratings WHERE user_id = 1").fetchone()[0]
    with pytest.raises(ops.HasActivity) as exc:
        ops.delete_account(1, admin_user["user_id"])
    assert exc.value.ratings == n and "Delete them first?" in str(exc.value)
    with superuser() as conn:                     # nothing was deleted
        assert conn.execute("SELECT count(*) FROM ratings WHERE user_id = 1").fetchone()[0] == n
        assert conn.execute("SELECT username FROM users WHERE user_id = 1").fetchone()[0] == "demo_user1"


def test_deleting_a_movie_with_ratings_is_refused():
    with pytest.raises(ops.AdminError, match="ratings or tags"):
        ops.delete_movie(1)
    with superuser() as conn:
        assert conn.execute("SELECT count(*) FROM movies WHERE movie_id = 1").fetchone()[0] == 1


@pytest.mark.parametrize("call, message", [
    (lambda: ops.create_account("newbie", "short", "user"), "at least 8"),
    (lambda: ops.create_account("ab", "long-enough-1", "user"), "at least 3"),
    (lambda: ops.create_account("newbie", "long-enough-1", "root"), "role"),
    (lambda: ops.add_movie("   ", 2000, []), "empty"),
    (lambda: ops.add_movie("Some Movie", 1700, []), "between 1870 and 2030"),
])
def test_admin_input_validation(call, message):
    with pytest.raises(ops.AdminError, match=message):
        call()


def test_add_then_delete_movie_uses_identity():
    with superuser() as conn:
        top = conn.execute("SELECT max(movie_id) FROM movies").fetchone()[0]
        genre = conn.execute("SELECT genre_id FROM genres WHERE name = 'Drama'").fetchone()[0]
    movie_id = ops.add_movie("Test Movie, The", 2026, [genre])
    try:
        assert movie_id > top
        detail = ops.movie_detail(movie_id)
        assert detail["title"] == "Test Movie, The" and detail["genre_ids"] == [genre]
    finally:
        ops.delete_movie(movie_id)                # no ratings/tags: genres cascade
    assert ops.movie_detail(movie_id) is None


def test_create_login_and_delete_account(admin_user):
    from auth import login
    user_id = ops.create_account("phase7_test", "a-long-password", "user")
    try:
        assert login("phase7_test", "a-long-password")["user_id"] == user_id   # hashed by pgcrypto
        assert login("phase7_test", "wrong-password") is None
    finally:
        ops.delete_account(user_id, admin_user["user_id"])
    assert login("phase7_test", "a-long-password") is None
