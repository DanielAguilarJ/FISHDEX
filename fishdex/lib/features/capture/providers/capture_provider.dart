import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/constants/app_constants.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../data/models/fish_capture.dart';
import '../../../data/models/identify_result.dart';
import '../../../data/repositories/captures_repository.dart';
import '../../../data/services/gamification_service.dart';

// =============================================================================
// ESTADO DEL FORMULARIO DE CAPTURA
// =============================================================================

/// Estado mutable del formulario de captura
class CaptureFormState {
  /// Resultado de la IA (si existe)
  final IdentifyResult? aiResult;

  /// Si la IA no pudo identificar con confianza suficiente
  final bool requiresManualInput;

  // Campos del formulario
  final String species;
  final String? scientificName;
  final String? family;
  final double? lengthCm;
  final double? weightKg;
  final String? condition; // 'alive', 'released', 'dead'
  final String? predominantColor;
  final String? physicalFeatures;
  final String? notes;
  final double? latitude;
  final double? longitude;
  final String? videoPath;
  final String? imagePath;

  // Estado UI
  final bool isLoading;
  final bool isSaved;
  final String? errorMessage;
  final CaptureResult? result;

  const CaptureFormState({
    this.aiResult,
    this.requiresManualInput = false,
    this.species = '',
    this.scientificName,
    this.family,
    this.lengthCm,
    this.weightKg,
    this.condition,
    this.predominantColor,
    this.physicalFeatures,
    this.notes,
    this.latitude,
    this.longitude,
    this.videoPath,
    this.imagePath,
    this.isLoading = false,
    this.isSaved = false,
    this.errorMessage,
    this.result,
  });

  CaptureFormState copyWith({
    IdentifyResult? aiResult,
    bool? requiresManualInput,
    String? species,
    String? scientificName,
    String? family,
    double? lengthCm,
    double? weightKg,
    String? condition,
    String? predominantColor,
    String? physicalFeatures,
    String? notes,
    double? latitude,
    double? longitude,
    String? videoPath,
    String? imagePath,
    bool? isLoading,
    bool? isSaved,
    String? errorMessage,
    bool clearError = false,
    CaptureResult? result,
  }) {
    return CaptureFormState(
      aiResult: aiResult ?? this.aiResult,
      requiresManualInput: requiresManualInput ?? this.requiresManualInput,
      species: species ?? this.species,
      scientificName: scientificName ?? this.scientificName,
      family: family ?? this.family,
      lengthCm: lengthCm ?? this.lengthCm,
      weightKg: weightKg ?? this.weightKg,
      condition: condition ?? this.condition,
      predominantColor: predominantColor ?? this.predominantColor,
      physicalFeatures: physicalFeatures ?? this.physicalFeatures,
      notes: notes ?? this.notes,
      latitude: latitude ?? this.latitude,
      longitude: longitude ?? this.longitude,
      videoPath: videoPath ?? this.videoPath,
      imagePath: imagePath ?? this.imagePath,
      isLoading: isLoading ?? this.isLoading,
      isSaved: isSaved ?? this.isSaved,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      result: result ?? this.result,
    );
  }
}

// =============================================================================
// NOTIFIER DE CAPTURA
// =============================================================================

class CaptureFormNotifier extends StateNotifier<CaptureFormState> {
  final Ref _ref;

  CaptureFormNotifier(this._ref) : super(const CaptureFormState());

  /// Inicializa el formulario con resultado de la IA
  void initializeWithAiResult(IdentifyResult aiResult, {
    double? latitude,
    double? longitude,
    String? videoPath,
  }) {
    final requiresManual =
        aiResult.confidence < AppConstants.aiConfidenceThreshold;

    state = CaptureFormState(
      aiResult: aiResult,
      requiresManualInput: requiresManual,
      species: requiresManual ? '' : aiResult.species,
      scientificName: null, // La IA placeholder no devuelve nombre científico aún
      family: null,
      lengthCm: aiResult.estimatedSizeCm,
      latitude: latitude,
      longitude: longitude,
      videoPath: videoPath,
    );
  }

