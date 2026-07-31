"""
FishDex AI Server - Czech Fish Species Database
=================================================
All 45 fish species found in Czech Republic fishing areas.
Each species has Czech, English, and Latin names plus rarity classification.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum query length before substring matching is attempted at all. Below this
# almost every query is ambiguous: a single letter matches 42 of the 45 species.
MIN_FUZZY_QUERY_LENGTH = 4


# =============================================================================
# SPECIES DATABASE
# =============================================================================

CZECH_SPECIES: list[dict] = [
    {
        "czech_name": "Kapr obecný",
        "english_name": "Common carp",
        "latin_name": "Cyprinus carpio",
        "slug": "cyprinus_carpio",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Karas obecný",
        "english_name": "Crucian carp",
        "latin_name": "Carassius carassius",
        "slug": "carassius_carassius",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Karas stříbřitý",
        "english_name": "Prussian carp",
        "latin_name": "Carassius gibelio",
        "slug": "carassius_gibelio",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Amur bílý",
        "english_name": "Grass carp",
        "latin_name": "Ctenopharyngodon idella",
        "slug": "ctenopharyngodon_idella",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Tolstolobik bílý",
        "english_name": "Silver carp",
        "latin_name": "Hypophthalmichthys molitrix",
        "slug": "hypophthalmichthys_molitrix",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Tolstolobik pestrý",
        "english_name": "Bighead carp",
        "latin_name": "Hypophthalmichthys nobilis",
        "slug": "hypophthalmichthys_nobilis",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Plotice obecná",
        "english_name": "Common roach",
        "latin_name": "Rutilus rutilus",
        "slug": "rutilus_rutilus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Perlín ostrobřichý",
        "english_name": "Common rudd",
        "latin_name": "Scardinius erythrophthalmus",
        "slug": "scardinius_erythrophthalmus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Cejn velký",
        "english_name": "Common bream",
        "latin_name": "Abramis brama",
        "slug": "abramis_brama",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Cejnek malý",
        "english_name": "White bream",
        "latin_name": "Blicca bjoerkna",
        "slug": "blicca_bjoerkna",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Podoustev říční",
        "english_name": "Vimba bream",
        "latin_name": "Vimba vimba",
        "slug": "vimba_vimba",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Parma obecná",
        "english_name": "Common barbel",
        "latin_name": "Barbus barbus",
        "slug": "barbus_barbus",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Ostroretka stěhovavá",
        "english_name": "Nase",
        "latin_name": "Chondrostoma nasus",
        "slug": "chondrostoma_nasus",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Jelec tloušť",
        "english_name": "Common chub",
        "latin_name": "Squalius cephalus",
        "slug": "squalius_cephalus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Jelec proudník",
        "english_name": "Common dace",
        "latin_name": "Leuciscus leuciscus",
        "slug": "leuciscus_leuciscus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Jelec jesen",
        "english_name": "Ide",
        "latin_name": "Leuciscus idus",
        "slug": "leuciscus_idus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Bolen dravý",
        "english_name": "Asp",
        "latin_name": "Leuciscus aspius (Aspius aspius)",
        "slug": "leuciscus_aspius",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Ouklej obecná",
        "english_name": "Bleak",
        "latin_name": "Alburnus alburnus",
        "slug": "alburnus_alburnus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Hořavka duhová",
        "english_name": "European bitterling",
        "latin_name": "Rhodeus amarus",
        "slug": "rhodeus_amarus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Střevle potoční",
        "english_name": "Eurasian minnow",
        "latin_name": "Phoxinus phoxinus",
        "slug": "phoxinus_phoxinus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Pstruh obecný",
        "english_name": "Brown trout",
        "latin_name": "Salmo trutta",
        "slug": "salmo_trutta",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Pstruh duhový",
        "english_name": "Rainbow trout",
        "latin_name": "Oncorhynchus mykiss",
        "slug": "oncorhynchus_mykiss",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Siven americký",
        "english_name": "Brook trout",
        "latin_name": "Salvelinus fontinalis",
        "slug": "salvelinus_fontinalis",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Lipan podhorní",
        "english_name": "European grayling",
        "latin_name": "Thymallus thymallus",
        "slug": "thymallus_thymallus",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Hlavatka obecná",
        "english_name": "Huchen (Danube salmon)",
        "latin_name": "Hucho hucho",
        "slug": "hucho_hucho",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Losos obecný",
        "english_name": "Atlantic salmon",
        "latin_name": "Salmo salar",
        "slug": "salmo_salar",
        "rarity": "legendary",
        "xp_base": 100,
    },
    {
        "czech_name": "Síh maréna",
        "english_name": "Maraena whitefish",
        "latin_name": "Coregonus maraena",
        "slug": "coregonus_maraena",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Síh peleď",
        "english_name": "Peled",
        "latin_name": "Coregonus peled",
        "slug": "coregonus_peled",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Štika obecná",
        "english_name": "Northern pike",
        "latin_name": "Esox lucius",
        "slug": "esox_lucius",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Candát obecný",
        "english_name": "Pike-perch (Zander)",
        "latin_name": "Sander lucioperca",
        "slug": "sander_lucioperca",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Candát východní",
        "english_name": "Volga pike-perch",
        "latin_name": "Sander volgensis",
        "slug": "sander_volgensis",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Okoun říční",
        "english_name": "European perch",
        "latin_name": "Perca fluviatilis",
        "slug": "perca_fluviatilis",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Ježdík obecný",
        "english_name": "Ruffe",
        "latin_name": "Gymnocephalus cernua",
        "slug": "gymnocephalus_cernua",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Sumec velký",
        "english_name": "Wels catfish",
        "latin_name": "Silurus glanis",
        "slug": "silurus_glanis",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Sumeček americký",
        "english_name": "Brown bullhead",
        "latin_name": "Ameiurus nebulosus",
        "slug": "ameiurus_nebulosus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Sumeček černý",
        "english_name": "Black bullhead",
        "latin_name": "Ameiurus melas",
        "slug": "ameiurus_melas",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Slunečnice pestrá",
        "english_name": "Pumpkinseed",
        "latin_name": "Lepomis gibbosus",
        "slug": "lepomis_gibbosus",
        "rarity": "common",
        "xp_base": 10,
    },
    {
        "czech_name": "Okounek pstruhový",
        "english_name": "Largemouth bass",
        "latin_name": "Micropterus salmoides",
        "slug": "micropterus_salmoides",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Úhoř říční",
        "english_name": "European eel",
        "latin_name": "Anguilla anguilla",
        "slug": "anguilla_anguilla",
        "rarity": "rare",
        "xp_base": 50,
    },
    {
        "czech_name": "Jeseter malý",
        "english_name": "Sterlet",
        "latin_name": "Acipenser ruthenus",
        "slug": "acipenser_ruthenus",
        "rarity": "legendary",
        "xp_base": 100,
    },
    {
        "czech_name": "Jeseter sibiřský",
        "english_name": "Siberian sturgeon",
        "latin_name": "Acipenser baerii",
        "slug": "acipenser_baerii",
        "rarity": "legendary",
        "xp_base": 100,
    },
    {
        "czech_name": "Hlaváč černoústý",
        "english_name": "Round goby",
        "latin_name": "Neogobius melanostomus",
        "slug": "neogobius_melanostomus",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Hlaváček mramorovaný",
        "english_name": "Western tubenose goby",
        "latin_name": "Proterorhinus semilunaris",
        "slug": "proterorhinus_semilunaris",
        "rarity": "uncommon",
        "xp_base": 25,
    },
    {
        "czech_name": "Hlaváč Kesslerův",
        "english_name": "Kessler's goby",
        "latin_name": "Ponticola kessleri",
        "slug": "ponticola_kessleri",
        "rarity": "legendary",
        "xp_base": 100,
    },
    {
        "czech_name": "Lín obecný",
        "english_name": "Tench",
        "latin_name": "Tinca tinca",
        "slug": "tinca_tinca",
        "rarity": "common",
        "xp_base": 10,
    },
]


# =============================================================================
# LOOKUP FUNCTIONS
# =============================================================================


def find_species_by_name(name: str) -> Optional[dict]:
    """
    Find a species by Czech, English or Latin name, or by slug (case-insensitive).

    Matching happens in two passes:

    1. **Exact**, after normalising case and treating spaces and underscores as
       equivalent. This is what the identification pipeline relies on.
    2. **Substring**, but only when the query is at least
       :data:`MIN_FUZZY_QUERY_LENGTH` characters *and* exactly one species matches.

    The second pass used to return the first species containing the query, which
    silently produced wrong answers on the most natural queries a human would try:

    * ``"perch"`` matched 3 species and returned *Pike-perch (Zander)*
      (``sander_lucioperca``) rather than *European perch*
      (``perca_fluviatilis``) — a different fish, purely because of catalog order.
    * ``"carp"`` matched 6 species and returned *Common carp*.
    * ``"a"`` matched 42 species and also returned *Common carp*.

    That mattered beyond search: ``scripts/export_classifier_onnx.py`` maps trained
    class labels through this function, so an ambiguous label would have baked a
    wrong species into the exported model's label map.

    Args:
        name: Species name or slug to look up.

    Returns:
        The species dict, or None when there is no match or the query is
        ambiguous.
    """
    if not name:
        return None

    name_lower = name.lower().strip()
    if not name_lower:
        return None
    name_slug = name_lower.replace(" ", "_").replace("-", "_")

    # ── Pass 1: exact ────────────────────────────────────────────────────────
    for species in CZECH_SPECIES:
        species_slug = species["slug"].lower()
        if (
            species["czech_name"].lower() == name_lower
            or species["english_name"].lower() == name_lower
            or species["latin_name"].lower() == name_lower
            or species_slug == name_lower
            or species_slug == name_slug
            or species_slug.replace("_", " ") == name_lower
        ):
            return species

    # ── Pass 2: substring, only when unambiguous ─────────────────────────────
    if len(name_lower) < MIN_FUZZY_QUERY_LENGTH:
        return None

    matches = [
        species
        for species in CZECH_SPECIES
        if name_lower in species["czech_name"].lower()
        or name_lower in species["english_name"].lower()
        or name_lower in species["latin_name"].lower()
    ]

    if len(matches) == 1:
        logger.debug(
            "Species %r resolved by substring to %s", name, matches[0]["slug"]
        )
        return matches[0]

    if matches:
        # Returning an arbitrary one of these is how "perch" became Zander.
        logger.warning(
            "Ambiguous species query %r matches %d species (%s); refusing to guess",
            name,
            len(matches),
            ", ".join(m["slug"] for m in matches[:5]),
        )
    return None


def get_all_species_names() -> list[str]:
    """
    Get all English species names for dropdown population.

    Returns:
        Sorted list of all English species names.
    """
    return sorted([s["english_name"] for s in CZECH_SPECIES])


def get_all_species() -> list[dict]:
    """
    Get the complete species database.

    Returns:
        A new list containing every species dict. The list is copied so a caller
        cannot append to, remove from or reorder the module-level catalog — the
        substring matcher and the job-upload validator both depend on its order
        and contents.
    """
    return list(CZECH_SPECIES)
