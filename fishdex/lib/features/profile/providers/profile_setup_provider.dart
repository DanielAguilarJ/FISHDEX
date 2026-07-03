import 'dart:io';
import 'package:appwrite/appwrite.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:geocoding/geocoding.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/providers/appwrite_providers.dart';

// =============================================================================
// MODELO DE DATOS DEL PERFIL DE USUARIO
// =============================================================================

/// Datos del perfil del usuario cargados (para uso en toda la app)
class UserProfile {
  final String username;
  final String city;
  final String? avatarPath; // Path local del avatar
  final String? avatarUrl; // URL de Appwrite (si existe)
  final bool shareLocation;
  final double? latitude;
  final double? longitude;

  const UserProfile({
    this.username = '',
    this.city = '',
    this.avatarPath,
    this.avatarUrl,
    this.shareLocation = false,
    this.latitude,
    this.longitude,
  });

  bool get hasAvatar => avatarPath != null || avatarUrl != null;
  bool get hasUsername => username.isNotEmpty;
  bool get hasCity => city.isNotEmpty;
}

// =============================================================================
// PROVIDER QUE CARGA EL PERFIL GUARDADO (para toda la app)
// =============================================================================

/// Provider principal del perfil del usuario — se usa en profile_screen, etc.
final userProfileProvider = FutureProvider<UserProfile>((ref) async {
  final prefs = await SharedPreferences.getInstance();

  // Si está en modo demo, cargar SOLO de SharedPreferences (sin tocar Appwrite)
  final isDemoMode = prefs.getBool('is_demo_mode') ?? false;
  if (isDemoMode) {
    return UserProfile(
      username: prefs.getString('profile_username') ?? 'Demo User',
      city: prefs.getString('profile_city') ?? '',
      avatarPath: prefs.getString('profile_avatar_path'),
      shareLocation: false,
    );
  }

  // No demo: intentar cargar de Appwrite primero
  try {
    final account = ref.read(appwriteAccountProvider);
    final databases = ref.read(appwriteDatabasesProvider);
    final user = await account.get();

    final doc = await databases.getDocument(
      databaseId: AppConstants.databaseId,
      collectionId: AppConstants.usersCollection,
      documentId: user.$id,
    );

    final data = doc.data;
    return UserProfile(
      username: data['username'] ?? '',
      city: data['city'] ?? '',
      avatarUrl: (data['avatarUrl'] != null && data['avatarUrl'] != '')
          ? data['avatarUrl']
          : null,
      avatarPath: prefs.getString('profile_avatar_path'),
      shareLocation: data['shareLocation'] ?? false,
      latitude: prefs.getDouble('profile_latitude'),
      longitude: prefs.getDouble('profile_longitude'),
    );
  } catch (e) {
    // Fallback: cargar de SharedPreferences
    debugPrint('📋 Cargando perfil desde SharedPreferences: $e');
    return UserProfile(
      username: prefs.getString('profile_username') ?? '',
      city: prefs.getString('profile_city') ?? '',
      avatarPath: prefs.getString('profile_avatar_path'),
      shareLocation: prefs.getBool('profile_share_location') ?? false,
      latitude: prefs.getDouble('profile_latitude'),
      longitude: prefs.getDouble('profile_longitude'),
    );
  }
});

// =============================================================================
// ESTADO DEL FORMULARIO DE SETUP
// =============================================================================

/// Estado del formulario de setup de perfil
class ProfileSetupState {
  final String username;
  final File? avatarFile;
  final String? existingAvatarPath;
  final String city;
  final bool shareLocation;
  final bool permissionsGranted;
  final bool isLoading;
  final bool isDetectingLocation;
  final String? errorMessage;
  final double? latitude;
  final double? longitude;

  const ProfileSetupState({
    this.username = '',
    this.avatarFile,
    this.existingAvatarPath,
    this.city = '',
    this.shareLocation = false,
    this.permissionsGranted = false,
    this.isLoading = false,
    this.isDetectingLocation = false,
    this.errorMessage,
    this.latitude,
    this.longitude,
  });

  bool get hasAvatar => avatarFile != null || existingAvatarPath != null;

