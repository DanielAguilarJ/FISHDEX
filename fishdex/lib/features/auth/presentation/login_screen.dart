import 'package:appwrite/appwrite.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/providers/appwrite_providers.dart';
import '../providers/auth_provider.dart';

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
  bool _isPinging = false;
  String? _pingMessage;

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
        final profileSetupCompleted =
            prefs.getBool('profile_setup_completed') ?? false;
        if (profileSetupCompleted) {
          context.go('/map');
        } else {
          context.go('/profile-setup');
        }
      }
    } catch (e) {
      setState(() {
        _errorMessage = 'Email o contraseña incorrectos';
      });
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  Future<void> _handlePing() async {
    setState(() {
      _isPinging = true;
      _pingMessage = null;
    });

    try {
      // Probamos obtener la cuenta anónima para verificar conectividad
      final account = ref.read(appwriteAccountProvider);
      await account.get();
      setState(() {
        _pingMessage = '✅ Pong! Conexión con Appwrite exitosa (sesión activa)';
      });
    } on AppwriteException catch (e) {
      debugPrint('❌ Ping Appwrite Error: [${e.code}] ${e.type} - ${e.message}');
      if (e.code == 401) {
        // 401 = No hay sesión pero el servidor respondió → conectividad OK
        setState(() {
          _pingMessage = '✅ Pong! Conexión con Appwrite exitosa (sin sesión)';
        });
      } else {
        setState(() {
          _pingMessage = '❌ Error Appwrite [${e.code}]: ${e.message}';
        });
      }
    } catch (e) {
      debugPrint('❌ Ping Error: $e');
      setState(() {
        _pingMessage = '❌ Error de conexión: $e';
      });
    } finally {
      if (mounted) {
        setState(() => _isPinging = false);
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
                    'INICIAR SESIÓN',
                    style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                          letterSpacing: 3,
                        ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Bienvenido de vuelta, pescador',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  const SizedBox(height: 40),
                  
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
                  
                  // Email field
                  TextFormField(
                    controller: _emailController,
                    keyboardType: TextInputType.emailAddress,
                    style: const TextStyle(color: Colors.white),
                    decoration: InputDecoration(
                      labelText: 'Email',
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
                  
                  // Password field
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
                        return 'Ingresa tu contraseña';
                      }
                      if (value.length < 8) {
                        return 'Mínimo 8 caracteres';
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
                          : const Text(
                              'ENTRAR',
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                                letterSpacing: 2,
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
                        '¿No tienes cuenta? ',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.6),
                        ),
                      ),
                      GestureDetector(
                        onTap: () => context.go('/register'),
                        child: const Text(
                          'Regístrate',
                          style: TextStyle(
                            color: AppTheme.accentBlue,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 32),
                  
                  // MODO DEMO - Entrar sin backend
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: OutlinedButton.icon(
                      onPressed: () async {
                        final prefs = await SharedPreferences.getInstance();
                        final profileSetupCompleted =
                            prefs.getBool('profile_setup_completed') ?? false;
                        if (mounted) {
                          if (profileSetupCompleted) {
                            context.go('/map');
                          } else {
                            context.go('/profile-setup');
                          }
                        }
                      },
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('MODO DEMO (sin servidor)'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.gold,
                        side: const BorderSide(color: AppTheme.gold),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  
                  // BOTÓN PING - Verificar conexión con Appwrite
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: OutlinedButton.icon(
                      onPressed: _isPinging ? null : _handlePing,
                      icon: _isPinging
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppTheme.accentBlue,
                              ),
                            )
                          : const Icon(Icons.wifi_tethering),
                      label: Text(_isPinging ? 'Pinging...' : 'Send a ping'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.accentBlue,
                        side: const BorderSide(color: AppTheme.accentBlue),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                    ),
                  ),
                  
                  // Resultado del ping
                  if (_pingMessage != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: _pingMessage!.startsWith('✅')
                              ? Colors.green.withOpacity(0.1)
                              : Colors.red.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: _pingMessage!.startsWith('✅')
                                ? Colors.green.withOpacity(0.3)
                                : Colors.red.withOpacity(0.3),
                          ),
                        ),
                        child: Text(
                          _pingMessage!,
                          style: TextStyle(
                            color: _pingMessage!.startsWith('✅')
                                ? Colors.green
                                : Colors.red,
                            fontSize: 13,
                          ),
                          textAlign: TextAlign.center,
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
    return Container(
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
    );
  }
}
