import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../../data/czech_fish_catalog.dart';
import '../../../data/repositories/identification_job_repository.dart';
import '../../../data/services/capture_location_service.dart';
import '../../auth/providers/auth_provider.dart';
import '../../camera/providers/capture_metadata_provider.dart';
import '../../identify/presentation/identifying_screen.dart';
import '../widgets/species_search_field.dart';

/// Pantalla intermedia para ingresar detalles de la captura (especie, tamaño, clima, cebo)
/// antes de iniciar el procesamiento con el servidor de IA.
class CaptureDetailScreen extends ConsumerStatefulWidget {
  final String videoPath;
  final bool hasRecordedLocation;

  const CaptureDetailScreen({
    super.key,
    required this.videoPath,
    this.hasRecordedLocation = false,
  });

  @override
  ConsumerState<CaptureDetailScreen> createState() =>
      _CaptureDetailScreenState();
}

class _CaptureDetailScreenState extends ConsumerState<CaptureDetailScreen> {
  final _formKey = GlobalKey<FormState>();

  CzechSpecies? _selectedSpecies;
  final _sizeController = TextEditingController();
  final _notesController = TextEditingController();
  final _customNameController = TextEditingController();

  String? _selectedWeather;
  String? _selectedBite;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _sizeController.dispose();
    _notesController.dispose();
    _customNameController.dispose();
    super.dispose();
  }

  Future<CaptureCoordinates> _resolveCaptureCoordinates() async {
    final metadata = ref.read(captureMetadataProvider);
    final latitude = metadata.lat;
    final longitude = metadata.lon;

    if (widget.hasRecordedLocation && latitude != null && longitude != null) {
      final recordedCoordinates = CaptureCoordinates(
        latitude: latitude,
        longitude: longitude,
        accuracyMeters: 0,
      );
      if (recordedCoordinates.isValid) return recordedCoordinates;
    }

    final currentCoordinates =
        await CaptureLocationService.getCurrentCoordinates();
    ref.read(captureMetadataProvider.notifier).setLocation(
          currentCoordinates.latitude,
          currentCoordinates.longitude,
        );
    return currentCoordinates;
  }

  Future<void> _handleStartIdentification() async {
    if (!_formKey.currentState!.validate()) return;

    final selectedSpecies = _selectedSpecies;
    if (selectedSpecies == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(context.l10n.captureFieldSpeciesRequired),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      final authUser = ref.read(authStateProvider).valueOrNull;
      if (authUser == null) {
        throw Exception('Usuario no autenticado');
      }

      final jobRepo = ref.read(identificationJobRepositoryProvider);
      final captureMetadataNotifier =
          ref.read(captureMetadataProvider.notifier);
      final coordinates = await _resolveCaptureCoordinates();

      // Guardar en metadata local
      captureMetadataNotifier.setSpecies(selectedSpecies.czechName);
      final parsedSize = double.tryParse(_sizeController.text);
      if (parsedSize != null) {
        captureMetadataNotifier.setSize(parsedSize);
      }
      if (_selectedWeather != null) {
        captureMetadataNotifier.setWeather(_selectedWeather!);
      }
      if (_selectedBite != null) {
        captureMetadataNotifier.setBite(_selectedBite!);
      }
      if (_notesController.text.trim().isNotEmpty) {
        captureMetadataNotifier.setFishState(_notesController.text.trim());
      }
      if (_customNameController.text.trim().isNotEmpty) {
        captureMetadataNotifier
            .setCustomName(_customNameController.text.trim());
      }

      final captureMetadata = ref.read(captureMetadataProvider);

      // 1. Upload video and register job directly to local SQLite
      final createdJobId = await jobRepo.uploadAndStartJob(
        videoPath: widget.videoPath,
        userId: authUser.id, // authUser is a LocalUser, using id instead of $id
        areaCode: captureMetadata.areaCode,
        areaName: captureMetadata.areaName,
        latitude: coordinates.latitude,
        longitude: coordinates.longitude,
        speciesSlug: selectedSpecies.slug,
        notes: _notesController.text.trim().isEmpty
            ? null
            : _notesController.text.trim(),
        weather: _selectedWeather,
        bite: _selectedBite,
        sizeCm: parsedSize,
        fishState: _notesController.text.trim().isEmpty
            ? null
            : _notesController.text.trim(),
        customName: _customNameController.text.trim().isEmpty
            ? null
            : _customNameController.text.trim(),
      );

      // 2. Trigger processing pipeline on local AI Server
      await jobRepo.triggerProcessing(jobId: createdJobId);

      // 4. Navegar a la pantalla de Identificación
      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => IdentifyingScreen(jobId: createdJobId),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isSubmitting = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content:
                Text(context.l10n.captureDetailsProcessingError(e.toString())),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      appBar: AppBar(
        title: Text(context.l10n.captureDetailsTitle),
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: _isSubmitting ? null : () => Navigator.of(context).pop(),
        ),
      ),
      body: _isSubmitting
          ? _buildSubmittingState()
          : SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      context.l10n.captureDetailsIntro,
                      style:
                          const TextStyle(color: Colors.white70, fontSize: 16),
                    ),
                    const SizedBox(height: 24),

                    // Selector de especie (searchable Autocomplete)
                    SpeciesSearchField(
                      initialSpecies: _selectedSpecies,
                      onSelected: (species) {
                        setState(() => _selectedSpecies = species);
                      },
                    ),
                    const SizedBox(height: 16),

                    // Tamaño en cm
                    TextFormField(
                      controller: _sizeController,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        labelText: context.l10n.captureDetailsSizeLabel,
                        prefixIcon: const Icon(Icons.straighten,
                            color: AppTheme.accentBlue),
                      ),
                      validator: (value) {
                        if (value != null && value.trim().isNotEmpty) {
                          final parsed = double.tryParse(value);
                          if (parsed == null) {
                            return context.l10n.captureDetailsInvalidNumber;
                          }
                          if (parsed <= 0) {
                            return context
                                .l10n.captureDetailsSizeGreaterThanZero;
                          }
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Clima dropdown
                    DropdownButtonFormField<String>(
                      value: _selectedWeather,
                      onChanged: (value) =>
                          setState(() => _selectedWeather = value),
                      style: const TextStyle(color: Colors.white),
                      dropdownColor: AppTheme.darkSurfaceElevated,
                      decoration: InputDecoration(
                        labelText: context.l10n.captureDetailsWeatherLabel,
                        prefixIcon: const Icon(Icons.wb_sunny,
                            color: AppTheme.accentBlue),
                      ),
                      items: [
                        DropdownMenuItem(
                            value: 'sunny',
                            child: Text(context.l10n.weatherSunny)),
                        DropdownMenuItem(
                            value: 'cloudy',
                            child: Text(context.l10n.weatherCloudy)),
                        DropdownMenuItem(
                            value: 'rainy',
                            child: Text(context.l10n.weatherRainy)),
                        DropdownMenuItem(
                            value: 'overcast',
                            child: Text(context.l10n.weatherOvercast)),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Cebo dropdown
                    DropdownButtonFormField<String>(
                      value: _selectedBite,
                      onChanged: (value) =>
                          setState(() => _selectedBite = value),
                      style: const TextStyle(color: Colors.white),
                      dropdownColor: AppTheme.darkSurfaceElevated,
                      decoration: InputDecoration(
                        labelText: context.l10n.captureDetailsBaitLabel,
                        prefixIcon: const Icon(Icons.catching_pokemon,
                            color: AppTheme.accentBlue),
                      ),
                      items: [
                        DropdownMenuItem(
                            value: 'worm', child: Text(context.l10n.baitWorm)),
                        DropdownMenuItem(
                            value: 'spinner',
                            child: Text(context.l10n.baitSpinner)),
                        DropdownMenuItem(
                            value: 'fly', child: Text(context.l10n.baitFly)),
                        DropdownMenuItem(
                            value: 'dough',
                            child: Text(context.l10n.baitDough)),
                        DropdownMenuItem(
                            value: 'corn', child: Text(context.l10n.baitCorn)),
                        DropdownMenuItem(
                            value: 'other',
                            child: Text(context.l10n.baitOther)),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Nombre personalizado
                    TextFormField(
                      controller: _customNameController,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        labelText: context.l10n.captureDetailsCustomNameLabel,
                        prefixIcon:
                            const Icon(Icons.badge, color: AppTheme.accentBlue),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Notas/Detalles del pez
                    TextFormField(
                      controller: _notesController,
                      maxLines: 3,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        labelText: context.l10n.captureDetailsNotesLabel,
                        prefixIcon:
                            const Icon(Icons.note, color: AppTheme.accentBlue),
                      ),
                    ),
                    const SizedBox(height: 32),

                    // Botón para procesar
                    SizedBox(
                      width: double.infinity,
                      height: 54,
                      child: ElevatedButton.icon(
                        onPressed: _handleStartIdentification,
                        icon: const Icon(Icons.search, color: Colors.white),
                        label: Text(
                          context.l10n.captureDetailsStartButton,
                          style: const TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
                              color: Colors.white),
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTheme.accentBlue,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 40),
                  ],
                ),
              ),
            ),
    );
  }

  Widget _buildSubmittingState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(color: AppTheme.accentBlue),
            const SizedBox(height: 24),
            Text(
              context.l10n.captureDetailsSubmittingTitle,
              style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.captureDetailsSubmittingSubtitle,
              style:
                  TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 14),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
