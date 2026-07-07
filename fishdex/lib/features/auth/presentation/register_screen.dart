import 'package:appwrite/appwrite.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../../../core/theme/app_theme.dart';
import '../../../data/models/user_role_model.dart';
import '../../../data/services/role_guard_service.dart';
import '../providers/auth_provider.dart';

/// Pantalla de Registro con diseño gamificado
/// Adapta los campos según el rol seleccionado en onboarding
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();
  final _institutionController = TextEditingController();
  final _reasonController = TextEditingController();
  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _errorMessage;
  String _selectedRole = 'fisherman'; // default

  @override
  void initState() {
    super.initState();
    _loadSelectedRole();
  }

  Future<void> _loadSelectedRole() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _selectedRole = prefs.getString('selected_role') ?? 'fisherman';
    });
  }

  bool get _isResearcherRole => _selectedRole == 'researcher';

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _institutionController.dispose();
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _handleRegister() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final authRepo = ref.read(authRepositoryProvider);
      final rolesRepo = ref.read(rolesRepositoryProvider);
      
      // Registrar usuario en Appwrite Auth
      await authRepo.register(
        email: _emailController.text.trim(),
        password: _passwordController.text,
        name: _nameController.text.trim(),
      );
      
      // Auto-login
      await authRepo.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );

      ref.invalidate(authStateProvider);
      final prefs = await SharedPreferences.getInstance();

      // Crear modelo de rol según selección
      if (_isResearcherRole) {
        // Researcher: guardar con estado pendiente
        final appwriteAccount = ref.read(appwriteAccountProvider);
        final user = await appwriteAccount.get();

        final roleModel = UserRoleModel.pendingResearcher(
          userId: user.$id,
          institution: _institutionController.text.trim(),
          reason: _reasonController.text.trim(),
        );

        await rolesRepo.saveUserRole(roleModel);

        // Crear solicitud de aprobación
        await rolesRepo.requestResearcherAccess(
          userId: user.$id,
          username: _nameController.text.trim(),
          institution: _institutionController.text.trim(),
          reason: _reasonController.text.trim(),
        );

        // Guardar rol en prefs
        await prefs.setString('cached_user_role', 'researcher');
        await prefs.setString('cached_approval_status', 'pending');

        if (mounted) {
          context.go('/pending-approval');
        }
      } else {
        // Fisherman: acceso inmediato
        final appwriteAccount = ref.read(appwriteAccountProvider);
        final user = await appwriteAccount.get();

        final roleModel = UserRoleModel.fisherman(user.$id);
        await rolesRepo.saveUserRole(roleModel);

        // Guardar rol en prefs
        await prefs.setString('cached_user_role', 'fisherman');
        await prefs.setString('cached_approval_status', 'approved');

        if (mounted) {
          final profileSetupCompleted =
              prefs.getBool('profile_setup_completed') ?? false;
          if (profileSetupCompleted) {
            context.go('/map');
          } else {
            context.go('/profile-setup');
          }
        }
      }
    } on AppwriteException catch (e) {
      debugPrint('Error Appwrite: [${e.code}] ${e.type} - ${e.message}');
      setState(() {
        if (e.message != null && e.message!.contains('already exists')) {
          _errorMessage = 'Este email ya está registrado';
        } else {
          _errorMessage = 'Error Appwrite [${e.code}]: ${e.message ?? "Error desconocido"}';
        }
      });
    } catch (e) {
      debugPrint('Error inesperado: $e');
      setState(() {
        _errorMessage = 'Error: $e';
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppTheme.darkBackground,
              Color(0xFF0D2137),
            ],
          ),
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Form(
              key: _formKey,
              child: Column(
                children: [
                  const SizedBox(height: 40),
                  
                  // Logo
                  Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: _isResearcherRole
                          ? AppTheme.legendaryGradient
                          : AppTheme.primaryGradient,
                      boxShadow: [
                        BoxShadow(
                          color: (_isResearcherRole
                                  ? Colors.purple
                                  : AppTheme.accentBlue)
                              .withOpacity(0.3),
                          blurRadius: 15,
                        ),
                      ],
                    ),
                    child: Icon(
                      _isResearcherRole ? Icons.biotech : Icons.phishing,
                      size: 40,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 32),
                  
                  // Título
                  Text(
                    'CREAR CUENTA',
                    style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                          letterSpacing: 3,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _isResearcherRole
                        ? 'Registro como investigador'
                        : 'Únete a la comunidad de pescadores',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),

                  // Badge de rol
                  if (_isResearcherRole) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.orange.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Colors.orange.withOpacity(0.4),
                        ),
                      ),
                      child: const Text(
                        'Requiere aprobación de administrador',
                        style: TextStyle(
                          color: Colors.orange,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ],

                  const SizedBox(height: 32),
                  
                  // Error message
                  if (_errorMessage != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: Colors.red.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.red.withOpacity(0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: Colors.red, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(color: Colors.red, fontSize: 14),
                            ),
                          ),
                        ],
                      ),
                    ),
                  
                  // Nombre
                  TextFormField(
                    controller: _nameController,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: _isResearcherRole
                          ? 'Nombre completo'
                          : 'Nombre de Pescador',
                      prefixIcon: Icon(
                        Icons.person_outline,
                        color: Colors.white.withOpacity(0.5),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Ingresa tu nombre';
                      }
                      if (value.length < 3) {
                        return 'Mínimo 3 caracteres';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  
                  // Email
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: _isResearcherRole
                          ? 'Email institucional'
                          : 'Email',
                      prefixIcon: Icon(
                        Icons.email_outlined,
                        color: Colors.white.withOpacity(0.5),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Ingresa tu email';
                      }
                      if (!value.contains('@')) {
                        return 'Email no válido';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  // === CAMPOS ADICIONALES PARA RESEARCHER ===
                  if (_isResearcherRole) ...[
                    // Institución
                    TextFormField(
                      controller: _institutionController,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        labelText: 'Institución / Universidad',
                        prefixIcon: Icon(
                          Icons.school_outlined,
                          color: Colors.white.withOpacity(0.5),
                        ),
                        hintText: 'Ej: Universidad de Barcelona',
                        hintStyle: TextStyle(
                          color: Colors.white.withOpacity(0.3),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Ingresa tu institución';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Motivo de uso
                    TextFormField(
                      controller: _reasonController,
                      style: const TextStyle(color: Colors.white),
                      maxLines: 3,
                      decoration: InputDecoration(
                        labelText: 'Motivo de uso',
                        prefixIcon: Padding(
                          padding: const EdgeInsets.only(bottom: 48),
                          child: Icon(
                            Icons.science_outlined,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                        hintText:
                            'Describe brevemente para qué necesitas '
                            'acceso a los datos completos',
                        hintStyle: TextStyle(
                          color: Colors.white.withOpacity(0.3),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return 'Describe el motivo de uso';
                        }
                        if (value.length < 20) {
                          return 'Mínimo 20 caracteres';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),
                  ],
                  
                  // Contraseña
                  TextFormField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      prefixIcon: Icon(
                        Icons.lock_outline,
                        color: Colors.white.withOpacity(0.5),
                      ),
                      suffixIcon: IconButton(
                        icon: Icon(
                          _obscurePassword
                              ? Icons.visibility_off
                              : Icons.visibility,
                          color: Colors.white.withOpacity(0.5),
                        ),
                        onPressed: () {
                          setState(() => _obscurePassword = !_obscurePassword);
                        },
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Ingresa una contraseña';
                      }
                      if (value.length < 8) {
                        return 'Mínimo 8 caracteres';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  
                  // Confirmar contraseña
                  TextFormField(
                    controller: _confirmPasswordController,
                    obscureText: true,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: 'Confirmar Contraseña',
                      prefixIcon: Icon(
                        Icons.lock_outline,
                        color: Colors.white.withOpacity(0.5),
                      ),
                    ),
                    validator: (value) {
                      if (value != _passwordController.text) {
                        return 'Las contraseñas no coinciden';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 32),
                  
                  // Register button
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _handleRegister,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.successGreen,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                      child: _isLoading
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : Text(
                              _isResearcherRole
                                  ? 'SOLICITAR ACCESO'
                                  : 'CREAR CUENTA',
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 2,
                                color: Colors.white,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  
                  // XP de bienvenida (solo fisherman)
                  if (!_isResearcherRole)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(20),
                        gradient: AppTheme.goldGradient,
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.star, color: Colors.white, size: 16),
                          SizedBox(width: 4),
                          Text(
                            '+50 XP de bienvenida',
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 24),
                  
                  // Link a login
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '¿Ya tienes cuenta? ',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                        ),
                      ),
                      GestureDetector(
                        onTap: () => context.go('/login'),
                        child: const Text(
                          'Inicia Sesión',
                          style: TextStyle(
                            color: AppTheme.accentBlue,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