  ProfileSetupState copyWith({
    String? username,
    File? avatarFile,
    bool clearAvatar = false,
    String? existingAvatarPath,
    bool clearExistingAvatar = false,
    String? city,
    bool? shareLocation,
    bool? permissionsGranted,
    bool? isLoading,
    bool? isDetectingLocation,
    String? errorMessage,
    bool clearError = false,
    double? latitude,
    double? longitude,
  }) {
    return ProfileSetupState(
      username: username ?? this.username,
      avatarFile: clearAvatar ? null : (avatarFile ?? this.avatarFile),
      existingAvatarPath: clearExistingAvatar
          ? null
          : (existingAvatarPath ?? this.existingAvatarPath),
      city: city ?? this.city,
      shareLocation: shareLocation ?? this.shareLocation,
      permissionsGranted: permissionsGranted ?? this.permissionsGranted,
      isLoading: isLoading ?? this.isLoading,
      isDetectingLocation: isDetectingLocation ?? this.isDetectingLocation,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
    );
  }
}

// =============================================================================
// NOTIFIER DEL SETUP DE PERFIL
// =============================================================================

class ProfileSetupNotifier extends StateNotifier<ProfileSetupState> {
  final Ref _ref;

  ProfileSetupNotifier(this._ref) : super(const ProfileSetupState()) {
    _loadExistingData();
  }

  /// Carga datos existentes del perfil (si ya configuró antes)
  Future<void> _loadExistingData() async {
    final prefs = await SharedPreferences.getInstance();
    final existingUsername = prefs.getString('profile_username') ?? '';
    final existingCity = prefs.getString('profile_city') ?? '';
    final existingAvatarPath = prefs.getString('profile_avatar_path');
    final existingShareLocation =
        prefs.getBool('profile_share_location') ?? false;
    final existingLat = prefs.getDouble('profile_latitude');
    final existingLng = prefs.getDouble('profile_longitude');

    state = state.copyWith(
      username: existingUsername,
      existingAvatarPath: existingAvatarPath,
      city: existingCity,
      shareLocation: existingShareLocation,
      latitude: existingLat,
      longitude: existingLng,
    );
  }

  void setUsername(String value) {
    state = state.copyWith(username: value, clearError: true);
  }

  void setAvatar(File? file) {
    if (file != null) {
      state = state.copyWith(avatarFile: file);
    } else {
      state = state.copyWith(clearAvatar: true);
    }
  }

  void setCity(String value) {
    state = state.copyWith(city: value);
  }

  void setShareLocation(bool value) {
    state = state.copyWith(shareLocation: value);
  }

  void setPermissionsGranted(bool value) {
    state = state.copyWith(permissionsGranted: value);
  }

  /// Auto-detecta la ubicación del usuario usando GPS + reverse geocoding
  Future<void> autoDetectLocation() async {
    state = state.copyWith(isDetectingLocation: true, clearError: true);

    try {
      // Verificar permisos de ubicación
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          state = state.copyWith(
            isDetectingLocation: false,
            errorMessage: 'Permiso de ubicación denegado',
          );
          return;
        }
      }
      if (permission == LocationPermission.deniedForever) {
        state = state.copyWith(
          isDetectingLocation: false,
          errorMessage: 'Permiso de ubicación denegado permanentemente',
        );
        return;
      }

