import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Tema visual de FishDex - Estilo gaming/gamificado
/// Colores oceánicos + dorados para XP + gradientes vibrantes
class AppTheme {
  AppTheme._();

  // ===========================================================================
  // PALETA DE COLORES PRINCIPAL
  // ===========================================================================
  
  /// Azul oceánico profundo - Color primario
  static const Color primaryBlue = Color(0xFF0D47A1);
  
  /// Azul brillante - Para acentos y CTAs
  static const Color accentBlue = Color(0xFF2196F3);
  
  /// Turquesa/Teal - Para agua y mapas
  static const Color teal = Color(0xFF00BCD4);
  
  /// Dorado - Para XP, niveles y logros
  static const Color gold = Color(0xFFFFD700);
  
  /// Dorado oscuro - Para texto sobre dorado
  static const Color goldDark = Color(0xFFC49000);
  
  /// Verde éxito - Nuevo pez descubierto
  static const Color successGreen = Color(0xFF4CAF50);
  
  /// Naranja energía - Reencuentros y racha
  static const Color energyOrange = Color(0xFFFF9800);
  
  /// Púrpura legendario - Peces legendarios
  static const Color legendaryPurple = Color(0xFF9C27B0);
  
  /// Rojo raro - Peces raros
  static const Color rareRed = Color(0xFFE91E63);
  
  /// Fondo oscuro - Background principal (modo gaming)
  static const Color darkBackground = Color(0xFF0A1628);
  
  /// Superficie oscura - Cards y panels
  static const Color darkSurface = Color(0xFF1A2744);
  
  /// Superficie elevada - Cards elevados
  static const Color darkSurfaceElevated = Color(0xFF243B55);

  // ===========================================================================
  // GRADIENTES
  // ===========================================================================
  
  /// Gradiente principal del header/splash
  static const LinearGradient primaryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF0D47A1), Color(0xFF00BCD4)],
  );
  
  /// Gradiente dorado para XP/niveles
  static const LinearGradient goldGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFFFFD700), Color(0xFFFFA000)],
  );
  
  /// Gradiente legendario
  static const LinearGradient legendaryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [Color(0xFF9C27B0), Color(0xFFE91E63)],
  );

  // ===========================================================================
  // COLORES POR RAREZA
  // ===========================================================================
  
  static Color getRarityColor(String rarity) {
    switch (rarity) {
      case 'common':
        return Colors.grey.shade400;
      case 'uncommon':
        return successGreen;
      case 'rare':
        return accentBlue;
      case 'legendary':
        return legendaryPurple;
      default:
        return Colors.grey;
    }
  }

  // ===========================================================================
  // TEMA OSCURO (PRINCIPAL - ESTILO GAMING)
  // ===========================================================================
  
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: darkBackground,
      colorScheme: const ColorScheme.dark(
        primary: accentBlue,
        secondary: teal,
        tertiary: gold,
        surface: darkSurface,
        error: rareRed,
      ),
      
      // Tipografía gaming
      textTheme: GoogleFonts.rajdhaniTextTheme(
        ThemeData.dark().textTheme,
      ).copyWith(
        // Títulos grandes - para pantallas de resultado
        displayLarge: GoogleFonts.orbitron(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
        displayMedium: GoogleFonts.orbitron(
          fontSize: 24,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
        // Títulos de sección
        headlineLarge: GoogleFonts.rajdhani(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
        headlineMedium: GoogleFonts.rajdhani(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        // Cuerpo de texto
        bodyLarge: GoogleFonts.rajdhani(
          fontSize: 18,
          fontWeight: FontWeight.w500,
          color: Colors.white.withOpacity(0.9),
        ),
        bodyMedium: GoogleFonts.rajdhani(
          fontSize: 16,
          color: Colors.white.withOpacity(0.8),
        ),
        // Labels
        labelLarge: GoogleFonts.rajdhani(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
      ),
      
      // App Bar
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.orbitron(
          fontSize: 18,
          fontWeight: FontWeight.bold,
          color: Colors.white,
        ),
      ),
      
      // Cards
      cardTheme: CardTheme(
        color: darkSurface,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
      ),
      
      // Botones elevados
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: accentBlue,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: GoogleFonts.rajdhani(
            fontSize: 18,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
      
      // Input fields
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: darkSurfaceElevated,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: accentBlue, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        hintStyle: TextStyle(color: Colors.white.withOpacity(0.4)),
        labelStyle: GoogleFonts.rajdhani(color: Colors.white.withOpacity(0.7)),
      ),
      
      // Bottom Navigation
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: darkSurface,
        selectedItemColor: accentBlue,
        unselectedItemColor: Colors.white38,
        type: BottomNavigationBarType.fixed,
        elevation: 8,
      ),
      
      // FAB
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: accentBlue,
        foregroundColor: Colors.white,
        elevation: 6,
      ),
      
      // Snackbar
      snackBarTheme: SnackBarThemeData(
        backgroundColor: darkSurfaceElevated,
        contentTextStyle: GoogleFonts.rajdhani(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  // ===========================================================================
  // TEMA CLARO (Alternativo)
  // ===========================================================================
  
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: const ColorScheme.light(
        primary: primaryBlue,
        secondary: teal,
        tertiary: goldDark,
      ),
      textTheme: GoogleFonts.rajdhaniTextTheme(),
    );
  }
}
