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

  /// Variante de superficie (headers, overlays)
  static const Color darkSurfaceVariant = Color(0xFF0D2137);

  /// Superficie más profunda (activity rows, nested containers)
  static const Color darkSurfaceDeep = Color(0xFF0D1B2A);

  /// Gris oceánico para rarity common (armoniza con la paleta)
  static const Color commonGrey = Color(0xFF8899AA);

  // ===========================================================================
  // SPACING TOKENS
  // ===========================================================================

  static const double spaceXs = 4.0;
  static const double spaceSm = 8.0;
  static const double spaceMd = 16.0;
  static const double spaceLg = 24.0;
  static const double spaceXl = 32.0;
  static const double space2xl = 48.0;
  static const double space3xl = 64.0;

  // ===========================================================================
  // RADIUS TOKENS
  // ===========================================================================

  static const double radiusSm = 8.0;
  static const double radiusMd = 12.0;
  static const double radiusLg = 16.0;
  static const double radiusXl = 20.0;
  static const double radiusFull = 999.0;

  // ===========================================================================
  // CUSTOM EASING CURVES (stronger than defaults)
  // ===========================================================================

  /// Strong ease-out: arranca rapido, se siente responsive
  static const Curve curveEaseOut = Cubic(0.23, 1.0, 0.32, 1.0);

  /// Strong ease-in-out: movimiento natural en pantalla
  static const Curve curveEaseInOut = Cubic(0.16, 1.0, 0.3, 1.0);

  /// Snap: para micro-interacciones de feedback
  static const Curve curveSnap = Cubic(0.2, 0.0, 0.0, 1.0);

  // ===========================================================================
  // DURATION TOKENS
  // ===========================================================================

  /// Micro-interacciones (press, hover)
  static const Duration durationFast = Duration(milliseconds: 120);

  /// Transiciones de UI (nav highlights, chips)
  static const Duration durationMedium = Duration(milliseconds: 200);

  /// Animaciones de contenido (cards, modales)
  static const Duration durationSlow = Duration(milliseconds: 350);

  // ===========================================================================
  // OPACITY TOKENS
  // ===========================================================================

  /// Texto secundario
  static const double opacityMuted = 0.55;

  /// Texto terciario / placeholders
  static const double opacitySubtle = 0.4;

  /// Bordes sutiles
  static const double opacityBorder = 0.2;

  /// Overlays y tints
  static const double opacityOverlay = 0.15;

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

  /// Gradiente de superficie (para headers con depth)
  static const LinearGradient surfaceGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [darkSurfaceVariant, darkBackground],
  );

  /// Gradiente de overlay (para el fondo del login/splash)
  static const LinearGradient overlayGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [darkBackground, darkSurfaceVariant],
  );

  // ===========================================================================
  // COLORES POR RAREZA
  // ===========================================================================
  
  static Color getRarityColor(String rarity) {
    switch (rarity) {
      case 'common':
        return commonGrey;
      case 'uncommon':
        return successGreen;
      case 'rare':
        return accentBlue;
      case 'legendary':
        return legendaryPurple;
      default:
        return commonGrey;
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
      
      // Tipografía con type scale sistematizada
      textTheme: GoogleFonts.rajdhaniTextTheme(
        ThemeData.dark().textTheme,
      ).copyWith(
        // Display: títulos de pantallas de resultado/impacto
        displayLarge: GoogleFonts.rajdhani(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: 1.5,
        ),
        displayMedium: GoogleFonts.rajdhani(
          fontSize: 24,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: 1.0,
        ),
        // Headlines: títulos de sección
        headlineLarge: GoogleFonts.rajdhani(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: 1.0,
        ),
        headlineMedium: GoogleFonts.rajdhani(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        // Body: texto de contenido
        bodyLarge: GoogleFonts.rajdhani(
          fontSize: 18,
          fontWeight: FontWeight.w500,
          color: Colors.white.withOpacity(0.9),
        ),
        bodyMedium: GoogleFonts.rajdhani(
          fontSize: 16,
          color: Colors.white.withOpacity(0.8),
        ),
        bodySmall: GoogleFonts.rajdhani(
          fontSize: 14,
          color: Colors.white.withOpacity(opacityMuted),
        ),
        // Labels
        labelLarge: GoogleFonts.rajdhani(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        labelMedium: GoogleFonts.rajdhani(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        labelSmall: GoogleFonts.rajdhani(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: Colors.white.withOpacity(opacityMuted),
        ),
      ),
      
      // App Bar
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: GoogleFonts.rajdhani(
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: 1.5,
        ),
      ),
      
      // Cards
      cardTheme: CardTheme(
        color: darkSurface,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radiusLg),
        ),
      ),
      
      // Botones elevados
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: accentBlue,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radiusMd),
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
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radiusMd),
          borderSide: const BorderSide(color: accentBlue, width: 2),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        hintStyle: TextStyle(color: Colors.white.withOpacity(opacitySubtle)),
        labelStyle: GoogleFonts.rajdhani(color: Colors.white.withOpacity(opacityMuted)),
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radiusSm)),
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

  // ===========================================================================
  // HELPERS
  // ===========================================================================

  /// Sombra estándar para cards elevados
  static List<BoxShadow> cardShadow({Color? color, double blur = 16}) => [
    BoxShadow(
      color: (color ?? accentBlue).withOpacity(0.15),
      blurRadius: blur,
      offset: const Offset(0, 4),
    ),
  ];

  /// Sombra con glow para elementos interactivos
  static List<BoxShadow> glowShadow(Color color, {double intensity = 0.3}) => [
    BoxShadow(
      color: color.withOpacity(intensity),
      blurRadius: 16,
      spreadRadius: 2,
    ),
  ];
}
