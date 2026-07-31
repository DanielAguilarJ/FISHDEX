"""
Species lookup.

Species resolution sits on the identification critical path: the candidate gallery
is partitioned by species, so resolving to the wrong one compares a fish against a
different species' embeddings and can only ever produce a wrong answer.

The substring fallback used to return the *first* species containing the query,
which silently mis-resolved the most natural human queries:

  "perch" -> Pike-perch (Zander), not European perch   <- different fish
  "carp"  -> Common carp, out of 6 candidates
  "a"     -> Common carp, out of 42 candidates

It now requires a query of at least MIN_FUZZY_QUERY_LENGTH characters *and* a
single unambiguous match. That also protects
``scripts/export_classifier_onnx.py``, which maps trained class labels through
this function and would otherwise bake a wrong species into the exported label map.
"""

from __future__ import annotations

import pytest

from app.data.czech_species import (
    CZECH_SPECIES,
    MIN_FUZZY_QUERY_LENGTH,
    find_species_by_name,
    get_all_species,
    get_all_species_names,
)


# ─────────────────────────────────────────────────────────────────────────────
# Catalog integrity
# ─────────────────────────────────────────────────────────────────────────────
def test_catalog_is_not_empty() -> None:
    assert len(CZECH_SPECIES) > 0


def test_every_entry_has_the_required_fields() -> None:
    for species in CZECH_SPECIES:
        for field in ("czech_name", "english_name", "latin_name", "slug", "rarity"):
            assert species.get(field), f"{species.get('slug')} is missing {field}"


def test_slugs_are_unique() -> None:
    """A duplicate slug would make gallery partitioning ambiguous."""
    slugs = [s["slug"] for s in CZECH_SPECIES]

    assert len(slugs) == len(set(slugs))


def test_slugs_are_lowercase_snake_case() -> None:
    for species in CZECH_SPECIES:
        slug = species["slug"]
        assert slug == slug.lower(), slug
        assert " " not in slug, slug
        assert "-" not in slug, slug


def test_english_names_are_unique() -> None:
    names = [s["english_name"] for s in CZECH_SPECIES]

    assert len(names) == len(set(names))


def test_latin_names_are_unique() -> None:
    names = [s["latin_name"] for s in CZECH_SPECIES]

    assert len(names) == len(set(names))


# ─────────────────────────────────────────────────────────────────────────────
# Exact matching
# ─────────────────────────────────────────────────────────────────────────────
def test_every_species_is_findable_by_its_own_slug() -> None:
    """The identification pipeline resolves stored slugs; all must round-trip."""
    for species in CZECH_SPECIES:
        found = find_species_by_name(species["slug"])
        assert found is not None, species["slug"]
        assert found["slug"] == species["slug"]


def test_every_species_is_findable_by_each_of_its_names() -> None:
    for species in CZECH_SPECIES:
        for field in ("czech_name", "english_name", "latin_name"):
            found = find_species_by_name(species[field])
            assert found is not None, f"{species['slug']} via {field}"
            assert found["slug"] == species["slug"], f"{species['slug']} via {field}"


def test_matching_is_case_insensitive() -> None:
    assert find_species_by_name("CYPRINUS_CARPIO")["slug"] == "cyprinus_carpio"
    assert find_species_by_name("Common Carp")["slug"] == "cyprinus_carpio"
    assert find_species_by_name("cYpRiNuS cArPiO")["slug"] == "cyprinus_carpio"


def test_spaces_and_underscores_are_interchangeable() -> None:
    """The client may send either form; the stored slug uses underscores."""
    assert find_species_by_name("cyprinus carpio")["slug"] == "cyprinus_carpio"
    assert find_species_by_name("cyprinus_carpio")["slug"] == "cyprinus_carpio"


def test_hyphens_are_normalised_to_underscores() -> None:
    assert find_species_by_name("cyprinus-carpio")["slug"] == "cyprinus_carpio"


def test_surrounding_whitespace_is_ignored() -> None:
    assert find_species_by_name("  cyprinus_carpio  ")["slug"] == "cyprinus_carpio"


def test_titlecased_slug_resolves() -> None:
    """
    identify.get_area_species turns a stored slug into
    slug.replace('_', ' ').title() before looking it up.
    """
    assert find_species_by_name("Cyprinus Carpio")["slug"] == "cyprinus_carpio"