      // Verificar si el servicio de ubicación está habilitado
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) {
        state = state.copyWith(
          isDetectingLocation: false,
          errorMessage: 'Servicio de ubicación desactivado',
        );
        return;
      }

      // Obtener posición actual
      final position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.low,
      );

      // Reverse geocoding → obtener nombre de ciudad
      String cityName = '';
      try {
        final placemarks = await placemarkFromCoordinates(
          position.latitude,
          position.longitude,
        );
        if (placemarks.isNotEmpty) {
          final place = placemarks.first;
          // Construir nombre legible: Ciudad, Estado, País
          final parts = <String>[];
          if (place.locality != null && place.locality!.isNotEmpty) {
            parts.add(place.locality!);
          }
          if (place.administrativeArea != null &&
              place.administrativeArea!.isNotEmpty) {
            parts.add(place.administrativeArea!);
          }
          if (place.country != null && place.country!.isNotEmpty) {
            parts.add(place.country!);
          }
          cityName = parts.join(', ');
        }
      } catch (e) {
        debugPrint('⚠️ Reverse geocoding failed: $e');
        cityName = '${position.latitude.toStringAsFixed(2)}, ${position.longitude.toStringAsFixed(2)}';
      }

      state = state.copyWith(
        city: cityName,
        latitude: position.latitude,
        longitude: position.longitude,
        isDetectingLocation: false,
      );
    } catch (e) {
      debugPrint('⚠️ Error auto-detectando ubicación: $e');
      state = state.copyWith(
        isDetectingLocation: false,
        errorMessage: 'No se pudo detectar la ubicación',
      );
    }
  }

  /// Valida el username
  String? validateUsername(String? value) {
    if (value == null || value.trim().isEmpty) {
      return 'Ingresa un nombre de usuario';
    }
    if (value.trim().length < 3) {
      return 'Mínimo 3 caracteres';
    }
    if (value.contains(' ')) {
      return 'No se permiten espacios';
    }
    return null;
  }

  /// Guarda el perfil en Appwrite (o SharedPreferences como fallback)
  Future<bool> saveProfile() async {
    state = state.copyWith(isLoading: true, clearError: true);

    try {
      final prefs = await SharedPreferences.getInstance();
      final isDemoMode = prefs.getBool('is_demo_mode') ?? false;

      if (isDemoMode) {
        // Demo: guardar SOLO localmente, sin tocar Appwrite
        await _saveToPreferences();
        await _markSetupCompleted();
        state = state.copyWith(isLoading: false);
        _ref.invalidate(userProfileProvider);
        return true;
      }

      // Usuario real: intentar Appwrite + fallback local
      try {
        await _saveToAppwrite();
      } on AppwriteException catch (e) {
        debugPrint('⚠️ Appwrite error al guardar perfil: ${e.message}');
        // Continuar con guardado local como fallback
      } catch (e) {
        debugPrint('⚠️ Error al guardar perfil en Appwrite: $e');
        // Continuar con guardado local como fallback
      }

      await _saveToPreferences();
      await _markSetupCompleted();
      state = state.copyWith(isLoading: false);
      _ref.invalidate(userProfileProvider);
      return true;
    } catch (e) {
      debugPrint('⚠️ Error crítico al guardar perfil: $e');
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Error al guardar el perfil',
      );
      return false;
    }
  }

  /// Guarda el perfil en Appwrite Databases
  Future<void> _saveToAppwrite() async {
    final databases = _ref.read(appwriteDatabasesProvider);
    final account = _ref.read(appwriteAccountProvider);

    final user = await account.get();

    String? avatarUrl;
    if (state.avatarFile != null) {
      // Subir avatar a Appwrite Storage
      final storage = _ref.read(appwriteStorageProvider);
      final file = await storage.createFile(
        bucketId: AppConstants.userAvatarsBucket,
        fileId: ID.unique(),
        file: InputFile.fromPath(
          path: state.avatarFile!.path,
          filename: 'avatar_${user.$id}.jpg',
        ),
      );
      avatarUrl = file.$id;
    }

    // Intentar actualizar primero, si no existe crear
    try {
      await databases.updateDocument(
        databaseId: AppConstants.databaseId,
        collectionId: AppConstants.usersCollection,
        documentId: user.$id,
        data: {
          'username': state.username.trim(),
          'city': state.city.trim(),
          if (avatarUrl != null) 'avatarUrl': avatarUrl,
          'shareLocation': state.shareLocation,
        },
      );
    } on AppwriteException catch (e) {
      if (e.code == 404) {
        // No existe, crear nuevo
        await databases.createDocument(
          databaseId: AppConstants.databaseId,
          collectionId: AppConstants.usersCollection,
          documentId: user.$id,
          data: {
            'userId': user.$id,
            'username': state.username.trim(),
            'city': state.city.trim(),
            'avatarUrl': avatarUrl ?? '',
            'shareLocation': state.shareLocation,
            'createdAt': DateTime.now().toIso8601String(),
          },
        );
      } else {
        rethrow;
      }
    }
  }

  /// Guarda en SharedPreferences (siempre, como cache local)
  Future<void> _saveToPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('profile_username', state.username.trim());
    await prefs.setString('profile_city', state.city.trim());
    await prefs.setBool('profile_share_location', state.shareLocation);
    if (state.avatarFile != null) {
      await prefs.setString('profile_avatar_path', state.avatarFile!.path);
    }
    if (state.latitude != null) {
      await prefs.setDouble('profile_latitude', state.latitude!);
    }
    if (state.longitude != null) {
      await prefs.setDouble('profile_longitude', state.longitude!);
    }
  }

  /// Marca el setup como completado
  Future<void> _markSetupCompleted() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('profile_setup_completed', true);
  }
}

// =============================================================================
// PROVIDERS
// =============================================================================

/// Provider del estado de setup de perfil
final profileSetupProvider =
    StateNotifierProvider<ProfileSetupNotifier, ProfileSetupState>((ref) {
  return ProfileSetupNotifier(ref);
});

/// Provider helper para verificar si el setup está completado
final isProfileSetupCompletedProvider = FutureProvider<bool>((ref) async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool('profile_setup_completed') ?? false;
});

/// Provider helper para verificar si el onboarding está completado
final isOnboardingCompletedProvider = FutureProvider<bool>((ref) async {
  final prefs = await SharedPreferences.getInstance();
  return prefs.getBool('onboarding_completed') ?? false;
});
