import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/l10n/l10n_extension.dart';
import '../../profile/providers/profile_setup_provider.dart';

/// Pantalla de configuración de perfil — flujo de 5 pasos
class ProfileSetupScreen extends ConsumerStatefulWidget {
  const ProfileSetupScreen({super.key});

  @override
  ConsumerState<ProfileSetupScreen> createState() => _ProfileSetupScreenState();
}

class _ProfileSetupScreenState extends ConsumerState<ProfileSetupScreen>
    with TickerProviderStateMixin {
  final PageController _pageController = PageController();
  int _currentStep = 0;
  final int _totalSteps = 5;

  // Controllers
  final _usernameController = TextEditingController();
  final _cityController = TextEditingController();
  final _usernameFormKey = GlobalKey<FormState>();

  // Estado local UI
  File? _selectedImage;
  bool _shareLocation = false;
  bool _permissionsGranted = false;
  bool _dataPreloaded = false;

  // Animación de celebración
  late AnimationController _celebrationController;
  late Animation<double> _celebrationScale;

  @override
  void initState() {
    super.initState();
    _celebrationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _celebrationScale = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _celebrationController, curve: Curves.elasticOut),
    );

    // Auto-detectar ubicación solo si no hay ciudad guardada
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final prefs = await SharedPreferences.getInstance();
      final existingCity = prefs.getString('profile_city') ?? '';
      if (existingCity.isEmpty) {
        ref.read(profileSetupProvider.notifier).autoDetectLocation();
      } else {
        // Precargar la ciudad existente en el controller
        _cityController.text = existingCity;
      }
    });
  }

  @override
  void dispose() {
    _pageController.dispose();
    _usernameController.dispose();
    _cityController.dispose();
    _celebrationController.dispose();
    super.dispose();
  }

  /// Pre-carga datos existentes del provider en los controllers
  void _preloadData(ProfileSetupState setupState) {
    if (_dataPreloaded) return;
    _dataPreloaded = true;

    if (setupState.username.isNotEmpty) {
      _usernameController.text = setupState.username;
    }
    if (setupState.city.isNotEmpty) {
      _cityController.text = setupState.city;
    }
    if (setupState.existingAvatarPath != null) {
      final file = File(setupState.existingAvatarPath!);
      if (file.existsSync()) {
        _selectedImage = file;
      }
    }
    _shareLocation = setupState.shareLocation;
  }

  void _nextStep() {
    if (_currentStep == 0) {
      // Validar username
      if (!_usernameFormKey.currentState!.validate()) return;
      ref
          .read(profileSetupProvider.notifier)
          .setUsername(_usernameController.text);
    } else if (_currentStep == 2) {
      ref.read(profileSetupProvider.notifier).setCity(_cityController.text);
      ref.read(profileSetupProvider.notifier).setShareLocation(_shareLocation);
    }

    if (_currentStep < _totalSteps - 1) {
      setState(() => _currentStep++);
      _pageController.nextPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
      // Iniciar animación de celebración en el último paso
      if (_currentStep == _totalSteps - 1) {
        _celebrationController.forward();
      }
    }
  }

  void _previousStep() {
    if (_currentStep > 0) {
      setState(() => _currentStep--);
      _pageController.previousPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    }
  }

  Future<void> _pickImage(ImageSource source) async {
    final picker = ImagePicker();
    final pickedFile = await picker.pickImage(
      source: source,
      maxWidth: 512,
      maxHeight: 512,
      imageQuality: 80,
    );
    if (pickedFile != null) {
      setState(() {
        _selectedImage = File(pickedFile.path);
      });
      ref.read(profileSetupProvider.notifier).setAvatar(_selectedImage);
    }
  }

  Future<void> _requestPermissions() async {
    final cameraStatus = await Permission.camera.request();
    final locationStatus = await Permission.location.request();
    final photosStatus = await Permission.photos.request();

    final allGranted = cameraStatus.isGranted &&
        locationStatus.isGranted &&
        photosStatus.isGranted;

    setState(() => _permissionsGranted = allGranted);
    ref.read(profileSetupProvider.notifier).setPermissionsGranted(allGranted);
  }

  Future<void> _completeSetup() async {
    final setupState = ref.read(profileSetupProvider);

    // Si el username está vacío (saltaron el paso), poner uno por defecto
    if (setupState.username.isEmpty) {
      ref.read(profileSetupProvider.notifier).setUsername(
            'Pescador_${DateTime.now().millisecondsSinceEpoch % 10000}',
          );
    }

    final notifier = ref.read(profileSetupProvider.notifier);
    final success = await notifier.saveProfile();
    if (success && mounted) {
      if (Navigator.of(context).canPop()) {
        Navigator.of(context).pop();
      } else {
        context.go('/map');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final setupState = ref.watch(profileSetupProvider);

    // Pre-cargar datos existentes en los controllers
    _preloadData(setupState);

    // Actualizar city controller cuando auto-detect termina
    if (setupState.city.isNotEmpty && _cityController.text.isEmpty) {
      _cityController.text = setupState.city;
    }

    return Scaffold(
      backgroundColor: AppTheme.darkBackground,
      body: SafeArea(
        child: Column(
          children: [
            const SizedBox(height: 16),
            // Barra de progreso
            _buildProgressBar(),
            const SizedBox(height: 8),
            // Contenido de pasos
            Expanded(
              child: PageView(
                controller: _pageController,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  _buildUsernameStep(),
                  _buildAvatarStep(),
                  _buildLocationStep(setupState),
                  _buildPermissionsStep(),
                  _buildCompletionStep(),
                ],
              ),
            ),
            // Botones de navegación
            if (_currentStep < _totalSteps - 1) _buildNavigationButtons(),
            if (setupState.isLoading)
              const Padding(
                padding: EdgeInsets.all(16),
                child: CircularProgressIndicator(color: AppTheme.accentBlue),
              ),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // BARRA DE PROGRESO
  // ===========================================================================

  Widget _buildProgressBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        children: [
          Row(
            children: [
              if (Navigator.of(context).canPop()) ...[
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white70, size: 20),
                  onPressed: () => Navigator.of(context).pop(),
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                ),
                const SizedBox(width: 12),
              ],
              Text(
                context.l10n.profileSetupStep(_currentStep + 1, _totalSteps),
                style: TextStyle(
                  color: Colors.white.withOpacity(0.7),
                  fontSize: 14,
                ),
              ),
              const Spacer(),
              Text(
                '${((_currentStep + 1) / _totalSteps * 100).toInt()}%',
                style: const TextStyle(
                  color: AppTheme.accentBlue,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (_currentStep + 1) / _totalSteps,
              backgroundColor: AppTheme.darkSurface,
              valueColor:
                  const AlwaysStoppedAnimation<Color>(AppTheme.accentBlue),
              minHeight: 6,
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // PASO 1 — NOMBRE DE USUARIO
  // ===========================================================================

  Widget _buildUsernameStep() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Form(
        key: _usernameFormKey,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(height: 60),
            Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: AppTheme.primaryGradient,
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.accentBlue.withOpacity(0.3),
                    blurRadius: 20,
                  ),
                ],
              ),
              child: const Icon(Icons.person, size: 50, color: Colors.white),
            ),
            const SizedBox(height: 32),
            Text(
              context.l10n.profileSetupUsername,
              style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                    letterSpacing: 1,
                  ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              context.l10n.profileSetupUsernameSubtitle,
              style: TextStyle(
                color: Colors.white.withOpacity(0.6),
                fontSize: 16,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 40),
            TextFormField(
              controller: _usernameController,
              style: const TextStyle(color: Colors.white, fontSize: 18),
              decoration: InputDecoration(
                labelText: context.l10n.profileSetupUsernameLabel,
                hintText: context.l10n.profileSetupUsernameHint,
                prefixIcon: Icon(
                  Icons.alternate_email,
                  color: Colors.white.withOpacity(0.5),
                ),
              ),
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return context.l10n.profileSetupUsernameRequired;
                }
                if (value.trim().length < 3) {
                  return context.l10n.profileSetupUsernameMinChars;
                }
                if (value.contains(' ')) {
                  return context.l10n.profileSetupUsernameNoSpaces;
                }
                return null;
              },
            ),
            const SizedBox(height: 12),
            Text(
              context.l10n.profileSetupUsernameHelper,
              style: TextStyle(
                color: Colors.white.withOpacity(0.4),
                fontSize: 13,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // PASO 2 — FOTO DE PERFIL
  // ===========================================================================

  Widget _buildAvatarStep() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 60),
          Text(
            context.l10n.profileSetupAvatar,
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  letterSpacing: 1,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Text(
            _selectedImage != null
                ? context.l10n.profileSetupAvatarSet
                : context.l10n.profileSetupAvatarEmpty,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 16,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 40),
          // Preview circular
          GestureDetector(
            onTap: () => _showImageSourceDialog(),
            child: Container(
              width: 150,
              height: 150,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTheme.darkSurface,
                border: Border.all(
                  color: _selectedImage != null
                      ? AppTheme.successGreen.withOpacity(0.7)
                      : AppTheme.accentBlue.withOpacity(0.5),
                  width: 3,
                ),
                image: _selectedImage != null
                    ? DecorationImage(
                        image: FileImage(_selectedImage!),
                        fit: BoxFit.cover,
                      )
                    : null,
              ),
              child: _selectedImage == null
                  ? Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.add_a_photo,
                          size: 40,
                          color: Colors.white.withOpacity(0.5),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          context.l10n.profileSetupAvatarTap,
                          style: TextStyle(
                            color: Colors.white.withOpacity(0.5),
                            fontSize: 12,
                          ),
                        ),
                      ],
                    )
                  : null,
            ),
          ),
          const SizedBox(height: 24),
          // Botones
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildImageButton(
                icon: Icons.photo_library,
                label: context.l10n.profileSetupAvatarGallery,
                onTap: () => _pickImage(ImageSource.gallery),
              ),
              const SizedBox(width: 16),
              _buildImageButton(
                icon: Icons.camera_alt,
                label: context.l10n.profileSetupAvatarCamera,
                onTap: () => _pickImage(ImageSource.camera),
              ),
            ],
          ),
          if (_selectedImage != null) ...[
            const SizedBox(height: 16),
            TextButton.icon(
              onPressed: () {
                setState(() => _selectedImage = null);
                ref.read(profileSetupProvider.notifier).setAvatar(null);
              },
              icon: Icon(Icons.delete_outline,
                  color: Colors.red.withOpacity(0.7), size: 18),
              label: Text(
                context.l10n.profileSetupAvatarRemove,
                style: TextStyle(color: Colors.red.withOpacity(0.7)),
              ),
            ),
          ],
          const SizedBox(height: 16),
          if (_selectedImage == null)
            TextButton(
              onPressed: _nextStep,
              child: Text(
                context.l10n.profileSetupAvatarSkip,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.5),
                  fontSize: 16,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildImageButton({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        decoration: BoxDecoration(
          color: AppTheme.darkSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.accentBlue.withOpacity(0.3)),
        ),
        child: Row(
          children: [
            Icon(icon, color: AppTheme.accentBlue, size: 20),
            const SizedBox(width: 8),
            Text(
              label,
              style: const TextStyle(color: Colors.white, fontSize: 14),
            ),
          ],
        ),
      ),
    );
  }

  void _showImageSourceDialog() {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTheme.darkSurface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              context.l10n.profileSetupSelectPhoto,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 20),
            ListTile(
              leading:
                  const Icon(Icons.photo_library, color: AppTheme.accentBlue),
              title: Text(
                context.l10n.profileSetupAvatarGallery,
                style: const TextStyle(color: Colors.white),
              ),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery);
              },
            ),
            ListTile(
              leading:
                  const Icon(Icons.camera_alt, color: AppTheme.accentBlue),
              title: Text(
                context.l10n.profileSetupAvatarCamera,
                style: const TextStyle(color: Colors.white),
              ),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.camera);
              },
            ),
          ],
        ),
      ),
    );
  }

  // ===========================================================================
  // PASO 3 — UBICACIÓN (con auto-detección)
  // ===========================================================================

  Widget _buildLocationStep(ProfileSetupState setupState) {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 60),
          // Icono de mapa
          Container(
            width: 100,
            height: 100,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: AppTheme.primaryGradient,
              boxShadow: [
                BoxShadow(
                  color: AppTheme.teal.withOpacity(0.3),
                  blurRadius: 20,
                ),
              ],
            ),
            child: const Icon(Icons.map, size: 50, color: Colors.white),
          ),
          const SizedBox(height: 32),
          Text(
            context.l10n.profileSetupLocation,
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  letterSpacing: 1,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Text(
            context.l10n.profileSetupLocationSubtitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 16,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),

          // Botón auto-detectar
          SizedBox(
            width: double.infinity,
            height: 48,
            child: OutlinedButton.icon(
              onPressed: setupState.isDetectingLocation
                  ? null
                  : () {
                      ref
                          .read(profileSetupProvider.notifier)
                          .autoDetectLocation();
                    },
              icon: setupState.isDetectingLocation
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: AppTheme.teal,
                      ),
                    )
                  : const Icon(Icons.my_location, color: AppTheme.teal),
              label: Text(
                setupState.isDetectingLocation
                    ? context.l10n.profileSetupDetectingLocation
                    : context.l10n.profileSetupDetectLocation,
                style: const TextStyle(fontSize: 14),
              ),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppTheme.teal,
                side: const BorderSide(color: AppTheme.teal),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
            ),
          ),

          const SizedBox(height: 20),

          // Campo de texto (se llena automático o manual)
          TextFormField(
            controller: _cityController,
            style: const TextStyle(color: Colors.white, fontSize: 18),
            decoration: InputDecoration(
              labelText: context.l10n.profileSetupCityLabel,
              hintText: context.l10n.profileSetupCityHint,
              prefixIcon: Icon(
                Icons.location_city,
                color: Colors.white.withOpacity(0.5),
              ),
              suffixIcon: _cityController.text.isNotEmpty
                  ? Icon(Icons.check_circle,
                      color: AppTheme.successGreen.withOpacity(0.7))
                  : null,
            ),
          ),

          if (setupState.errorMessage != null &&
              setupState.errorMessage!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              setupState.errorMessage!,
              style: TextStyle(
                color: Colors.orange.withOpacity(0.8),
                fontSize: 13,
              ),
            ),
          ],

          if (setupState.latitude != null && setupState.longitude != null) ...[
            const SizedBox(height: 8),
            Text(
              '${context.l10n.mapCoordinates}: ${setupState.latitude!.toStringAsFixed(4)}, ${setupState.longitude!.toStringAsFixed(4)}',
              style: TextStyle(
                color: Colors.white.withOpacity(0.3),
                fontSize: 12,
              ),
            ),
          ],

          const SizedBox(height: 24),
          // Checkbox compartir ubicación
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkSurface,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Checkbox(
                  value: _shareLocation,
                  onChanged: (value) {
                    setState(() => _shareLocation = value ?? false);
                  },
                  activeColor: AppTheme.accentBlue,
                  checkColor: Colors.white,
                ),
                Expanded(
                  child: Text(
                    context.l10n.profileSetupShareLocation,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.8),
                      fontSize: 14,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // PASO 4 — PERMISOS
  // ===========================================================================

  Widget _buildPermissionsStep() {
    return SingleChildScrollView(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const SizedBox(height: 40),
          Text(
            context.l10n.profileSetupPermissions,
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  letterSpacing: 1,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 12),
          Text(
            context.l10n.profileSetupPermissionsSubtitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 16,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          _buildPermissionTile(
            icon: Icons.camera_alt,
            title: context.l10n.profileSetupPermCamera,
            description: context.l10n.profileSetupPermCameraDesc,
            color: AppTheme.accentBlue,
          ),
          const SizedBox(height: 12),
          _buildPermissionTile(
            icon: Icons.location_on,
            title: context.l10n.profileSetupPermLocation,
            description: context.l10n.profileSetupPermLocationDesc,
            color: AppTheme.teal,
          ),
          const SizedBox(height: 12),
          _buildPermissionTile(
            icon: Icons.photo_library,
            title: context.l10n.profileSetupPermGallery,
            description: context.l10n.profileSetupPermGalleryDesc,
            color: AppTheme.energyOrange,
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            height: 56,
            child: ElevatedButton.icon(
              onPressed: _permissionsGranted ? null : _requestPermissions,
              icon: Icon(
                _permissionsGranted ? Icons.check_circle : Icons.security,
                color: Colors.white,
              ),
              label: Text(
                _permissionsGranted
                    ? context.l10n.profileSetupPermissionsGranted
                    : context.l10n.profileSetupGrantPermissions,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1,
                ),
              ),
              style: ElevatedButton.styleFrom(
                backgroundColor: _permissionsGranted
                    ? AppTheme.successGreen
                    : AppTheme.accentBlue,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),
          TextButton(
            onPressed: _nextStep,
            child: Text(
              context.l10n.profileSetupSkipForNow,
              style: TextStyle(
                color: Colors.white.withOpacity(0.5),
                fontSize: 16,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPermissionTile({
    required IconData icon,
    required String title,
    required String description,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 24),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // PASO 5 — COMPLETADO
  // ===========================================================================

  Widget _buildCompletionStep() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          ScaleTransition(
            scale: _celebrationScale,
            child: Container(
              width: 140,
              height: 140,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: AppTheme.goldGradient,
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.gold.withOpacity(0.4),
                    blurRadius: 30,
                    spreadRadius: 5,
                  ),
                ],
              ),
              child: const Icon(
                Icons.celebration,
                size: 70,
                color: Colors.white,
              ),
            ),
          ),
          const SizedBox(height: 40),
          Text(
            context.l10n.profileSetupDoneTitle,
            style: Theme.of(context).textTheme.displayMedium?.copyWith(
                  color: AppTheme.gold,
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            context.l10n.profileSetupDoneSubtitle,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 18,
              height: 1.5,
            ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 48),
          SizedBox(
            width: double.infinity,
            height: 60,
            child: ElevatedButton(
              onPressed: _completeSetup,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.successGreen,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
                elevation: 6,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.phishing, color: Colors.white, size: 24),
                  const SizedBox(width: 12),
                  Text(
                    context.l10n.profileSetupStartButton,
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 2,
                      color: Colors.white,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ===========================================================================
  // BOTONES DE NAVEGACIÓN
  // ===========================================================================

  Widget _buildNavigationButtons() {
    // Paso 3 (índice 3) = Permisos = último paso con botones de navegación
    final isLastStep = _currentStep == _totalSteps - 2;

    return Padding(
      padding: const EdgeInsets.fromLTRB(32, 0, 32, 24),
      child: Row(
        children: [
          if (_currentStep > 0)
            Expanded(
              child: SizedBox(
                height: 52,
                child: OutlinedButton(
                  onPressed: _previousStep,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                    side: BorderSide(color: Colors.white.withOpacity(0.3)),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: Text(
                    context.l10n.back,
                    style: const TextStyle(fontSize: 16),
                  ),
                ),
              ),
            ),
          if (_currentStep > 0) const SizedBox(width: 16),
          Expanded(
            child: SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: isLastStep
                    ? () {
                        // Avanzar al paso de completado y disparar animación
                        setState(() => _currentStep++);
                        _pageController.nextPage(
                          duration: const Duration(milliseconds: 350),
                          curve: Curves.easeInOut,
                        );
                        _celebrationController.forward();
                        // _completeSetup() se llama desde el botón "EMPEZAR A PESCAR!"
                      }
                    : _nextStep,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.accentBlue,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                child: Text(
                  isLastStep
                      ? context.l10n.profileSetupViewProfile
                      : context.l10n.next,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
