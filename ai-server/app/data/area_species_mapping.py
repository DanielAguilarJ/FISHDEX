"""
FishDex AI Server - Area-Species Mapping
==========================================
Maps which fish species are commonly found in which types of areas
based on area name classification (pond, reservoir, stream, river, lake).
"""


from app.data.czech_species import CZECH_SPECIES


# =============================================================================
# AREA TYPE CLASSIFICATION
# =============================================================================

# Keywords that indicate area type from Czech area names
_POND_KEYWORDS = ["RYBNÍK", "RYBNIK", "POND"]
_RESERVOIR_KEYWORDS = ["NÁDRŽ", "NADRZ", "VODNÍ DÍLO", "VODNI DILO", "PŘEHRADA", "PREHRADA", "VD "]
_STREAM_KEYWORDS = ["POTOK", "BROOK", "CREEK"]
_LAKE_KEYWORDS = ["JEZERO", "LAKE"]
_RIVER_NAMES = [
    "VLTAVA", "LABE", "BEROUNKA", "OHŘE", "OHRE", "MORAVA", "DYJE",
    "ODRA", "SÁZAVA", "SAZAVA", "OTAVA", "LUŽNICE", "LUZNICE",
    "SVRATKA", "JIHLAVA", "BEČVA", "BECVA", "JIZERA", "CIDLINA",
    "PLOUČNICE", "PLOUCNICE", "OPAVA", "OSTRAVICE", "ORLICE",
    "DOUBRAVA", "CHRUDIMKA", "DIVOKÁ ORLICE", "TICHÁ ORLICE",
    "NEŽÁRKA", "BLANICE", "ŽELIVKA", "ZELIVKA", "ROKYTNÁ",
    "OSLAVA", "TŘEBŮVKA", "MŽE", "ÚHLAVA", "RADBUZA", "ÚSLAVA",
]

# Species preferences by area type
_POND_SPECIES = [
    "cyprinus_carpio", "carassius_carassius", "carassius_gibelio",
    "tinca_tinca", "scardinius_erythrophthalmus", "rutilus_rutilus",
    "abramis_brama", "esox_lucius", "perca_fluviatilis",
    "ctenopharyngodon_idella", "hypophthalmichthys_molitrix",
    "hypophthalmichthys_nobilis", "sander_lucioperca",
    "silurus_glanis", "lepomis_gibbosus", "ameiurus_nebulosus",
]

_RESERVOIR_SPECIES = [
    "cyprinus_carpio", "esox_lucius", "sander_lucioperca",
    "perca_fluviatilis", "silurus_glanis", "abramis_brama",
    "rutilus_rutilus", "blicca_bjoerkna", "alburnus_alburnus",
    "coregonus_maraena", "coregonus_peled", "anguilla_anguilla",
    "tinca_tinca", "scardinius_erythrophthalmus",
    "acipenser_ruthenus", "acipenser_baerii",
]

_STREAM_SPECIES = [
    "salmo_trutta", "oncorhynchus_mykiss", "salvelinus_fontinalis",
    "thymallus_thymallus", "phoxinus_phoxinus", "squalius_cephalus",
    "leuciscus_leuciscus", "barbus_barbus", "chondrostoma_nasus",
    "rhodeus_amarus", "gymnocephalus_cernua",
]

_RIVER_SPECIES = [
    "cyprinus_carpio", "esox_lucius", "sander_lucioperca",
    "silurus_glanis", "barbus_barbus", "squalius_cephalus",
    "leuciscus_leuciscus", "leuciscus_idus", "leuciscus_aspius",
    "chondrostoma_nasus", "vimba_vimba", "abramis_brama",
    "rutilus_rutilus", "perca_fluviatilis", "alburnus_alburnus",
    "anguilla_anguilla", "salmo_trutta", "thymallus_thymallus",
    "neogobius_melanostomus", "proterorhinus_semilunaris",
    "ponticola_kessleri", "hucho_hucho",
]

_LAKE_SPECIES = [
    "cyprinus_carpio", "esox_lucius", "perca_fluviatilis",
    "rutilus_rutilus", "abramis_brama", "tinca_tinca",
    "scardinius_erythrophthalmus", "sander_lucioperca",
    "anguilla_anguilla", "coregonus_maraena",
]


def get_area_type(area_name: str) -> str:
    """
    Determine the type of fishing area from its name.

    Args:
        area_name: Name of the fishing area (Czech).

    Returns:
        One of: 'pond', 'reservoir', 'stream', 'river', 'lake'
    """
    name_upper = area_name.upper()

    # Check pond keywords
    for keyword in _POND_KEYWORDS:
        if keyword in name_upper:
            return "pond"

    # Check reservoir keywords
    for keyword in _RESERVOIR_KEYWORDS:
        if keyword in name_upper:
            return "reservoir"

    # Check stream keywords
    for keyword in _STREAM_KEYWORDS:
        if keyword in name_upper:
            return "stream"

    # Check lake keywords
    for keyword in _LAKE_KEYWORDS:
        if keyword in name_upper:
            return "lake"

    # Check if it's a known river
    for river in _RIVER_NAMES:
        if river in name_upper:
            return "river"

    # Default to river (most areas are river sections)
    return "river"


def get_likely_species_for_area(area_code: str) -> list[str]:
    """
    Get list of likely species English names for an area based on its type.

    Args:
        area_code: Czech fishing area code (e.g. '401 001')

    Returns:
        List of English species names likely found in this type of area.
    """
    try:
        from app.data.czech_areas import find_area_by_code
        area_info = find_area_by_code(area_code)
        if not area_info:
            # Return all species if area not found
            return [s["english_name"] for s in CZECH_SPECIES]
        area_name = area_info["name"]
    except ImportError:
        return [s["english_name"] for s in CZECH_SPECIES]

    area_type = get_area_type(area_name)

    # Get the species slugs for this area type
    slug_map = {
        "pond": _POND_SPECIES,
        "reservoir": _RESERVOIR_SPECIES,
        "stream": _STREAM_SPECIES,
        "river": _RIVER_SPECIES,
        "lake": _LAKE_SPECIES,
    }
    likely_slugs = slug_map.get(area_type, _RIVER_SPECIES)

    # Convert slugs to English names
    slug_to_name = {s["slug"]: s["english_name"] for s in CZECH_SPECIES}
    likely_names = [slug_to_name[slug] for slug in likely_slugs if slug in slug_to_name]

    return sorted(likely_names)


def get_likely_species_info_for_area(area_code: str) -> list[dict]:
    """
    Get full species info dicts for species likely found in an area.

    Args:
        area_code: Czech fishing area code

    Returns:
        List of species dicts with all fields.
    """
    try:
        from app.data.czech_areas import find_area_by_code
        area_info = find_area_by_code(area_code)
        if not area_info:
            return CZECH_SPECIES
        area_name = area_info["name"]
    except ImportError:
        return CZECH_SPECIES

    area_type = get_area_type(area_name)

    slug_map = {
        "pond": _POND_SPECIES,
        "reservoir": _RESERVOIR_SPECIES,
        "stream": _STREAM_SPECIES,
        "river": _RIVER_SPECIES,
        "lake": _LAKE_SPECIES,
    }
    likely_slugs = set(slug_map.get(area_type, _RIVER_SPECIES))

    return [s for s in CZECH_SPECIES if s["slug"] in likely_slugs]
