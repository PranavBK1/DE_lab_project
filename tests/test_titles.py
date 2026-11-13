"""GAP 7: display_title() and the article-aware search patterns (no database)."""
import pytest

from queries import display_title, search_patterns, stored_form


@pytest.mark.parametrize("stored, shown", [
    ("Matrix, The", "The Matrix"),
    ("Godfather, The", "The Godfather"),
    ("Usual Suspects, The", "The Usual Suspects"),
    ("Good, the Bad and the Ugly, The", "The Good, the Bad and the Ugly"),
    ("Hungarian Fairy Tale, A (Hol volt, hol nem volt)", "A Hungarian Fairy Tale (Hol volt, hol nem volt)"),
    ("Postman, The (Postino, Il)", "The Postman (Postino, Il)"),
    ("City of Lost Children, The (Cité des enfants perdus, La)",
     "The City of Lost Children (Cité des enfants perdus, La)"),
    ("Mariachi, El", "El Mariachi"),
    ("Misérables, Les", "Les Misérables"),
    ("Enfer, L'", "L'Enfer"),
    ("Boot, Das (Boat, The)", "Das Boot (Boat, The)"),
    ("Cercle Rouge, Le (Red Circle, The)", "Le Cercle Rouge (Red Circle, The)"),
    ("American Tail, An", "An American Tail"),
    # unchanged
    ("Toy Story", "Toy Story"),
    ("Amelie (Fabuleux destin d'Amélie Poulain, Le)", "Amelie (Fabuleux destin d'Amélie Poulain, Le)"),
    ("Die, Mommie, Die", "Die, Mommie, Die"),
    ("Star Wars: Episode IV - A New Hope", "Star Wars: Episode IV - A New Hope"),
    ("", ""),
])
def test_display_title(stored, shown):
    assert display_title(stored) == shown


@pytest.mark.parametrize("query, stored", [
    ("the matrix", "matrix, the"),
    ("The  Matrix ", "matrix, the"),
    ("a beautiful mind", "beautiful mind, a"),
    ("an american tail", "american tail, an"),
    ("el mariachi", "mariachi, el"),
    ("l'enfer", "enfer, l'"),
    ("matrix", None),
    ("theory of everything", None),      # "the" must be a whole word
])
def test_stored_form(query, stored):
    assert stored_form(query) == stored


def test_search_patterns_try_both_forms():
    p = search_patterns("The Matrix")
    assert p == {"prefix": "the matrix%", "alt_prefix": "matrix, the%",
                 "contains": "%the matrix%", "alt_contains": "%matrix, the%"}


def test_search_patterns_escape_wildcards():
    assert search_patterns("100%_")["prefix"] == "100\\%\\_%"