  /// Inicializa un formulario completamente manual (sin resultado IA)
  void initializeManual({
    double? latitude,
    double? longitude,
    String? videoPath,
  }) {
    state = CaptureFormState(
      requiresManualInput: true,
      latitude: latitude,
      longitude: longitude,
      videoPath: videoPath,
    );
  }

  // Setters para los campos del formulario
  void setSpecies(String value) =>
      state = state.copyWith(species: value, clearError: true);
  void setScientificName(String value) =>
      state = state.copyWith(scientificName: value);
  void setFamily(String value) =>
      state = state.copyWith(family: value);
  void setLengthCm(double? value) =>
      state = state.copyWith(lengthCm: value);
  void setWeightKg(double? value) =>
      state = state.copyWith(weightKg: value);
  void setCondition(String? value) =>
      state = state.copyWith(condition: value);
  void setPredominantColor(String? value) =>
      state = state.copyWith(predominantColor: value);
  void setPhysicalFeatures(String? value) =>
      state = state.copyWith(physicalFeatures: value);
  void setNotes(String? value) =>
      state = state.copyWith(notes: value);
  void setLatitude(double? value) =>
      state = state.copyWith(latitude: value);
  void setLongitude(double? value) =>
      state = state.copyWith(longitude: value);

  /// Guarda la captura completa
  Future<bool> saveCapture(String userId) async {
    if (state.species.isEmpty) {
      state = state.copyWith(
          errorMessage: 'Debes indicar la especie o descripción del pez');
      return false;
    }
    if (state.lengthCm == null || state.lengthCm! <= 0) {
      state = state.copyWith(
          errorMessage: 'Debes indicar la longitud estimada');
      return false;
    }
    if (state.condition == null || state.condition!.isEmpty) {
      state = state.copyWith(
          errorMessage: 'Debes indicar la condición del pez');
      return false;
    }

    state = state.copyWith(isLoading: true, clearError: true);

    try {
      final capturesRepo = _ref.read(capturesRepositoryProvider);

      // 1. Match o crear fish_id
      final matchResult = await capturesRepo.matchOrCreateFishId(
        species: state.species,
        latitude: state.latitude ?? 0.0,
        longitude: state.longitude ?? 0.0,
      );

      // 2. Calcular XP
      final gamification = GamificationService();
      final rarity = state.aiResult?.rarity ?? 'common';
      final xpEarned = gamification.calculateXP(rarity, matchResult.isNewFish);

      // 3. Construir FishCapture
      final capture = FishCapture(
        captureId: '', // Se genera en el repositorio
        fishId: matchResult.fishId,
        userId: userId,
        latitude: state.latitude ?? 0.0,
        longitude: state.longitude ?? 0.0,
        capturedAt: DateTime.now(),
        species: state.species,
        scientificName: state.scientificName,
        family: state.family,
        lengthCm: state.lengthCm,
        weightKg: state.weightKg,
        condition: state.condition,
        videoUrl: state.videoPath, // En producción se subiría a Storage primero
        imageUrl: state.imagePath,
        confidence: state.aiResult?.confidence ?? 0.0,
        predominantColor: state.predominantColor,
        physicalFeatures: state.physicalFeatures,
        notes: state.notes,
        rarity: rarity,
        isManualEntry: state.requiresManualInput,
        xpEarned: xpEarned,
        isNewFish: matchResult.isNewFish,
      );

      // 4. Guardar
      final result = await capturesRepo.saveCapture(capture);

      state = state.copyWith(
        isLoading: false,
        isSaved: result.success,
        result: result,
        errorMessage: result.success ? null : result.errorMessage,
      );

      return result.success;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: 'Error al guardar la captura: $e',
      );
      return false;
    }
  }
}

// =============================================================================
// PROVIDERS
// =============================================================================

/// Provider del formulario de captura
final captureFormProvider =
    StateNotifierProvider<CaptureFormNotifier, CaptureFormState>((ref) {
  return CaptureFormNotifier(ref);
});
