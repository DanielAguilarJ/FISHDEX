import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// Servicio de caché offline usando SharedPreferences
/// Permite almacenar datos del usuario, colección, spots y avistamientos pendientes
/// para funcionar sin conexión a internet
class CacheService {
  // =========================================================================
  // CLAVES DE CACHÉ
  // =========================================================================

  static const String _keyUserProfile = 'cache_user_profile';
  static const String _keyFishCollection = 'cache_fish_collection';
  static const String _keyFishingSpots = 'cache_fishing_spots';
  static const String _keyPendingSightings = 'cache_pending_sightings';

  // =========================================================================
  // MÉTODOS GENÉRICOS DE CACHÉ
  // =========================================================================

  /// Guarda datos en caché con una clave dada
  /// [key] - Clave única para identificar los datos
  /// [data] - Datos a almacenar (se convierte a JSON)
  Future<bool> saveToCache(String key, dynamic data) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(data);
      return await prefs.setString(key, jsonString);
    } catch (e) {
      // Error al guardar en caché - fallo silencioso
      return false;
    }
  }

  /// Recupera datos de caché por clave
  /// Retorna null si no existe o hay error
  Future<dynamic> getFromCache(String key) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(key);
      if (jsonString == null) return null;
      return jsonDecode(jsonString);
    } catch (e) {
      // Error al leer caché - retornar null
      return null;
    }
  }

  /// Limpia toda la caché de la aplicación
  Future<bool> clearCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_keyUserProfile);
      await prefs.remove(_keyFishCollection);
      await prefs.remove(_keyFishingSpots);
      await prefs.remove(_keyPendingSightings);
      return true;
    } catch (e) {
      return false;
    }
  }

  // =========================================================================
  // PERFIL DE USUARIO
  // =========================================================================

  /// Almacena el perfil del usuario en caché
  /// [profile] - Mapa con datos: name, level, xp, stats, etc.
  Future<bool> cacheUserProfile(Map<String, dynamic> profile) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(profile);
      return await prefs.setString(_keyUserProfile, jsonString);
    } catch (e) {
      return false;
    }
  }

  /// Recupera el perfil del usuario desde caché
  /// Retorna null si no hay datos almacenados
  Future<Map<String, dynamic>?> getCachedProfile() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyUserProfile);
      if (jsonString == null) return null;
      final decoded = jsonDecode(jsonString);
      return Map<String, dynamic>.from(decoded as Map);
    } catch (e) {
      return null;
    }
  }

  // =========================================================================
  // COLECCIÓN DE PECES
  // =========================================================================

  /// Almacena la colección completa de peces identificados
  /// [collection] - Lista de mapas con datos de cada pez
  Future<bool> cacheFishCollection(List<Map<String, dynamic>> collection) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(collection);
      return await prefs.setString(_keyFishCollection, jsonString);
    } catch (e) {
      return false;
    }
  }

  /// Recupera la colección de peces desde caché
  /// Retorna lista vacía si no hay datos
  Future<List<Map<String, dynamic>>> getCachedCollection() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyFishCollection);
      if (jsonString == null) return [];
      final decoded = jsonDecode(jsonString) as List;
      return decoded
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    } catch (e) {
      return [];
    }
  }

  // =========================================================================
  // SPOTS DE PESCA (PARA EL MAPA)
  // =========================================================================

  /// Almacena los spots de pesca para uso offline del mapa
  /// [spots] - Lista de mapas con datos de cada spot
  Future<bool> cacheFishingSpots(List<Map<String, dynamic>> spots) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = jsonEncode(spots);
      return await prefs.setString(_keyFishingSpots, jsonString);
    } catch (e) {
      return false;
    }
  }

  /// Recupera los spots de pesca desde caché
  /// Retorna lista vacía si no hay datos
  Future<List<Map<String, dynamic>>> getCachedFishingSpots() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyFishingSpots);
      if (jsonString == null) return [];
      final decoded = jsonDecode(jsonString) as List;
      return decoded
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    } catch (e) {
      return [];
    }
  }

  // =========================================================================
  // COLA DE AVISTAMIENTOS PENDIENTES
  // =========================================================================

  /// Agrega un avistamiento a la cola de pendientes (para subir cuando haya red)
  /// [sighting] - Mapa con datos del avistamiento (video, ubicación, timestamp)
  Future<bool> queueSighting(Map<String, dynamic> sighting) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyPendingSightings);
      final List<dynamic> currentQueue =
          jsonString != null ? jsonDecode(jsonString) as List : [];

      // Agregar timestamp si no tiene
      if (!sighting.containsKey('queued_at')) {
        sighting['queued_at'] = DateTime.now().toIso8601String();
      }

      currentQueue.add(sighting);
      final updatedJson = jsonEncode(currentQueue);
      return await prefs.setString(_keyPendingSightings, updatedJson);
    } catch (e) {
      return false;
    }
  }

  /// Recupera todos los avistamientos pendientes de subir
  /// Retorna lista vacía si no hay pendientes
  Future<List<Map<String, dynamic>>> getPendingSightings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyPendingSightings);
      if (jsonString == null) return [];
      final decoded = jsonDecode(jsonString) as List;
      return decoded
          .map((item) => Map<String, dynamic>.from(item as Map))
          .toList();
    } catch (e) {
      return [];
    }
  }

  /// Elimina un avistamiento pendiente de la cola (tras subirse exitosamente)
  /// [queuedAt] - Timestamp ISO del momento en que se encoló
  Future<bool> removePendingSighting(String queuedAt) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonString = prefs.getString(_keyPendingSightings);
      if (jsonString == null) return true;

      final List<dynamic> currentQueue = jsonDecode(jsonString) as List;
      currentQueue.removeWhere(
        (item) => (item as Map)['queued_at'] == queuedAt,
      );

      final updatedJson = jsonEncode(currentQueue);
      return await prefs.setString(_keyPendingSightings, updatedJson);
    } catch (e) {
      return false;
    }
  }

  /// Retorna el número de avistamientos pendientes en la cola
  Future<int> getPendingSightingsCount() async {
    final sightings = await getPendingSightings();
    return sightings.length;
  }
}
