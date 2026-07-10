import 'package:appwrite/appwrite.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../providers/auth_provider.dart';
import '../../../core/l10n/l10n_extension.dart';

/// Pantalla de Login con diseño gamificado
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;
  bool _obscurePassword = true;
  String? _errorMessage;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    // Capture l10n before async gap
    final l10n = context.l10n;

    try {
      final authRepo = ref.read(authRepositoryProvider);
      await authRepo.login(
        email: _emailController.text.trim(),
        password: _passwordController.text,
      );
      ref.invalidate(authStateProvider);
      
      if (mounted) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setBool('has_active_session', true);
        await prefs.setBool('is_demo_mode', false); // limpiar flag demo al hacer login real
        final profileSetupCompleted =
            prefs.getBool('profile_setup_completed') ?? false;
        if (profileSetupCompleted) {
          context.go('/map');
        } else {
          context.go('/profile-setup');
        }
      }
    } catch (e) {
      String errorMsg;
      final errorStr = e.toString().toLowerCase();
      if (errorStr.contains('401') || errorStr.contains('invalid')) {
        errorMsg = l10n.loginWrongCredentials;
      } else if (errorStr.contains('connection') || errorStr.contains('socket')) {
        errorMsg = l10n.noConnection;
      } else {
        errorMsg = '${l10n.loginError}: $e';
      }
      setState(() => _errorMessage = errorMsg);
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _handlePing() async {
    try {
      final account = ref.read(appwriteAccountProvider);
      await account.get();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Pong! Conexion con Appwrite exitosa')),
        );
      }
    } on AppwriteException catch (e) {
      if (e.code == 401) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Pong! Servidor responde (sin sesion)')),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Error Appwrite [${e.code}]: ${e.message}')),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error de conexion: $e')),
        );
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
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(height: 60),
                  
                  // Logo
                  _buildLogo(),
                  const SizedBox(height: 48),
                  
                  // Título
                  Text(
                    context.l10n.loginTitle,
                    style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                          letterSpacing: 1.5,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    context.l10n.loginSubtitle,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 40),
                  
                  // Error message
                  if (_errorMessage != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 16),
                      decoration: BoxDecoration(
                        color: AppTheme.rareRed.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(AppTheme.radiusSm),
                        border: Border.all(color: AppTheme.rareRed.withOpacity(0.3)),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.error_outline, color: AppTheme.rareRed, size: 20),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _errorMessage!,
                              style: const TextStyle(color: AppTheme.rareRed, fontSize: 14),
                            ),
                          ),
                        ],
                      ),
                    ),
                  
                  // Email field
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: context.l10n.fieldEmail,
                      prefixIcon: Icon(
                        Icons.email_outlined,
                        color: Colors.white.withOpacity(0.5),
                      ),
                    ),
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return context.l10n.fieldEmailEnter;
                      }
                      if (!value.contains('@')) {
                        return context.l10n.fieldEmailInvalid;
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  
                  // Password field
                  TextFormField(
                    controller: _passwordController,
                    obscureText: _obscurePassword,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: context.l10n.fieldPassword,
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
                        return context.l10n.fieldPasswordEnter;
                      }
                      if (value.length < 8) {
                        return context.l10n.fieldPasswordMin;
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 32),
                  
                  // Login button
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton(
                      onPressed: _isLoading ? null : _handleLogin,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppTheme.accentBlue,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(AppTheme.radiusMd),
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
                              context.l10n.loginButton,
                              style: const TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 1.5,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  
                  // Link a registro
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        context.l10n.loginNoAccount,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                        ),
                      ),
                      GestureDetector(
                        onTap: () => context.go('/register'),
                        child: Text(
                          context.l10n.loginRegister,
                          style: const TextStyle(
                            color: AppTheme.accentBlue,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  
                  // MODO DEMO - Entrar sin backend
                  TextButton(
                    onPressed: () async {
                      final prefs = await SharedPreferences.getInstance();
                      await prefs.setBool('is_demo_mode', true);
                      await prefs.setBool('onboarding_completed', true);
                      if (context.mounted) context.go('/map');
                    },
                    child: Text(
                      context.l10n.loginDemoMode,
                      style: TextStyle(
                        color: Colors.white.withOpacity(AppTheme.opacityMuted),
                        fontSize: 14,
                      ),
                    ),
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

  Widget _buildLogo() {
    return GestureDetector(
      onLongPress: _handlePing, // Hidden dev tool: long-press logo to ping
      child: Container(
        width: 100,
        height: 100,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: AppTheme.primaryGradient,
          boxShadow: [
            BoxShadow(
              color: AppTheme.accentBlue.withOpacity(0.4),
              blurRadius: 20,
              spreadRadius: 2,
            ),
          ],
        ),
        child: const Icon(
          Icons.phishing,
          size: 50,
          color: Colors.white,
        ),
      ),
    );
  }
}
