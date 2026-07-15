/// Catálogo estático de las 45 especies de peces de República Checa.
/// Fuente: czech_species.py del servidor AI.
/// Se usa para poblar la colección completa (descubiertos + no descubiertos).
class CzechSpecies {
  final String slug;
  final String czechName;
  final String englishName;
  final String latinName;
  final String rarity;
  final int xpBase;

  const CzechSpecies({
    required this.slug,
    required this.czechName,
    required this.englishName,
    required this.latinName,
    required this.rarity,
    required this.xpBase,
  });
}

/// Las 45 especies de peces registradas en la República Checa.
const List<CzechSpecies> czechFishCatalog = [
  CzechSpecies(
    slug: 'cyprinus_carpio',
    czechName: 'Kapr obecný',
    englishName: 'Common carp',
    latinName: 'Cyprinus carpio',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'carassius_carassius',
    czechName: 'Karas obecný',
    englishName: 'Crucian carp',
    latinName: 'Carassius carassius',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'carassius_gibelio',
    czechName: 'Karas stříbřitý',
    englishName: 'Prussian carp',
    latinName: 'Carassius gibelio',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'ctenopharyngodon_idella',
    czechName: 'Amur bílý',
    englishName: 'Grass carp',
    latinName: 'Ctenopharyngodon idella',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'hypophthalmichthys_molitrix',
    czechName: 'Tolstolobik bílý',
    englishName: 'Silver carp',
    latinName: 'Hypophthalmichthys molitrix',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'hypophthalmichthys_nobilis',
    czechName: 'Tolstolobik pestrý',
    englishName: 'Bighead carp',
    latinName: 'Hypophthalmichthys nobilis',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'rutilus_rutilus',
    czechName: 'Plotice obecná',
    englishName: 'Common roach',
    latinName: 'Rutilus rutilus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'scardinius_erythrophthalmus',
    czechName: 'Perlín ostrobřichý',
    englishName: 'Common rudd',
    latinName: 'Scardinius erythrophthalmus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'abramis_brama',
    czechName: 'Cejn velký',
    englishName: 'Common bream',
    latinName: 'Abramis brama',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'blicca_bjoerkna',
    czechName: 'Cejnek malý',
    englishName: 'White bream',
    latinName: 'Blicca bjoerkna',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'vimba_vimba',
    czechName: 'Podoustev říční',
    englishName: 'Vimba bream',
    latinName: 'Vimba vimba',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'barbus_barbus',
    czechName: 'Parma obecná',
    englishName: 'Common barbel',
    latinName: 'Barbus barbus',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'chondrostoma_nasus',
    czechName: 'Ostroretka stěhovavá',
    englishName: 'Nase',
    latinName: 'Chondrostoma nasus',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'squalius_cephalus',
    czechName: 'Jelec tloušť',
    englishName: 'Common chub',
    latinName: 'Squalius cephalus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'leuciscus_leuciscus',
    czechName: 'Jelec proudník',
    englishName: 'Common dace',
    latinName: 'Leuciscus leuciscus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'leuciscus_idus',
    czechName: 'Jelec jesen',
    englishName: 'Ide',
    latinName: 'Leuciscus idus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'leuciscus_aspius',
    czechName: 'Bolen dravý',
    englishName: 'Asp',
    latinName: 'Leuciscus aspius (Aspius aspius)',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'alburnus_alburnus',
    czechName: 'Ouklej obecná',
    englishName: 'Bleak',
    latinName: 'Alburnus alburnus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'rhodeus_amarus',
    czechName: 'Hořavka duhová',
    englishName: 'European bitterling',
    latinName: 'Rhodeus amarus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'phoxinus_phoxinus',
    czechName: 'Střevle potoční',
    englishName: 'Eurasian minnow',
    latinName: 'Phoxinus phoxinus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'salmo_trutta',
    czechName: 'Pstruh obecný',
    englishName: 'Brown trout',
    latinName: 'Salmo trutta',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'oncorhynchus_mykiss',
    czechName: 'Pstruh duhový',
    englishName: 'Rainbow trout',
    latinName: 'Oncorhynchus mykiss',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'salvelinus_fontinalis',
    czechName: 'Siven americký',
    englishName: 'Brook trout',
    latinName: 'Salvelinus fontinalis',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'thymallus_thymallus',
    czechName: 'Lipan podhorní',
    englishName: 'European grayling',
    latinName: 'Thymallus thymallus',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'hucho_hucho',
    czechName: 'Hlavatka obecná',
    englishName: 'Huchen (Danube salmon)',
    latinName: 'Hucho hucho',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'salmo_salar',
    czechName: 'Losos obecný',
    englishName: 'Atlantic salmon',
    latinName: 'Salmo salar',
    rarity: 'legendary',
    xpBase: 100,
  ),
  CzechSpecies(
    slug: 'coregonus_maraena',
    czechName: 'Síh maréna',
    englishName: 'Maraena whitefish',
    latinName: 'Coregonus maraena',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'coregonus_peled',
    czechName: 'Síh peleď',
    englishName: 'Peled',
    latinName: 'Coregonus peled',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'esox_lucius',
    czechName: 'Štika obecná',
    englishName: 'Northern pike',
    latinName: 'Esox lucius',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'sander_lucioperca',
    czechName: 'Candát obecný',
    englishName: 'Pike-perch (Zander)',
    latinName: 'Sander lucioperca',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'sander_volgensis',
    czechName: 'Candát východní',
    englishName: 'Volga pike-perch',
    latinName: 'Sander volgensis',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'perca_fluviatilis',
    czechName: 'Okoun říční',
    englishName: 'European perch',
    latinName: 'Perca fluviatilis',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'gymnocephalus_cernua',
    czechName: 'Ježdík obecný',
    englishName: 'Ruffe',
    latinName: 'Gymnocephalus cernua',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'silurus_glanis',
    czechName: 'Sumec velký',
    englishName: 'Wels catfish',
    latinName: 'Silurus glanis',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'ameiurus_nebulosus',
    czechName: 'Sumeček americký',
    englishName: 'Brown bullhead',
    latinName: 'Ameiurus nebulosus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'ameiurus_melas',
    czechName: 'Sumeček černý',
    englishName: 'Black bullhead',
    latinName: 'Ameiurus melas',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'lepomis_gibbosus',
    czechName: 'Slunečnice pestrá',
    englishName: 'Pumpkinseed',
    latinName: 'Lepomis gibbosus',
    rarity: 'common',
    xpBase: 10,
  ),
  CzechSpecies(
    slug: 'micropterus_salmoides',
    czechName: 'Okounek pstruhový',
    englishName: 'Largemouth bass',
    latinName: 'Micropterus salmoides',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'anguilla_anguilla',
    czechName: 'Úhoř říční',
    englishName: 'European eel',
    latinName: 'Anguilla anguilla',
    rarity: 'rare',
    xpBase: 50,
  ),
  CzechSpecies(
    slug: 'acipenser_ruthenus',
    czechName: 'Jeseter malý',
    englishName: 'Sterlet',
    latinName: 'Acipenser ruthenus',
    rarity: 'legendary',
    xpBase: 100,
  ),
  CzechSpecies(
    slug: 'acipenser_baerii',
    czechName: 'Jeseter sibiřský',
    englishName: 'Siberian sturgeon',
    latinName: 'Acipenser baerii',
    rarity: 'legendary',
    xpBase: 100,
  ),
  CzechSpecies(
    slug: 'neogobius_melanostomus',
    czechName: 'Hlaváč černoústý',
    englishName: 'Round goby',
    latinName: 'Neogobius melanostomus',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'proterorhinus_semilunaris',
    czechName: 'Hlaváček mramorovaný',
    englishName: 'Western tubenose goby',
    latinName: 'Proterorhinus semilunaris',
    rarity: 'uncommon',
    xpBase: 25,
  ),
  CzechSpecies(
    slug: 'ponticola_kessleri',
    czechName: 'Hlaváč Kesslerův',
    englishName: "Kessler's goby",
    latinName: 'Ponticola kessleri',
    rarity: 'legendary',
    xpBase: 100,
  ),
  CzechSpecies(
    slug: 'tinca_tinca',
    czechName: 'Lín obecný',
    englishName: 'Tench',
    latinName: 'Tinca tinca',
    rarity: 'common',
    xpBase: 10,
  ),
];

