import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/czech_fish_catalog.dart';
import '../../../data/repositories/identification_job_repository.dart';
import '../../auth/providers/auth_provider.dart';
import '../../camera/providers/capture_metadata_provider.dart';
import '../../identify/presentation/identifying_screen.dart';
import '../widgets/species_search_field.dart';

/// Pantalla intermedia para ingresar detalles de la captura (especie, tamaño, clima, cebo)
/// antes de iniciar el procesamiento con el servidor de IA.
class CaptureDetailScreen extends ConsumerStatefulWidget {
  final String videoPath;

  const CaptureDetailScreen({super.key, required this.videoPath});

  @override
  ConsumerState<CaptureDetailScreen> createState() => _CaptureDetailScreenState();
}

class _CaptureDetailScreenState extends ConsumerState<CaptureDetailScreen> {
  final _formKey = GlobalKey<FormState>();
  
  CzechSpecies? _selectedSpecies;
  final _sizeController = TextEditingController();
  final _notesController = TextEditingController();
  
  String? _selectedWeather;
  String? _selectedBite;
  bool _isSubmitting = false;

  @override
  void dispose() {
    _sizeController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  Future<void> _handleStartIdentification() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isSubmitting = true);

    try {
      final authUser = ref.read(authStateProvider).valueOrNull;
      if (authUser == null) {
        throw Exception('Usuario no autenticado');
      }

      final jobRepo = ref.read(identificationJobRepositoryProvider);
      final captureMetadataNotifier = ref.read(captureMetadataProvider.notifier);
      final captureMetadata = ref.read(captureMetadataProvider);

      // Guardar en metadata local
      if (_selectedSpecies != null) {
        captureMetadataNotifier.setSpecies(_selectedSpecies!.czechName);
      }
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

      // 1. Upload video and register job directly to local SQLite
      final createdJobId = await jobRepo.uploadAndStartJob(
        videoPath: widget.videoPath,
        userId: authUser.id, // authUser is a LocalUser, using id instead of $id
        areaCode: captureMetadata.areaCode,
        areaName: captureMetadata.areaName,
        latitude: captureMetadata.lat,
        longitude: captureMetadata.lon,
        speciesSlug: _selectedSpecies?.slug,
        notes: _notesController.text.trim().isEmpty ? null : _notesController.text.trim(),
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
      setState(() => _isSubmitting = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error al procesar: ${e.toString()}'),
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
        title: const Text('Detalles de la Captura'),
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
                    const Text(
                      'Completa los datos de tu captura para iniciar la identificación asistida por IA.',
                      style: TextStyle(color: Colors.white70, fontSize: 16),
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
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        labelText: 'Tamaño estimado (cm)',
                        prefixIcon: Icon(Icons.straighten, color: AppTheme.accentBlue),
                      ),
                      validator: (value) {
                        if (value != null && value.trim().isNotEmpty) {
                          final parsed = double.tryParse(value);
                          if (parsed == null) {
                            return 'Ingresa un número válido';
                          }
                          if (parsed <= 0) {
                            return 'El tamaño debe ser mayor a 0';
                          }
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Clima dropdown
                    DropdownButtonFormField<String>(
                      value: _selectedWeather,
                      onChanged: (value) => setState(() => _selectedWeather = value),
                      style: const TextStyle(color: Colors.white),
                      dropdownColor: AppTheme.darkSurfaceElevated,
                      decoration: const InputDecoration(
                        labelText: 'Condiciones climáticas',
                        prefixIcon: Icon(Icons.wb_sunny, color: AppTheme.accentBlue),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'sunny', child: Text('Soleado')),
                        DropdownMenuItem(value: 'cloudy', child: Text('Nublado')),
                        DropdownMenuItem(value: 'rainy', child: Text('Lluvioso')),
                        DropdownMenuItem(value: 'overcast', child: Text('Cubierto')),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Cebo dropdown
                    DropdownButtonFormField<String>(
                      value: _selectedBite,
                      onChanged: (value) => setState(() => _selectedBite = value),
                      style: const TextStyle(color: Colors.white),
                      dropdownColor: AppTheme.darkSurfaceElevated,
                      decoration: const InputDecoration(
                        labelText: 'Cebo utilizado',
                        prefixIcon: Icon(Icons.catching_pokemon, color: AppTheme.accentBlue),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'worm', child: Text('Lombriz')),
                        DropdownMenuItem(value: 'spinner', child: Text('Señuelo')),
                        DropdownMenuItem(value: 'fly', child: Text('Mosca')),
                        DropdownMenuItem(value: 'dough', child: Text('Masa')),
                        DropdownMenuItem(value: 'corn', child: Text('Maíz')),
                        DropdownMenuItem(value: 'other', child: Text('Otro')),
                      ],
                    ),
                    const SizedBox(height: 16),

                    // Notas/Detalles del pez
                    TextFormField(
                      controller: _notesController,
                      maxLines: 3,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        labelText: 'Notas o estado del pez',
                        prefixIcon: Icon(Icons.note, color: AppTheme.accentBlue),
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
                        label: const Text(
                          'Iniciar Identificación',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.white),
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
            const Text(
              'Subiendo y procesando video...',
              style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Esto puede tomar unos segundos. Por favor no cierres la aplicación.',
              style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 14),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