# ─────────────────────────────────────────────────────────────────────────────
# Ambiguity — the actual defect
# ─────────────────────────────────────────────────────────────────────────────
def test_perch_no_longer_silently_resolves_to_zander() -> None:
    """
    'perch' matches European perch, Pike-perch (Zander) and Volga pike-perch.
    Zander came first in the catalog and was returned — a different fish.
    """
    assert find_species_by_name("perch") is None


def test_european_perch_still_resolves_by_its_full_name() -> None:
    """Refusing the ambiguous query must not break the unambiguous one."""
    assert find_species_by_name("European perch")["slug"] == "perca_fluviatilis"
    assert find_species_by_name("perca_fluviatilis")["slug"] == "perca_fluviatilis"


@pytest.mark.parametrize("ambiguous", ["carp", "trout", "bream", "pike", "perch"])
def test_ambiguous_common_names_are_refused(ambiguous: str) -> None:
    """
    Each of these matches several species. Returning one of them arbitrarily is
    worse than returning nothing, because the caller cannot tell it happened.
    """
    candidates = [
        s
        for s in CZECH_SPECIES
        if ambiguous in s["czech_name"].lower()
        or ambiguous in s["english_name"].lower()
        or ambiguous in s["latin_name"].lower()
    ]
    assert len(candidates) > 1, f"{ambiguous} is no longer ambiguous; update the test"
    assert find_species_by_name(ambiguous) is None


def test_ambiguous_query_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """An ambiguous query is a caller bug and must be visible."""
    import logging

    with caplog.at_level(logging.WARNING, logger="app.data.czech_species"):
        find_species_by_name("carp")

    assert any("Ambiguous species query" in r.message for r in caplog.records)


@pytest.mark.parametrize("short", ["a", "e", "ca", "car"])
def test_queries_below_the_minimum_length_are_refused(short: str) -> None:
    """A single letter matched 42 of 45 species and returned the first."""
    assert len(short) < MIN_FUZZY_QUERY_LENGTH
    assert find_species_by_name(short) is None


def test_a_short_query_that_matches_exactly_is_still_accepted() -> None:
    """
    The length floor applies only to the substring pass. An exact name shorter
    than the floor must still resolve.
    """
    short_named = [s for s in CZECH_SPECIES if len(s["english_name"]) < MIN_FUZZY_QUERY_LENGTH]
    for species in short_named:
        assert find_species_by_name(species["english_name"]) is not None


def test_unambiguous_substring_still_resolves() -> None:
    """
    The useful case is preserved: a genus name matching one species resolves.
    'cyprinus' appears only in Cyprinus carpio.
    """
    assert find_species_by_name("cyprinus")["slug"] == "cyprinus_carpio"


# ─────────────────────────────────────────────────────────────────────────────
# Rejections
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("empty", ["", "   ", "\t", "\n"])
def test_blank_queries_are_refused(empty: str) -> None:
    assert find_species_by_name(empty) is None


def test_none_is_refused() -> None:
    assert find_species_by_name(None) is None  # type: ignore[arg-type]


def test_unknown_species_is_refused() -> None:
    assert find_species_by_name("loch_ness_monster") is None


def test_a_typo_does_not_resolve() -> None:
    """
    A near-miss must fail loudly. 'cyprinus_carpi' is not a substring of
    'cyprinus carpio' (underscore vs space), and must not fuzzy-match.
    """
    assert find_species_by_name("cyprinus_carpi") is None


# ─────────────────────────────────────────────────────────────────────────────
# Catalog accessors
# ─────────────────────────────────────────────────────────────────────────────
def test_get_all_species_returns_the_whole_catalog() -> None:
    assert len(get_all_species()) == len(CZECH_SPECIES)


def test_get_all_species_returns_a_copy() -> None:
    """
    The catalog is module-level state that the substring matcher and the upload
    validator both depend on. A caller must not be able to reorder or truncate it.
    """
    catalog = get_all_species()
    original_length = len(CZECH_SPECIES)

    catalog.clear()

    assert len(CZECH_SPECIES) == original_length


def test_get_all_species_names_is_sorted_and_complete() -> None:
    names = get_all_species_names()

    assert names == sorted(names)
    assert len(names) == len(CZECH_SPECIES)


def test_every_name_from_the_accessor_resolves_back() -> None:
    """Round-trip: whatever the dropdown offers, the server must accept."""
    for name in get_all_species_names():
        assert find_species_by_name(name) is not None, name