/// Busca una especie del catálogo por nombre inglés (case-insensitive).
CzechSpecies? findCzechSpeciesByEnglishName(String name) {
  final lower = name.toLowerCase().trim();
  for (final sp in czechFishCatalog) {
    if (sp.englishName.toLowerCase() == lower) return sp;
  }
  // Partial match fallback
  for (final sp in czechFishCatalog) {
    if (sp.englishName.toLowerCase().contains(lower) ||
        lower.contains(sp.englishName.toLowerCase())) return sp;
  }
  return null;
}

/// Busca una especie del catálogo por cualquier nombre (checo, inglés, latín).
CzechSpecies? findCzechSpeciesByAnyName(String name) {
  final lower = name.toLowerCase().trim();
  for (final sp in czechFishCatalog) {
    if (sp.englishName.toLowerCase() == lower ||
        sp.czechName.toLowerCase() == lower ||
        sp.latinName.toLowerCase() == lower) {
      return sp;
    }
  }
  // Partial match
  for (final sp in czechFishCatalog) {
    if (sp.englishName.toLowerCase().contains(lower) ||
        sp.czechName.toLowerCase().contains(lower) ||
        lower.contains(sp.englishName.toLowerCase())) {
      return sp;
    }
  }
  return null;
}

/// Devuelve el nombre de la especie localizado.
/// Si es checo ('cs'), usa czechName. En cualquier otro caso, englishName.
String getLocalizedSpeciesName(String species, String languageCode) {
  final matched = findCzechSpeciesByAnyName(species);
  if (matched == null) return species;
  if (languageCode == 'cs') {
    return matched.czechName;
  } else {
    return matched.englishName;
  }
}
