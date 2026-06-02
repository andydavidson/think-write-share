import re
from words import generate_slug, _ADJECTIVES, _NOUNS


def test_default_slug_has_four_parts():
    assert len(generate_slug().split("-")) == 4


def test_custom_word_count():
    for count in (2, 3, 5):
        assert len(generate_slug(word_count=count).split("-")) == count


def test_slug_is_lowercase():
    for _ in range(20):
        slug = generate_slug()
        assert slug == slug.lower()


def test_slug_chars_are_valid():
    for _ in range(30):
        slug = generate_slug()
        assert re.fullmatch(r"[a-z][a-z\-]*[a-z]", slug), f"Bad slug: {slug}"


def test_slug_words_come_from_word_lists():
    pool = set(_ADJECTIVES + _NOUNS)
    for _ in range(20):
        for word in generate_slug().split("-"):
            assert word in pool, f"'{word}' is not in the word lists"


def test_slugs_vary():
    # With hundreds of words in the pool, two random 4-word slugs should
    # almost never be identical.
    slugs = {generate_slug() for _ in range(15)}
    assert len(slugs) > 1


def test_no_duplicate_words_within_slug():
    # random.sample guarantees no repeats within a single slug
    for _ in range(30):
        words = generate_slug().split("-")
        assert len(words) == len(set(words))
