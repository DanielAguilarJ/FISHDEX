import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_cs.dart';
import 'app_localizations_en.dart';
import 'app_localizations_es.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale) : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate = _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates = <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('cs'),
    Locale('en'),
    Locale('es')
  ];

  /// App title
  ///
  /// In es, this message translates to:
  /// **'FishDex'**
  String get appTitle;

  /// No description provided for @appTagline.
  ///
  /// In es, this message translates to:
  /// **'Identifica peces con IA'**
  String get appTagline;

  /// No description provided for @loading.
  ///
  /// In es, this message translates to:
  /// **'Cargando...'**
  String get loading;

  /// No description provided for @save.
  ///
  /// In es, this message translates to:
  /// **'Guardar'**
  String get save;

  /// No description provided for @cancel.
  ///
  /// In es, this message translates to:
  /// **'Cancelar'**
  String get cancel;

  /// No description provided for @retry.
  ///
  /// In es, this message translates to:
  /// **'Reintentar'**
  String get retry;

  /// No description provided for @skip.
  ///
  /// In es, this message translates to:
  /// **'Saltar'**
  String get skip;

  /// No description provided for @next.
  ///
  /// In es, this message translates to:
  /// **'Siguiente'**
  String get next;

  /// No description provided for @back.
  ///
  /// In es, this message translates to:
  /// **'Atrás'**
  String get back;

  /// No description provided for @close.
  ///
  /// In es, this message translates to:
  /// **'Cerrar'**
  String get close;

  /// No description provided for @delete.
  ///
  /// In es, this message translates to:
  /// **'Eliminar'**
  String get delete;

  /// No description provided for @edit.
  ///
  /// In es, this message translates to:
  /// **'Editar'**
  String get edit;

  /// No description provided for @confirm.
  ///
  /// In es, this message translates to:
  /// **'Confirmar'**
  String get confirm;

  /// No description provided for @comingSoon.
  ///
  /// In es, this message translates to:
  /// **'Próximamente'**
  String get comingSoon;

  /// No description provided for @error.
  ///
  /// In es, this message translates to:
  /// **'Error'**
  String get error;

  /// No description provided for @success.
  ///
  /// In es, this message translates to:
  /// **'Éxito'**
  String get success;

  /// No description provided for @noConnection.
  ///
  /// In es, this message translates to:
  /// **'Sin conexión. Verifica tu internet'**
  String get noConnection;

  /// No description provided for @unknownError.
  ///
  /// In es, this message translates to:
  /// **'Error desconocido'**
  String get unknownError;

  /// No description provided for @serverError.
  ///
  /// In es, this message translates to:
  /// **'Error del servidor. Inténtalo más tarde'**
  String get serverError;

  /// No description provided for @navMap.
  ///
  /// In es, this message translates to:
  /// **'Mapa'**
  String get navMap;

  /// No description provided for @navCollection.
  ///
  /// In es, this message translates to:
  /// **'Colección'**
  String get navCollection;

  /// No description provided for @navRanking.
  ///
  /// In es, this message translates to:
  /// **'Ranking'**
  String get navRanking;

  /// No description provided for @navProfile.
  ///
  /// In es, this message translates to:
  /// **'Perfil'**
  String get navProfile;

  /// No description provided for @navGallery.
  ///
  /// In es, this message translates to:
  /// **'Galería'**
  String get navGallery;

  /// No description provided for @navIdentify.
  ///
  /// In es, this message translates to:
  /// **'Identificar'**
  String get navIdentify;

  /// No description provided for @navSpot.
  ///
  /// In es, this message translates to:
  /// **'Spot'**
  String get navSpot;

  /// No description provided for @loginTitle.
  ///
  /// In es, this message translates to:
  /// **'INICIAR SESIÓN'**
  String get loginTitle;

  /// No description provided for @loginSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Bienvenido de vuelta, pescador'**
  String get loginSubtitle;

  /// No description provided for @loginButton.
  ///
  /// In es, this message translates to:
  /// **'ENTRAR'**
  String get loginButton;

  /// No description provided for @loginDemoMode.
  ///
  /// In es, this message translates to:
  /// **'MODO DEMO (sin servidor)'**
  String get loginDemoMode;

  /// No description provided for @loginNoAccount.
  ///
  /// In es, this message translates to:
  /// **'¿No tienes cuenta? '**
  String get loginNoAccount;

  /// No description provided for @loginRegister.
  ///
  /// In es, this message translates to:
  /// **'Regístrate'**
  String get loginRegister;

  /// No description provided for @loginPinging.
  ///
  /// In es, this message translates to:
  /// **'Pinging...'**
  String get loginPinging;

  /// No description provided for @loginSendPing.
  ///
  /// In es, this message translates to:
  /// **'Send a ping'**
  String get loginSendPing;

  /// No description provided for @loginError.
  ///
  /// In es, this message translates to:
  /// **'Error al iniciar sesión'**
  String get loginError;

  /// No description provided for @loginWrongCredentials.
  ///
  /// In es, this message translates to:
  /// **'Email o contraseña incorrectos'**
  String get loginWrongCredentials;

  /// No description provided for @loginTooManyAttempts.
  ///
  /// In es, this message translates to:
  /// **'Demasiados intentos. Espera un momento'**
  String get loginTooManyAttempts;

  /// No description provided for @registerTitle.
  ///
  /// In es, this message translates to:
  /// **'CREAR CUENTA'**
  String get registerTitle;

  /// No description provided for @registerSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Únete a la comunidad de pescadores'**
  String get registerSubtitle;

  /// No description provided for @registerResearcherSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Registro como investigador'**
  String get registerResearcherSubtitle;

  /// No description provided for @registerButton.
  ///
  /// In es, this message translates to:
  /// **'CREAR CUENTA'**
  String get registerButton;

  /// No description provided for @registerResearcherButton.
  ///
  /// In es, this message translates to:
  /// **'SOLICITAR ACCESO'**
  String get registerResearcherButton;

  /// No description provided for @registerHasAccount.
  ///
  /// In es, this message translates to:
  /// **'¿Ya tienes cuenta? '**
  String get registerHasAccount;

  /// No description provided for @registerLogin.
  ///
  /// In es, this message translates to:
  /// **'Inicia Sesión'**
  String get registerLogin;

  /// No description provided for @registerWelcomeXp.
  ///
  /// In es, this message translates to:
  /// **'+50 XP de bienvenida'**
  String get registerWelcomeXp;

  /// No description provided for @registerApprovalRequired.
  ///
  /// In es, this message translates to:
  /// **'Requiere aprobación de administrador'**
  String get registerApprovalRequired;

  /// No description provided for @registerEmailAlreadyExists.
  ///
  /// In es, this message translates to:
  /// **'Este email ya está registrado'**
  String get registerEmailAlreadyExists;

  /// No description provided for @fieldEmail.
  ///
  /// In es, this message translates to:
  /// **'Email'**
  String get fieldEmail;

  /// No description provided for @fieldEmailInstitutional.
  ///
  /// In es, this message translates to:
  /// **'Email institucional'**
  String get fieldEmailInstitutional;

  /// No description provided for @fieldEmailEnter.
  ///
  /// In es, this message translates to:
  /// **'Ingresa tu email'**
  String get fieldEmailEnter;

  /// No description provided for @fieldEmailInvalid.
  ///
  /// In es, this message translates to:
  /// **'Email no válido'**
  String get fieldEmailInvalid;

  /// No description provided for @fieldPassword.
  ///
  /// In es, this message translates to:
  /// **'Contraseña'**
  String get fieldPassword;

  /// No description provided for @fieldPasswordEnter.
  ///
  /// In es, this message translates to:
  /// **'Ingresa una contraseña'**
  String get fieldPasswordEnter;

  /// No description provided for @fieldPasswordMin.
  ///
  /// In es, this message translates to:
  /// **'Mínimo 8 caracteres'**
  String get fieldPasswordMin;

  /// No description provided for @fieldPasswordConfirm.
  ///
  /// In es, this message translates to:
  /// **'Confirmar Contraseña'**
  String get fieldPasswordConfirm;

  /// No description provided for @fieldPasswordMismatch.
  ///
  /// In es, this message translates to:
  /// **'Las contraseñas no coinciden'**
  String get fieldPasswordMismatch;

  /// No description provided for @fieldName.
  ///
  /// In es, this message translates to:
  /// **'Nombre de Pescador'**
  String get fieldName;

  /// No description provided for @fieldNameFull.
  ///
  /// In es, this message translates to:
  /// **'Nombre completo'**
  String get fieldNameFull;

  /// No description provided for @fieldNameEnter.
  ///
  /// In es, this message translates to:
  /// **'Ingresa tu nombre'**
  String get fieldNameEnter;

  /// No description provided for @fieldNameMin.
  ///
  /// In es, this message translates to:
  /// **'Mínimo 3 caracteres'**
  String get fieldNameMin;

  /// No description provided for @fieldInstitution.
  ///
  /// In es, this message translates to:
  /// **'Institución / Universidad'**
  String get fieldInstitution;

  /// No description provided for @fieldInstitutionEnter.
  ///
  /// In es, this message translates to:
  /// **'Ingresa tu institución'**
  String get fieldInstitutionEnter;

  /// No description provided for @fieldInstitutionHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: Universidad de Barcelona'**
  String get fieldInstitutionHint;

  /// No description provided for @fieldReason.
  ///
  /// In es, this message translates to:
  /// **'Motivo de uso'**
  String get fieldReason;

  /// No description provided for @fieldReasonHint.
  ///
  /// In es, this message translates to:
  /// **'Describe brevemente para qué necesitas acceso a los datos completos'**
  String get fieldReasonHint;

  /// No description provided for @fieldReasonMin.
  ///
  /// In es, this message translates to:
  /// **'Mínimo 20 caracteres'**
  String get fieldReasonMin;

  /// No description provided for @onboardingSkip.
  ///
  /// In es, this message translates to:
  /// **'Saltar'**
  String get onboardingSkip;

  /// No description provided for @onboardingChooseRole.
  ///
  /// In es, this message translates to:
  /// **'Elegir mi rol'**
  String get onboardingChooseRole;

  /// No description provided for @onboardingPage1Title.
  ///
  /// In es, this message translates to:
  /// **'Identifica Peces'**
  String get onboardingPage1Title;

  /// No description provided for @onboardingPage1Desc.
  ///
  /// In es, this message translates to:
  /// **'Usa la cámara para grabar peces en su hábitat natural. Nuestra IA identifica cada pez individualmente, como una huella dactilar submarina.'**
  String get onboardingPage1Desc;

  /// No description provided for @onboardingPage2Title.
  ///
  /// In es, this message translates to:
  /// **'Colecciona y Compite'**
  String get onboardingPage2Title;

  /// No description provided for @onboardingPage2Desc.
  ///
  /// In es, this message translates to:
  /// **'Construye tu FishDex como un Pokédex acuático. Descubre especies raras, gana XP, sube de nivel y compite en el ranking con otros exploradores.'**
  String get onboardingPage2Desc;

  /// No description provided for @onboardingPage3Title.
  ///
  /// In es, this message translates to:
  /// **'Contribuye a la Ciencia'**
  String get onboardingPage3Title;

  /// No description provided for @onboardingPage3Desc.
  ///
  /// In es, this message translates to:
  /// **'Cada avistamiento ayuda a los investigadores a rastrear migración, crecimiento y salud de los ecosistemas marinos. Tus datos hacen la diferencia.'**
  String get onboardingPage3Desc;

  /// No description provided for @onboardingRoleTitle.
  ///
  /// In es, this message translates to:
  /// **'¿Cuál es tu perfil?'**
  String get onboardingRoleTitle;

  /// No description provided for @onboardingRoleSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Esto define qué datos puedes ver en la app'**
  String get onboardingRoleSubtitle;

  /// No description provided for @onboardingFishermanTitle.
  ///
  /// In es, this message translates to:
  /// **'Soy Pescador'**
  String get onboardingFishermanTitle;

  /// No description provided for @onboardingFishermanDesc.
  ///
  /// In es, this message translates to:
  /// **'Registra tus capturas, colecciona especies y compite en el ranking. Acceso inmediato.'**
  String get onboardingFishermanDesc;

  /// No description provided for @onboardingResearcherTitle.
  ///
  /// In es, this message translates to:
  /// **'Soy Investigador'**
  String get onboardingResearcherTitle;

  /// No description provided for @onboardingResearcherDesc.
  ///
  /// In es, this message translates to:
  /// **'Accede a datos completos de ubicación, historial y estadísticas. Requiere aprobación de un admin.'**
  String get onboardingResearcherDesc;

  /// No description provided for @onboardingRequiresApproval.
  ///
  /// In es, this message translates to:
  /// **'Requiere aprobación'**
  String get onboardingRequiresApproval;

  /// No description provided for @pendingApprovalTitle.
  ///
  /// In es, this message translates to:
  /// **'Solicitud Enviada'**
  String get pendingApprovalTitle;

  /// No description provided for @pendingApprovalDesc.
  ///
  /// In es, this message translates to:
  /// **'Tu solicitud como investigador está siendo revisada por un administrador.'**
  String get pendingApprovalDesc;

  /// No description provided for @pendingApprovalNote.
  ///
  /// In es, this message translates to:
  /// **'Te notificaremos automáticamente cuando sea aprobada. No necesitas cerrar la app.'**
  String get pendingApprovalNote;

  /// No description provided for @pendingApprovalStatus.
  ///
  /// In es, this message translates to:
  /// **'Pendiente de aprobación'**
  String get pendingApprovalStatus;

  /// No description provided for @pendingApprovalApproved.
  ///
  /// In es, this message translates to:
  /// **'Tu cuenta ha sido aprobada!'**
  String get pendingApprovalApproved;

  /// No description provided for @pendingApprovalRejected.
  ///
  /// In es, this message translates to:
  /// **'Tu solicitud ha sido rechazada. Contacta al administrador.'**
  String get pendingApprovalRejected;

  /// No description provided for @pendingApprovalLogout.
  ///
  /// In es, this message translates to:
  /// **'Cerrar sesión'**
  String get pendingApprovalLogout;

  /// No description provided for @profileTitle.
  ///
  /// In es, this message translates to:
  /// **'Perfil'**
  String get profileTitle;

  /// No description provided for @profileEditButton.
  ///
  /// In es, this message translates to:
  /// **'Editar perfil'**
  String get profileEditButton;

  /// No description provided for @profileLogout.
  ///
  /// In es, this message translates to:
  /// **'Cerrar sesión'**
  String get profileLogout;

  /// No description provided for @profileLogoutConfirm.
  ///
  /// In es, this message translates to:
  /// **'¿Seguro que quieres cerrar sesión?'**
  String get profileLogoutConfirm;

  /// No description provided for @profileLogoutTitle.
  ///
  /// In es, this message translates to:
  /// **'Cerrar sesión'**
  String get profileLogoutTitle;

  /// No description provided for @profileStatsTitle.
  ///
  /// In es, this message translates to:
  /// **'ESTADÍSTICAS'**
  String get profileStatsTitle;

  /// No description provided for @profileQuickAccess.
  ///
  /// In es, this message translates to:
  /// **'ACCESOS RÁPIDOS'**
  String get profileQuickAccess;

  /// No description provided for @profileSummary.
  ///
  /// In es, this message translates to:
  /// **'RESUMEN'**
  String get profileSummary;

  /// No description provided for @profileLastActivity.
  ///
  /// In es, this message translates to:
  /// **'Última actividad'**
  String get profileLastActivity;

  /// No description provided for @profileTotalCaptures.
  ///
  /// In es, this message translates to:
  /// **'Total capturas'**
  String get profileTotalCaptures;

  /// No description provided for @profileUniqueSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especies únicas'**
  String get profileUniqueSpecies;

  /// No description provided for @profileTotalXp.
  ///
  /// In es, this message translates to:
  /// **'XP total'**
  String get profileTotalXp;

  /// No description provided for @profileAdminPanel.
  ///
  /// In es, this message translates to:
  /// **'Panel de Administración'**
  String get profileAdminPanel;

  /// No description provided for @profileNoActivity.
  ///
  /// In es, this message translates to:
  /// **'Sin actividad reciente'**
  String get profileNoActivity;

  /// No description provided for @profileMinutesAgo.
  ///
  /// In es, this message translates to:
  /// **'Hace {minutes} min'**
  String profileMinutesAgo(int minutes);

  /// No description provided for @profileHoursAgo.
  ///
  /// In es, this message translates to:
  /// **'Hace {hours}h'**
  String profileHoursAgo(int hours);

  /// No description provided for @profileDaysAgo.
  ///
  /// In es, this message translates to:
  /// **'Hace {days} días'**
  String profileDaysAgo(int days);

  /// No description provided for @levelTitle.
  ///
  /// In es, this message translates to:
  /// **'NV. {level}'**
  String levelTitle(int level);

  /// No description provided for @levelBeginner.
  ///
  /// In es, this message translates to:
  /// **'Principiante'**
  String get levelBeginner;

  /// No description provided for @levelApprentice.
  ///
  /// In es, this message translates to:
  /// **'Aprendiz'**
  String get levelApprentice;

  /// No description provided for @levelIntermediate.
  ///
  /// In es, this message translates to:
  /// **'Intermedio'**
  String get levelIntermediate;

  /// No description provided for @levelAdvanced.
  ///
  /// In es, this message translates to:
  /// **'Avanzado'**
  String get levelAdvanced;

  /// No description provided for @levelVeteran.
  ///
  /// In es, this message translates to:
  /// **'Veterano'**
  String get levelVeteran;

  /// No description provided for @levelExpert.
  ///
  /// In es, this message translates to:
  /// **'Experto'**
  String get levelExpert;

  /// No description provided for @levelMaster.
  ///
  /// In es, this message translates to:
  /// **'Maestro'**
  String get levelMaster;

  /// No description provided for @levelGrandMaster.
  ///
  /// In es, this message translates to:
  /// **'Gran Maestro'**
  String get levelGrandMaster;

  /// No description provided for @levelLegendaryMaster.
  ///
  /// In es, this message translates to:
  /// **'Maestro Legendario'**
  String get levelLegendaryMaster;

  /// No description provided for @statsCaptures.
  ///
  /// In es, this message translates to:
  /// **'Capturas'**
  String get statsCaptures;

  /// No description provided for @statsSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especies'**
  String get statsSpecies;

  /// No description provided for @statsRare.
  ///
  /// In es, this message translates to:
  /// **'Raros'**
  String get statsRare;

  /// No description provided for @statsLegendary.
  ///
  /// In es, this message translates to:
  /// **'Legendarios'**
  String get statsLegendary;

  /// No description provided for @roleAdmin.
  ///
  /// In es, this message translates to:
  /// **'Administrador'**
  String get roleAdmin;

  /// No description provided for @roleFisherman.
  ///
  /// In es, this message translates to:
  /// **'Pescador'**
  String get roleFisherman;

  /// No description provided for @roleResearcher.
  ///
  /// In es, this message translates to:
  /// **'Investigador'**
  String get roleResearcher;

  /// No description provided for @profileSetupStep.
  ///
  /// In es, this message translates to:
  /// **'Paso {current} de {total}'**
  String profileSetupStep(int current, int total);

  /// No description provided for @profileSetupUsername.
  ///
  /// In es, this message translates to:
  /// **'Elige tu nombre de pescador'**
  String get profileSetupUsername;

  /// No description provided for @profileSetupUsernameSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Este nombre te identificará en la comunidad'**
  String get profileSetupUsernameSubtitle;

  /// No description provided for @profileSetupUsernameLabel.
  ///
  /// In es, this message translates to:
  /// **'Nombre de usuario'**
  String get profileSetupUsernameLabel;

  /// No description provided for @profileSetupUsernameHint.
  ///
  /// In es, this message translates to:
  /// **'ej: PescadorPro123'**
  String get profileSetupUsernameHint;

  /// No description provided for @profileSetupUsernameHelper.
  ///
  /// In es, this message translates to:
  /// **'Mínimo 3 caracteres, sin espacios'**
  String get profileSetupUsernameHelper;

  /// No description provided for @profileSetupUsernameRequired.
  ///
  /// In es, this message translates to:
  /// **'Ingresa un nombre de usuario'**
  String get profileSetupUsernameRequired;

  /// No description provided for @profileSetupUsernameMinChars.
  ///
  /// In es, this message translates to:
  /// **'Mínimo 3 caracteres'**
  String get profileSetupUsernameMinChars;

  /// No description provided for @profileSetupUsernameNoSpaces.
  ///
  /// In es, this message translates to:
  /// **'No se permiten espacios'**
  String get profileSetupUsernameNoSpaces;

  /// No description provided for @profileSetupAvatar.
  ///
  /// In es, this message translates to:
  /// **'Foto de perfil'**
  String get profileSetupAvatar;

  /// No description provided for @profileSetupAvatarSet.
  ///
  /// In es, this message translates to:
  /// **'¡Se ve genial! Puedes cambiarla cuando quieras'**
  String get profileSetupAvatarSet;

  /// No description provided for @profileSetupAvatarEmpty.
  ///
  /// In es, this message translates to:
  /// **'Muestra tu mejor cara de pescador'**
  String get profileSetupAvatarEmpty;

  /// No description provided for @profileSetupAvatarTap.
  ///
  /// In es, this message translates to:
  /// **'Toca para elegir'**
  String get profileSetupAvatarTap;

  /// No description provided for @profileSetupAvatarGallery.
  ///
  /// In es, this message translates to:
  /// **'Galería'**
  String get profileSetupAvatarGallery;

  /// No description provided for @profileSetupAvatarCamera.
  ///
  /// In es, this message translates to:
  /// **'Cámara'**
  String get profileSetupAvatarCamera;

  /// No description provided for @profileSetupAvatarRemove.
  ///
  /// In es, this message translates to:
  /// **'Eliminar foto'**
  String get profileSetupAvatarRemove;

  /// No description provided for @profileSetupAvatarSkip.
  ///
  /// In es, this message translates to:
  /// **'Omitir este paso'**
  String get profileSetupAvatarSkip;

  /// No description provided for @profileSetupSelectPhoto.
  ///
  /// In es, this message translates to:
  /// **'Seleccionar foto'**
  String get profileSetupSelectPhoto;

  /// No description provided for @profileSetupLocation.
  ///
  /// In es, this message translates to:
  /// **'Tu ubicación'**
  String get profileSetupLocation;

  /// No description provided for @profileSetupLocationSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Ayuda a otros pescadores cercanos a encontrarte'**
  String get profileSetupLocationSubtitle;

  /// No description provided for @profileSetupDetectingLocation.
  ///
  /// In es, this message translates to:
  /// **'Detectando...'**
  String get profileSetupDetectingLocation;

  /// No description provided for @profileSetupDetectLocation.
  ///
  /// In es, this message translates to:
  /// **'Detectar mi ubicación automáticamente'**
  String get profileSetupDetectLocation;

  /// No description provided for @profileSetupCityLabel.
  ///
  /// In es, this message translates to:
  /// **'Ciudad o región'**
  String get profileSetupCityLabel;

  /// No description provided for @profileSetupCityHint.
  ///
  /// In es, this message translates to:
  /// **'ej: Cancún, México'**
  String get profileSetupCityHint;

  /// No description provided for @profileSetupShareLocation.
  ///
  /// In es, this message translates to:
  /// **'Compartir mi ubicación aproximada con la comunidad'**
  String get profileSetupShareLocation;

  /// No description provided for @profileSetupPermissions.
  ///
  /// In es, this message translates to:
  /// **'Permisos necesarios'**
  String get profileSetupPermissions;

  /// No description provided for @profileSetupPermissionsSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Para brindarte la mejor experiencia, necesitamos algunos permisos'**
  String get profileSetupPermissionsSubtitle;

  /// No description provided for @profileSetupPermCamera.
  ///
  /// In es, this message translates to:
  /// **'Cámara'**
  String get profileSetupPermCamera;

  /// No description provided for @profileSetupPermCameraDesc.
  ///
  /// In es, this message translates to:
  /// **'Para identificar peces en tiempo real'**
  String get profileSetupPermCameraDesc;

  /// No description provided for @profileSetupPermLocation.
  ///
  /// In es, this message translates to:
  /// **'Ubicación'**
  String get profileSetupPermLocation;

  /// No description provided for @profileSetupPermLocationDesc.
  ///
  /// In es, this message translates to:
  /// **'Para registrar avistamientos en el mapa'**
  String get profileSetupPermLocationDesc;

  /// No description provided for @profileSetupPermGallery.
  ///
  /// In es, this message translates to:
  /// **'Fotos / Galería'**
  String get profileSetupPermGallery;

  /// No description provided for @profileSetupPermGalleryDesc.
  ///
  /// In es, this message translates to:
  /// **'Para tu foto de perfil y galería de peces'**
  String get profileSetupPermGalleryDesc;

  /// No description provided for @profileSetupPermissionsGranted.
  ///
  /// In es, this message translates to:
  /// **'Permisos concedidos'**
  String get profileSetupPermissionsGranted;

  /// No description provided for @profileSetupGrantPermissions.
  ///
  /// In es, this message translates to:
  /// **'Conceder permisos'**
  String get profileSetupGrantPermissions;

  /// No description provided for @profileSetupSkipForNow.
  ///
  /// In es, this message translates to:
  /// **'Omitir por ahora'**
  String get profileSetupSkipForNow;

  /// No description provided for @profileSetupDoneTitle.
  ///
  /// In es, this message translates to:
  /// **'¡Todo listo!'**
  String get profileSetupDoneTitle;

  /// No description provided for @profileSetupDoneSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Tu perfil está configurado.\nEs hora de explorar el mundo acuático.'**
  String get profileSetupDoneSubtitle;

  /// No description provided for @profileSetupStartButton.
  ///
  /// In es, this message translates to:
  /// **'EMPEZAR A PESCAR!'**
  String get profileSetupStartButton;

  /// No description provided for @profileSetupViewProfile.
  ///
  /// In es, this message translates to:
  /// **'Ver mi perfil'**
  String get profileSetupViewProfile;

  /// No description provided for @mapTitle.
  ///
  /// In es, this message translates to:
  /// **'MAPA DE PESCA'**
  String get mapTitle;

  /// No description provided for @mapSpots.
  ///
  /// In es, this message translates to:
  /// **'Spots'**
  String get mapSpots;

  /// No description provided for @mapActivateLocation.
  ///
  /// In es, this message translates to:
  /// **'Activar ubicación para ver spots cercanos'**
  String get mapActivateLocation;

  /// No description provided for @mapGettingLocation.
  ///
  /// In es, this message translates to:
  /// **'Obteniendo ubicación...'**
  String get mapGettingLocation;

  /// No description provided for @mapGpsError.
  ///
  /// In es, this message translates to:
  /// **'Error GPS: {error}'**
  String mapGpsError(String error);

  /// No description provided for @mapAnonymousTitle.
  ///
  /// In es, this message translates to:
  /// **'Pez registrado anteriormente'**
  String get mapAnonymousTitle;

  /// No description provided for @mapAnonymousDesc.
  ///
  /// In es, this message translates to:
  /// **'Este pez ({species}) ya fue registrado por otro explorador en esta zona. La ubicación exacta no está disponible para proteger la privacidad de otros usuarios.'**
  String mapAnonymousDesc(String species);

  /// No description provided for @mapDataProtected.
  ///
  /// In es, this message translates to:
  /// **'Datos protegidos'**
  String get mapDataProtected;

  /// No description provided for @mapFishDate.
  ///
  /// In es, this message translates to:
  /// **'Fecha'**
  String get mapFishDate;

  /// No description provided for @mapFishId.
  ///
  /// In es, this message translates to:
  /// **'Fish ID'**
  String get mapFishId;

  /// No description provided for @mapCoordinates.
  ///
  /// In es, this message translates to:
  /// **'Coordenadas'**
  String get mapCoordinates;

  /// No description provided for @spotWaterRiver.
  ///
  /// In es, this message translates to:
  /// **'Río'**
  String get spotWaterRiver;

  /// No description provided for @spotWaterLake.
  ///
  /// In es, this message translates to:
  /// **'Lago'**
  String get spotWaterLake;

  /// No description provided for @spotWaterSea.
  ///
  /// In es, this message translates to:
  /// **'Mar'**
  String get spotWaterSea;

  /// No description provided for @spotWaterReservoir.
  ///
  /// In es, this message translates to:
  /// **'Embalse'**
  String get spotWaterReservoir;

  /// No description provided for @spotRareFish.
  ///
  /// In es, this message translates to:
  /// **'Peces raros'**
  String get spotRareFish;

  /// No description provided for @spotCaptures.
  ///
  /// In es, this message translates to:
  /// **'Capturas'**
  String get spotCaptures;

  /// No description provided for @spotSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especies'**
  String get spotSpecies;

  /// No description provided for @spotLastCatch.
  ///
  /// In es, this message translates to:
  /// **'Última captura'**
  String get spotLastCatch;

  /// No description provided for @spotCommonSpecies.
  ///
  /// In es, this message translates to:
  /// **'ESPECIES COMUNES'**
  String get spotCommonSpecies;

  /// No description provided for @spotFishHere.
  ///
  /// In es, this message translates to:
  /// **'PESCAR AQUÍ'**
  String get spotFishHere;

  /// No description provided for @spotToday.
  ///
  /// In es, this message translates to:
  /// **'Hoy'**
  String get spotToday;

  /// No description provided for @spotYesterday.
  ///
  /// In es, this message translates to:
  /// **'Ayer'**
  String get spotYesterday;

  /// No description provided for @spotDaysAgo.
  ///
  /// In es, this message translates to:
  /// **'Hace {days}d'**
  String spotDaysAgo(int days);

  /// No description provided for @quickSpotTitle.
  ///
  /// In es, this message translates to:
  /// **'MARCAR SPOT'**
  String get quickSpotTitle;

  /// No description provided for @quickSpotSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Guarda este lugar de pesca en el mapa'**
  String get quickSpotSubtitle;

  /// No description provided for @quickSpotNameLabel.
  ///
  /// In es, this message translates to:
  /// **'Nombre del spot'**
  String get quickSpotNameLabel;

  /// No description provided for @quickSpotNameHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: Río Lozoya - Poza norte'**
  String get quickSpotNameHint;

  /// No description provided for @quickSpotWaterType.
  ///
  /// In es, this message translates to:
  /// **'Tipo de agua'**
  String get quickSpotWaterType;

  /// No description provided for @quickSpotDescription.
  ///
  /// In es, this message translates to:
  /// **'Descripción (opcional)'**
  String get quickSpotDescription;

  /// No description provided for @quickSpotDescriptionHint.
  ///
  /// In es, this message translates to:
  /// **'Notas sobre este spot...'**
  String get quickSpotDescriptionHint;

  /// No description provided for @quickSpotLocationCurrent.
  ///
  /// In es, this message translates to:
  /// **'Ubicación GPS actual'**
  String get quickSpotLocationCurrent;

  /// No description provided for @quickSpotLocationNone.
  ///
  /// In es, this message translates to:
  /// **'Sin señal GPS'**
  String get quickSpotLocationNone;

  /// No description provided for @quickSpotLocationGetting.
  ///
  /// In es, this message translates to:
  /// **'Obteniendo GPS...'**
  String get quickSpotLocationGetting;

  /// No description provided for @quickSpotLocationError.
  ///
  /// In es, this message translates to:
  /// **'Error al obtener ubicación'**
  String get quickSpotLocationError;

  /// No description provided for @quickSpotSaving.
  ///
  /// In es, this message translates to:
  /// **'Guardando...'**
  String get quickSpotSaving;

  /// No description provided for @quickSpotSaveButton.
  ///
  /// In es, this message translates to:
  /// **'GUARDAR SPOT'**
  String get quickSpotSaveButton;

  /// No description provided for @quickSpotSavedDemo.
  ///
  /// In es, this message translates to:
  /// **'¡Spot \"{name}\" marcado (modo demo)!\nRegistra una cuenta para guardarlo permanentemente.'**
  String quickSpotSavedDemo(String name);

  /// No description provided for @quickSpotSaved.
  ///
  /// In es, this message translates to:
  /// **'¡Spot \"{name}\" guardado en el mapa!'**
  String quickSpotSaved(String name);

  /// No description provided for @quickSpotErrorGps.
  ///
  /// In es, this message translates to:
  /// **'No se pudo obtener tu ubicación GPS.\nActiva el GPS e inténtalo de nuevo.'**
  String get quickSpotErrorGps;

  /// No description provided for @quickSpotErrorName.
  ///
  /// In es, this message translates to:
  /// **'Ponle un nombre al spot para poder guardarlo.'**
  String get quickSpotErrorName;

  /// No description provided for @quickSpotErrorSave.
  ///
  /// In es, this message translates to:
  /// **'Error al guardar el spot.\n{error}'**
  String quickSpotErrorSave(String error);

  /// No description provided for @quickSpotWaterRiver.
  ///
  /// In es, this message translates to:
  /// **'Río'**
  String get quickSpotWaterRiver;

  /// No description provided for @quickSpotWaterReservoir.
  ///
  /// In es, this message translates to:
  /// **'Embalse'**
  String get quickSpotWaterReservoir;

  /// No description provided for @quickSpotWaterLake.
  ///
  /// In es, this message translates to:
  /// **'Lago'**
  String get quickSpotWaterLake;

  /// No description provided for @quickSpotWaterSea.
  ///
  /// In es, this message translates to:
  /// **'Mar'**
  String get quickSpotWaterSea;

  /// No description provided for @collectionTitle.
  ///
  /// In es, this message translates to:
  /// **'MI COLECCIÓN'**
  String get collectionTitle;

  /// No description provided for @collectionDiscovered.
  ///
  /// In es, this message translates to:
  /// **'{count} especies descubiertas'**
  String collectionDiscovered(int count);

  /// No description provided for @collectionFilterAll.
  ///
  /// In es, this message translates to:
  /// **'Todos'**
  String get collectionFilterAll;

  /// No description provided for @collectionFilterCommon.
  ///
  /// In es, this message translates to:
  /// **'Comunes'**
  String get collectionFilterCommon;

  /// No description provided for @collectionFilterUncommon.
  ///
  /// In es, this message translates to:
  /// **'Poco comunes'**
  String get collectionFilterUncommon;

  /// No description provided for @collectionFilterRare.
  ///
  /// In es, this message translates to:
  /// **'Raros'**
  String get collectionFilterRare;

  /// No description provided for @collectionFilterLegendary.
  ///
  /// In es, this message translates to:
  /// **'Legendarios'**
  String get collectionFilterLegendary;

  /// No description provided for @collectionUndiscovered.
  ///
  /// In es, this message translates to:
  /// **'No descubierto'**
  String get collectionUndiscovered;

  /// No description provided for @collectionTimesSpotted.
  ///
  /// In es, this message translates to:
  /// **'{count}x'**
  String collectionTimesSpotted(int count);

  /// No description provided for @collectionSizeLabel.
  ///
  /// In es, this message translates to:
  /// **'Tamaño'**
  String get collectionSizeLabel;

  /// No description provided for @collectionSightingsLabel.
  ///
  /// In es, this message translates to:
  /// **'Avistamientos'**
  String get collectionSightingsLabel;

  /// No description provided for @collectionRarityLabel.
  ///
  /// In es, this message translates to:
  /// **'Rareza'**
  String get collectionRarityLabel;

  /// No description provided for @collectionHistoryTitle.
  ///
  /// In es, this message translates to:
  /// **'HISTORIAL DE AVISTAMIENTOS'**
  String get collectionHistoryTitle;

  /// No description provided for @collectionFirstSighting.
  ///
  /// In es, this message translates to:
  /// **'Primer avistamiento'**
  String get collectionFirstSighting;

  /// No description provided for @rankingTitle.
  ///
  /// In es, this message translates to:
  /// **'RANKING'**
  String get rankingTitle;

  /// No description provided for @rankingTabXp.
  ///
  /// In es, this message translates to:
  /// **'XP TOTAL'**
  String get rankingTabXp;

  /// No description provided for @rankingTabSpecies.
  ///
  /// In es, this message translates to:
  /// **'ESPECIES'**
  String get rankingTabSpecies;

  /// No description provided for @rankingTabBiggest.
  ///
  /// In es, this message translates to:
  /// **'PEZ MAYOR'**
  String get rankingTabBiggest;

  /// No description provided for @rankingPeriodGlobal.
  ///
  /// In es, this message translates to:
  /// **'Global'**
  String get rankingPeriodGlobal;

  /// No description provided for @rankingPeriodWeekly.
  ///
  /// In es, this message translates to:
  /// **'Semanal'**
  String get rankingPeriodWeekly;

  /// No description provided for @rankingPeriodMonthly.
  ///
  /// In es, this message translates to:
  /// **'Mensual'**
  String get rankingPeriodMonthly;

  /// No description provided for @rankingYourPosition.
  ///
  /// In es, this message translates to:
  /// **'Tu posición:'**
  String get rankingYourPosition;

  /// No description provided for @rankingLoginToSee.
  ///
  /// In es, this message translates to:
  /// **'Inicia sesión para ver tu posición'**
  String get rankingLoginToSee;

  /// No description provided for @rankingEmpty.
  ///
  /// In es, this message translates to:
  /// **'Sé el primero en el ranking'**
  String get rankingEmpty;

  /// No description provided for @rankingEmptySubtitle.
  ///
  /// In es, this message translates to:
  /// **'¡Identifica tu primer pez!'**
  String get rankingEmptySubtitle;

  /// No description provided for @rankingNoConnection.
  ///
  /// In es, this message translates to:
  /// **'Sin conexión'**
  String get rankingNoConnection;

  /// No description provided for @rankingYouBadge.
  ///
  /// In es, this message translates to:
  /// **'TÚ'**
  String get rankingYouBadge;

  /// No description provided for @rankingLevel.
  ///
  /// In es, this message translates to:
  /// **'Nv. {level}'**
  String rankingLevel(int level);

  /// No description provided for @rankingValueXp.
  ///
  /// In es, this message translates to:
  /// **'{value} XP'**
  String rankingValueXp(int value);

  /// No description provided for @rankingValueSpecies.
  ///
  /// In es, this message translates to:
  /// **'{value} spp'**
  String rankingValueSpecies(int value);

  /// No description provided for @rankingValueBiggest.
  ///
  /// In es, this message translates to:
  /// **'{value} cm'**
  String rankingValueBiggest(String value);

  /// No description provided for @cameraLoading.
  ///
  /// In es, this message translates to:
  /// **'Iniciando cámara...'**
  String get cameraLoading;

  /// No description provided for @cameraNoCameras.
  ///
  /// In es, this message translates to:
  /// **'No se encontraron cámaras disponibles'**
  String get cameraNoCameras;

  /// No description provided for @cameraInitError.
  ///
  /// In es, this message translates to:
  /// **'Error al inicializar la cámara: {error}'**
  String cameraInitError(String error);

  /// No description provided for @cameraRecordError.
  ///
  /// In es, this message translates to:
  /// **'Error al iniciar grabación'**
  String get cameraRecordError;

  /// No description provided for @cameraStopError.
  ///
  /// In es, this message translates to:
  /// **'Error al detener grabación'**
  String get cameraStopError;

  /// No description provided for @cameraRetry.
  ///
  /// In es, this message translates to:
  /// **'Reintentar'**
  String get cameraRetry;

  /// No description provided for @videoPreviewTitle.
  ///
  /// In es, this message translates to:
  /// **'¿Se ve bien tu captura?'**
  String get videoPreviewTitle;

  /// No description provided for @videoPreviewSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Asegúrate de que el pez se vea claramente'**
  String get videoPreviewSubtitle;

  /// No description provided for @videoPreviewRetake.
  ///
  /// In es, this message translates to:
  /// **'REGRABAR'**
  String get videoPreviewRetake;

  /// No description provided for @videoPreviewIdentify.
  ///
  /// In es, this message translates to:
  /// **'IDENTIFICAR'**
  String get videoPreviewIdentify;

  /// No description provided for @identifyingProcessing.
  ///
  /// In es, this message translates to:
  /// **'Procesando video...'**
  String get identifyingProcessing;

  /// No description provided for @identifyingExtractingFrames.
  ///
  /// In es, this message translates to:
  /// **'Extrayendo frames...'**
  String get identifyingExtractingFrames;

  /// No description provided for @identifyingAnalyzing.
  ///
  /// In es, this message translates to:
  /// **'Analizando con IA...'**
  String get identifyingAnalyzing;

  /// No description provided for @identifyingSuccess.
  ///
  /// In es, this message translates to:
  /// **'¡Pez identificado!'**
  String get identifyingSuccess;

  /// No description provided for @identifyingError.
  ///
  /// In es, this message translates to:
  /// **'Error'**
  String get identifyingError;

  /// No description provided for @identifyingUnexpectedError.
  ///
  /// In es, this message translates to:
  /// **'Error inesperado al identificar'**
  String get identifyingUnexpectedError;

  /// No description provided for @identifyingRetry.
  ///
  /// In es, this message translates to:
  /// **'Volver a intentar'**
  String get identifyingRetry;

  /// No description provided for @resultNewDiscovery.
  ///
  /// In es, this message translates to:
  /// **'¡NUEVO DESCUBRIMIENTO!'**
  String get resultNewDiscovery;

  /// No description provided for @resultReunion.
  ///
  /// In es, this message translates to:
  /// **'¡REENCUENTRO!'**
  String get resultReunion;

  /// No description provided for @resultDetails.
  ///
  /// In es, this message translates to:
  /// **'Detalles del avistamiento'**
  String get resultDetails;

  /// No description provided for @resultFishId.
  ///
  /// In es, this message translates to:
  /// **'ID del pez'**
  String get resultFishId;

  /// No description provided for @resultSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especie'**
  String get resultSpecies;

  /// No description provided for @resultEstimatedSize.
  ///
  /// In es, this message translates to:
  /// **'Tamaño estimado'**
  String get resultEstimatedSize;

  /// No description provided for @resultAiConfidence.
  ///
  /// In es, this message translates to:
  /// **'Confianza IA'**
  String get resultAiConfidence;

  /// No description provided for @resultViewCollection.
  ///
  /// In es, this message translates to:
  /// **'VER EN MI COLECCIÓN'**
  String get resultViewCollection;

  /// No description provided for @resultBackToMap.
  ///
  /// In es, this message translates to:
  /// **'VOLVER AL MAPA'**
  String get resultBackToMap;

  /// No description provided for @fishCardNew.
  ///
  /// In es, this message translates to:
  /// **'NUEVO'**
  String get fishCardNew;

  /// No description provided for @fishCardRarity.
  ///
  /// In es, this message translates to:
  /// **'RAREZA'**
  String get fishCardRarity;

  /// No description provided for @fishCardAiConfidence.
  ///
  /// In es, this message translates to:
  /// **'% IA'**
  String get fishCardAiConfidence;

  /// No description provided for @reunionHistory.
  ///
  /// In es, this message translates to:
  /// **'Historial del pez'**
  String get reunionHistory;

  /// No description provided for @reunionTimesSeen.
  ///
  /// In es, this message translates to:
  /// **'{count}x visto'**
  String reunionTimesSeen(int count);

  /// No description provided for @reunionFirstSighting.
  ///
  /// In es, this message translates to:
  /// **'Primer avistamiento'**
  String get reunionFirstSighting;

  /// No description provided for @reunionFirstLocation.
  ///
  /// In es, this message translates to:
  /// **'Primera ubicación'**
  String get reunionFirstLocation;

  /// No description provided for @reunionLastSighting.
  ///
  /// In es, this message translates to:
  /// **'Último avistamiento'**
  String get reunionLastSighting;

  /// No description provided for @reunionUnknown.
  ///
  /// In es, this message translates to:
  /// **'Desconocida'**
  String get reunionUnknown;

  /// No description provided for @reunionGrown.
  ///
  /// In es, this message translates to:
  /// **'¡Ha crecido!'**
  String get reunionGrown;

  /// No description provided for @reunionGrowthLabel.
  ///
  /// In es, this message translates to:
  /// **'cm'**
  String get reunionGrowthLabel;

  /// No description provided for @captureFormTitle.
  ///
  /// In es, this message translates to:
  /// **'Identificación Manual'**
  String get captureFormTitle;

  /// No description provided for @captureFormTitleComplete.
  ///
  /// In es, this message translates to:
  /// **'Completar Captura'**
  String get captureFormTitleComplete;

  /// No description provided for @captureFormTitleRegister.
  ///
  /// In es, this message translates to:
  /// **'Registrar Captura'**
  String get captureFormTitleRegister;

  /// No description provided for @captureFormLowConfidence.
  ///
  /// In es, this message translates to:
  /// **'Identificación no concluyente'**
  String get captureFormLowConfidence;

  /// No description provided for @captureFormLowConfidenceDesc.
  ///
  /// In es, this message translates to:
  /// **'La IA no pudo identificar el pez con suficiente confianza ({percent}%). Por favor, completa la información manualmente.'**
  String captureFormLowConfidenceDesc(int percent);

  /// No description provided for @captureFormAiBanner.
  ///
  /// In es, this message translates to:
  /// **'IA: {species}'**
  String captureFormAiBanner(String species);

  /// No description provided for @captureFormAiBannerDesc.
  ///
  /// In es, this message translates to:
  /// **'Confianza: {percent}% - Puedes agregar datos adicionales abajo.'**
  String captureFormAiBannerDesc(int percent);

  /// No description provided for @captureFormSaveButton.
  ///
  /// In es, this message translates to:
  /// **'GUARDAR CAPTURA'**
  String get captureFormSaveButton;

  /// No description provided for @captureFormSaved.
  ///
  /// In es, this message translates to:
  /// **'Captura guardada exitosamente!'**
  String get captureFormSaved;

  /// No description provided for @captureFormSelectCondition.
  ///
  /// In es, this message translates to:
  /// **'Selecciona la condición del pez'**
  String get captureFormSelectCondition;

  /// No description provided for @captureFieldSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especie / Descripción visual *'**
  String get captureFieldSpecies;

  /// No description provided for @captureFieldSpeciesHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: Trucha Arcoíris, pez plateado con manchas...'**
  String get captureFieldSpeciesHint;

  /// No description provided for @captureFieldSpeciesRequired.
  ///
  /// In es, this message translates to:
  /// **'Campo obligatorio'**
  String get captureFieldSpeciesRequired;

  /// No description provided for @captureFieldLength.
  ///
  /// In es, this message translates to:
  /// **'Longitud estimada (cm) *'**
  String get captureFieldLength;

  /// No description provided for @captureFieldLengthHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: 35.5'**
  String get captureFieldLengthHint;

  /// No description provided for @captureFieldLengthRequired.
  ///
  /// In es, this message translates to:
  /// **'Campo obligatorio'**
  String get captureFieldLengthRequired;

  /// No description provided for @captureFieldLengthInvalid.
  ///
  /// In es, this message translates to:
  /// **'Ingresa un número válido'**
  String get captureFieldLengthInvalid;

  /// No description provided for @captureFieldWeight.
  ///
  /// In es, this message translates to:
  /// **'Peso estimado (kg)'**
  String get captureFieldWeight;

  /// No description provided for @captureFieldWeightHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: 2.3'**
  String get captureFieldWeightHint;

  /// No description provided for @captureFieldColor.
  ///
  /// In es, this message translates to:
  /// **'Color predominante'**
  String get captureFieldColor;

  /// No description provided for @captureFieldColorHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: Plateado con reflejos azules'**
  String get captureFieldColorHint;

  /// No description provided for @captureFieldCondition.
  ///
  /// In es, this message translates to:
  /// **'Condición al momento de captura *'**
  String get captureFieldCondition;

  /// No description provided for @captureConditionAlive.
  ///
  /// In es, this message translates to:
  /// **'Vivo'**
  String get captureConditionAlive;

  /// No description provided for @captureConditionReleased.
  ///
  /// In es, this message translates to:
  /// **'Liberado'**
  String get captureConditionReleased;

  /// No description provided for @captureConditionDead.
  ///
  /// In es, this message translates to:
  /// **'Muerto'**
  String get captureConditionDead;

  /// No description provided for @captureFieldFeatures.
  ///
  /// In es, this message translates to:
  /// **'Características físicas'**
  String get captureFieldFeatures;

  /// No description provided for @captureFieldFeaturesHint.
  ///
  /// In es, this message translates to:
  /// **'Ej: Aleta dorsal prominente, cola bifurcada...'**
  String get captureFieldFeaturesHint;

  /// No description provided for @captureFieldNotes.
  ///
  /// In es, this message translates to:
  /// **'Notas adicionales'**
  String get captureFieldNotes;

  /// No description provided for @captureFieldNotesHint.
  ///
  /// In es, this message translates to:
  /// **'Cualquier observación adicional...'**
  String get captureFieldNotesHint;

  /// No description provided for @captureFieldGps.
  ///
  /// In es, this message translates to:
  /// **'Ubicación GPS'**
  String get captureFieldGps;

  /// No description provided for @captureFieldLatitude.
  ///
  /// In es, this message translates to:
  /// **'Latitud'**
  String get captureFieldLatitude;

  /// No description provided for @captureFieldLongitude.
  ///
  /// In es, this message translates to:
  /// **'Longitud'**
  String get captureFieldLongitude;

  /// No description provided for @galleryTitle.
  ///
  /// In es, this message translates to:
  /// **'Abriendo galería'**
  String get galleryTitle;

  /// No description provided for @gallerySubtitle.
  ///
  /// In es, this message translates to:
  /// **'Selecciona un video de tu pez\npara identificarlo con IA'**
  String get gallerySubtitle;

  /// No description provided for @galleryCancel.
  ///
  /// In es, this message translates to:
  /// **'Cancelar'**
  String get galleryCancel;

  /// No description provided for @galleryError.
  ///
  /// In es, this message translates to:
  /// **'No se pudo acceder a la galería: {error}'**
  String galleryError(String error);

  /// No description provided for @achievementsCategory.
  ///
  /// In es, this message translates to:
  /// **'Logros'**
  String get achievementsCategory;

  /// No description provided for @achievementsDiscovery.
  ///
  /// In es, this message translates to:
  /// **'Descubrimiento'**
  String get achievementsDiscovery;

  /// No description provided for @achievementsCollection.
  ///
  /// In es, this message translates to:
  /// **'Colección'**
  String get achievementsCollection;

  /// No description provided for @achievementsSocial.
  ///
  /// In es, this message translates to:
  /// **'Social'**
  String get achievementsSocial;

  /// No description provided for @achievementsExploration.
  ///
  /// In es, this message translates to:
  /// **'Exploración'**
  String get achievementsExploration;

  /// No description provided for @achievementsUnlocked.
  ///
  /// In es, this message translates to:
  /// **'¡Logro desbloqueado!'**
  String get achievementsUnlocked;

  /// No description provided for @achievementsBronze.
  ///
  /// In es, this message translates to:
  /// **'Bronce'**
  String get achievementsBronze;

  /// No description provided for @achievementsSilver.
  ///
  /// In es, this message translates to:
  /// **'Plata'**
  String get achievementsSilver;

  /// No description provided for @achievementsGold.
  ///
  /// In es, this message translates to:
  /// **'Oro'**
  String get achievementsGold;

  /// No description provided for @achievementsPlatinum.
  ///
  /// In es, this message translates to:
  /// **'Platino'**
  String get achievementsPlatinum;

  /// No description provided for @achievementsProgressLabel.
  ///
  /// In es, this message translates to:
  /// **'{current}/{target}'**
  String achievementsProgressLabel(int current, int target);

  /// No description provided for @adminPanelTitle.
  ///
  /// In es, this message translates to:
  /// **'PANEL DE ADMIN'**
  String get adminPanelTitle;

  /// No description provided for @adminPendingRequests.
  ///
  /// In es, this message translates to:
  /// **'Solicitudes Pendientes'**
  String get adminPendingRequests;

  /// No description provided for @adminStats.
  ///
  /// In es, this message translates to:
  /// **'Estadísticas'**
  String get adminStats;

  /// No description provided for @adminNoPending.
  ///
  /// In es, this message translates to:
  /// **'No hay solicitudes pendientes'**
  String get adminNoPending;

  /// No description provided for @adminApprove.
  ///
  /// In es, this message translates to:
  /// **'Aprobar'**
  String get adminApprove;

  /// No description provided for @adminReject.
  ///
  /// In es, this message translates to:
  /// **'Rechazar'**
  String get adminReject;

  /// No description provided for @adminApproved.
  ///
  /// In es, this message translates to:
  /// **'Investigador aprobado correctamente'**
  String get adminApproved;

  /// No description provided for @adminRejected.
  ///
  /// In es, this message translates to:
  /// **'Solicitud rechazada'**
  String get adminRejected;

  /// No description provided for @adminErrorLoading.
  ///
  /// In es, this message translates to:
  /// **'Error al cargar solicitudes: {error}'**
  String adminErrorLoading(String error);

  /// No description provided for @adminStatsPending.
  ///
  /// In es, this message translates to:
  /// **'Pendientes'**
  String get adminStatsPending;

  /// No description provided for @adminStatsCapturesDay.
  ///
  /// In es, this message translates to:
  /// **'Capturas Hoy'**
  String get adminStatsCapturesDay;

  /// No description provided for @adminStatsUsers.
  ///
  /// In es, this message translates to:
  /// **'Usuarios'**
  String get adminStatsUsers;

  /// No description provided for @adminStatsSpecies.
  ///
  /// In es, this message translates to:
  /// **'Especies'**
  String get adminStatsSpecies;

  /// No description provided for @demoModeBanner.
  ///
  /// In es, this message translates to:
  /// **'Modo demo activo. Crea una cuenta para guardar tu progreso.'**
  String get demoModeBanner;

  /// No description provided for @demoModeCreateAccount.
  ///
  /// In es, this message translates to:
  /// **'Crear cuenta'**
  String get demoModeCreateAccount;

  /// No description provided for @rarityCommon.
  ///
  /// In es, this message translates to:
  /// **'Común'**
  String get rarityCommon;

  /// No description provided for @rarityUncommon.
  ///
  /// In es, this message translates to:
  /// **'Poco común'**
  String get rarityUncommon;

  /// No description provided for @rarityRare.
  ///
  /// In es, this message translates to:
  /// **'Raro'**
  String get rarityRare;

  /// No description provided for @rarityLegendary.
  ///
  /// In es, this message translates to:
  /// **'Legendario'**
  String get rarityLegendary;

  /// No description provided for @conditionAlive.
  ///
  /// In es, this message translates to:
  /// **'Vivo'**
  String get conditionAlive;

  /// No description provided for @conditionReleased.
  ///
  /// In es, this message translates to:
  /// **'Liberado'**
  String get conditionReleased;

  /// No description provided for @conditionDead.
  ///
  /// In es, this message translates to:
  /// **'Muerto'**
  String get conditionDead;

  /// No description provided for @cameraGuideSkip.
  ///
  /// In es, this message translates to:
  /// **'Omitir'**
  String get cameraGuideSkip;

  /// No description provided for @cameraGuideNext.
  ///
  /// In es, this message translates to:
  /// **'Siguiente'**
  String get cameraGuideNext;

  /// No description provided for @cameraGuideStart.
  ///
  /// In es, this message translates to:
  /// **'Iniciar cámara'**
  String get cameraGuideStart;

  /// No description provided for @cameraGuideOrientationTitle.
  ///
  /// In es, this message translates to:
  /// **'Orientación correcta'**
  String get cameraGuideOrientationTitle;

  /// No description provided for @cameraGuideOrientationDesc.
  ///
  /// In es, this message translates to:
  /// **'Coloca siempre el pez con la CABEZA apuntando hacia la DERECHA y la COLA apuntando hacia la IZQUIERDA. Esto asegura una identificación consistente.'**
  String get cameraGuideOrientationDesc;

  /// No description provided for @cameraGuideOrientationTip.
  ///
  /// In es, this message translates to:
  /// **'Misma orientación = mejor precisión'**
  String get cameraGuideOrientationTip;

  /// No description provided for @cameraGuidePositionTitle.
  ///
  /// In es, this message translates to:
  /// **'Cuerpo completo visible'**
  String get cameraGuidePositionTitle;

  /// No description provided for @cameraGuidePositionDesc.
  ///
  /// In es, this message translates to:
  /// **'Asegúrate de que todo el cuerpo del pez sea visible en el encuadre, desde la boca hasta la cola. Deja pequeños márgenes en todos los lados. Distancia: 30-50 cm.'**
  String get cameraGuidePositionDesc;

  /// No description provided for @cameraGuidePositionTip.
  ///
  /// In es, this message translates to:
  /// **'Cuerpo completo = patrones analizados correctamente'**
  String get cameraGuidePositionTip;

  /// No description provided for @cameraGuideTechniqueTitle.
  ///
  /// In es, this message translates to:
  /// **'Consejos de grabación'**
  String get cameraGuideTechniqueTitle;

  /// No description provided for @cameraGuideTechniqueDesc.
  ///
  /// In es, this message translates to:
  /// **'Coloca el pez sobre una superficie plana (una alfombrilla de medición es ideal). Minimiza la cobertura con las manos. Un video estable de 5-10 segundos es perfecto.'**
  String get cameraGuideTechniqueDesc;

  /// No description provided for @cameraGuideDoFlat.
  ///
  /// In es, this message translates to:
  /// **'Colocar el pez plano sobre la alfombrilla'**
  String get cameraGuideDoFlat;

  /// No description provided for @cameraGuideDoLight.
  ///
  /// In es, this message translates to:
  /// **'Usar buena luz natural'**
  String get cameraGuideDoLight;

  /// No description provided for @cameraGuideDoSteady.
  ///
  /// In es, this message translates to:
  /// **'Grabar 5-10 segundos de forma estable'**
  String get cameraGuideDoSteady;

  /// No description provided for @cameraGuideDontHands.
  ///
  /// In es, this message translates to:
  /// **'Sostener el pez cubriendo el cuerpo'**
  String get cameraGuideDontHands;

  /// No description provided for @cameraGuideDontDark.
  ///
  /// In es, this message translates to:
  /// **'Grabar en condiciones muy oscuras'**
  String get cameraGuideDontDark;

  /// No description provided for @cameraGuideReadyTitle.
  ///
  /// In es, this message translates to:
  /// **'¡Listo para capturar!'**
  String get cameraGuideReadyTitle;

  /// No description provided for @cameraGuideReadyDesc.
  ///
  /// In es, this message translates to:
  /// **'La cámara mostrará una guía con la silueta de un pez. Alinea el pez con el contorno y presiona el botón de grabar. ¡La IA identificará tu captura!'**
  String get cameraGuideReadyDesc;

  /// No description provided for @cameraGuideReadySettings.
  ///
  /// In es, this message translates to:
  /// **'Siempre puedes acceder a esta guía desde los ajustes de la cámara.'**
  String get cameraGuideReadySettings;

  /// No description provided for @arAlignSilhouette.
  ///
  /// In es, this message translates to:
  /// **'Alinea el pez con la silueta'**
  String get arAlignSilhouette;

  /// No description provided for @arHeadLeftBodyVisible.
  ///
  /// In es, this message translates to:
  /// **'Cabeza hacia la DERECHA • Cuerpo completo visible'**
  String get arHeadLeftBodyVisible;

  /// No description provided for @arHeadLabel.
  ///
  /// In es, this message translates to:
  /// **'CABEZA'**
  String get arHeadLabel;

  /// No description provided for @arTailLabel.
  ///
  /// In es, this message translates to:
  /// **'COLA'**
  String get arTailLabel;

  /// No description provided for @arHorizontal.
  ///
  /// In es, this message translates to:
  /// **'Horizontal'**
  String get arHorizontal;

  /// No description provided for @arDistance.
  ///
  /// In es, this message translates to:
  /// **'30-50cm'**
  String get arDistance;

  /// No description provided for @arGoodLight.
  ///
  /// In es, this message translates to:
  /// **'Buena luz'**
  String get arGoodLight;

  /// No description provided for @recordingStateRecording.
  ///
  /// In es, this message translates to:
  /// **'Grabando... Mantén estable'**
  String get recordingStateRecording;

  /// No description provided for @recordingStatePressToRecord.
  ///
  /// In es, this message translates to:
  /// **'Pulsa para grabar ({seconds}s máx)'**
  String recordingStatePressToRecord(int seconds);

  /// No description provided for @sheetOwnCapture.
  ///
  /// In es, this message translates to:
  /// **'MI CAPTURA'**
  String get sheetOwnCapture;

  /// No description provided for @sheetFieldDate.
  ///
  /// In es, this message translates to:
  /// **'Fecha'**
  String get sheetFieldDate;

  /// No description provided for @sheetFieldTime.
  ///
  /// In es, this message translates to:
  /// **'Hora'**
  String get sheetFieldTime;

  /// No description provided for @sheetFieldFishId.
  ///
  /// In es, this message translates to:
  /// **'Fish ID'**
  String get sheetFieldFishId;

  /// No description provided for @sheetFieldCaptureId.
  ///
  /// In es, this message translates to:
  /// **'Capture ID'**
  String get sheetFieldCaptureId;

  /// No description provided for @sheetFieldUser.
  ///
  /// In es, this message translates to:
  /// **'Usuario'**
  String get sheetFieldUser;

  /// No description provided for @sheetFieldCoordinates.
  ///
  /// In es, this message translates to:
  /// **'Coordenadas exactas'**
  String get sheetFieldCoordinates;

  /// No description provided for @sheetHistoryTitle.
  ///
  /// In es, this message translates to:
  /// **'Historial del pez'**
  String get sheetHistoryTitle;

  /// No description provided for @sheetHistorySubtitle.
  ///
  /// In es, this message translates to:
  /// **'Ver todas las capturas de este pez'**
  String get sheetHistorySubtitle;

  /// No description provided for @timelineSummary.
  ///
  /// In es, this message translates to:
  /// **'{captures} capturas en {locations} ubicaciones'**
  String timelineSummary(int captures, int locations);

  /// No description provided for @timelineLocationZone.
  ///
  /// In es, this message translates to:
  /// **'Zona {label}'**
  String timelineLocationZone(String label);

  /// No description provided for @timelineStatusNew.
  ///
  /// In es, this message translates to:
  /// **'Nuevo'**
  String get timelineStatusNew;

  /// No description provided for @timelineStatusReunion.
  ///
  /// In es, this message translates to:
  /// **'Reencuentro'**
  String get timelineStatusReunion;

  /// No description provided for @timelineEmpty.
  ///
  /// In es, this message translates to:
  /// **'No hay historial disponible para este pez'**
  String get timelineEmpty;

  /// No description provided for @timelineError.
  ///
  /// In es, this message translates to:
  /// **'Error al cargar historial: {error}'**
  String timelineError(Object error);

  /// No description provided for @quickSpotFishingAreaLabel.
  ///
  /// In es, this message translates to:
  /// **'Coto de Pesca (Revír)'**
  String get quickSpotFishingAreaLabel;

  /// No description provided for @quickSpotLoadingAreas.
  ///
  /// In es, this message translates to:
  /// **'Cargando cotos cercanos...'**
  String get quickSpotLoadingAreas;

  /// No description provided for @quickSpotSearchAreaHint.
  ///
  /// In es, this message translates to:
  /// **'Buscar coto por nombre o código...'**
  String get quickSpotSearchAreaHint;

  /// No description provided for @quickSpotNoAreasNearby.
  ///
  /// In es, this message translates to:
  /// **'No se encontraron cotos cercanos. Intenta aumentar el radio.'**
  String get quickSpotNoAreasNearby;

  /// No description provided for @quickSpotNoAreasMatching.
  ///
  /// In es, this message translates to:
  /// **'Sin cotos que coincidan. Intenta otra búsqueda.'**
  String get quickSpotNoAreasMatching;

  /// No description provided for @splashTagline.
  ///
  /// In es, this message translates to:
  /// **'Identifica. Colecciona. Compite.'**
  String get splashTagline;

  /// No description provided for @captureDetailsTitle.
  ///
  /// In es, this message translates to:
  /// **'Detalles de la Captura'**
  String get captureDetailsTitle;

  /// No description provided for @captureDetailsIntro.
  ///
  /// In es, this message translates to:
  /// **'Completa los datos de tu captura para iniciar la identificación asistida por IA.'**
  String get captureDetailsIntro;

  /// No description provided for @captureDetailsSizeLabel.
  ///
  /// In es, this message translates to:
  /// **'Tamaño estimado (cm)'**
  String get captureDetailsSizeLabel;

  /// No description provided for @captureDetailsInvalidNumber.
  ///
  /// In es, this message translates to:
  /// **'Ingresa un número válido'**
  String get captureDetailsInvalidNumber;

  /// No description provided for @captureDetailsSizeGreaterThanZero.
  ///
  /// In es, this message translates to:
  /// **'El tamaño debe ser mayor a 0'**
  String get captureDetailsSizeGreaterThanZero;

  /// No description provided for @captureDetailsWeatherLabel.
  ///
  /// In es, this message translates to:
  /// **'Condiciones climáticas'**
  String get captureDetailsWeatherLabel;

  /// No description provided for @captureDetailsBaitLabel.
  ///
  /// In es, this message translates to:
  /// **'Cebo utilizado'**
  String get captureDetailsBaitLabel;

  /// No description provided for @captureDetailsCustomNameLabel.
  ///
  /// In es, this message translates to:
  /// **'Nombre personalizado (opcional)'**
  String get captureDetailsCustomNameLabel;

  /// No description provided for @captureDetailsNotesLabel.
  ///
  /// In es, this message translates to:
  /// **'Notas o estado del pez'**
  String get captureDetailsNotesLabel;

  /// No description provided for @captureDetailsStartButton.
  ///
  /// In es, this message translates to:
  /// **'Iniciar Identificación'**
  String get captureDetailsStartButton;

  /// No description provided for @captureDetailsSubmittingTitle.
  ///
  /// In es, this message translates to:
  /// **'Subiendo y procesando video...'**
  String get captureDetailsSubmittingTitle;

  /// No description provided for @captureDetailsSubmittingSubtitle.
  ///
  /// In es, this message translates to:
  /// **'Esto puede tomar unos segundos. Por favor no cierres la aplicación.'**
  String get captureDetailsSubmittingSubtitle;

  /// No description provided for @captureDetailsProcessingError.
  ///
  /// In es, this message translates to:
  /// **'Error al procesar: {error}'**
  String captureDetailsProcessingError(String error);

  /// No description provided for @weatherSunny.
  ///
  /// In es, this message translates to:
  /// **'Soleado'**
  String get weatherSunny;

  /// No description provided for @weatherCloudy.
  ///
  /// In es, this message translates to:
  /// **'Nublado'**
  String get weatherCloudy;

  /// No description provided for @weatherRainy.
  ///
  /// In es, this message translates to:
  /// **'Lluvioso'**
  String get weatherRainy;

  /// No description provided for @weatherOvercast.
  ///
  /// In es, this message translates to:
  /// **'Cubierto'**
  String get weatherOvercast;

  /// No description provided for @baitWorm.
  ///
  /// In es, this message translates to:
  /// **'Lombriz'**
  String get baitWorm;

  /// No description provided for @baitSpinner.
  ///
  /// In es, this message translates to:
  /// **'Señuelo'**
  String get baitSpinner;

  /// No description provided for @baitFly.
  ///
  /// In es, this message translates to:
  /// **'Mosca'**
  String get baitFly;

  /// No description provided for @baitDough.
  ///
  /// In es, this message translates to:
  /// **'Masa'**
  String get baitDough;

  /// No description provided for @baitCorn.
  ///
  /// In es, this message translates to:
  /// **'Maíz'**
  String get baitCorn;

  /// No description provided for @baitOther.
  ///
  /// In es, this message translates to:
  /// **'Otro'**
  String get baitOther;

  /// No description provided for @speciesSearchLabel.
  ///
  /// In es, this message translates to:
  /// **'Selecciona una especie *'**
  String get speciesSearchLabel;

  /// No description provided for @speciesSearchHint.
  ///
  /// In es, this message translates to:
  /// **'Escribe y selecciona una especie de la lista'**
  String get speciesSearchHint;

  /// No description provided for @speciesSearchInvalid.
  ///
  /// In es, this message translates to:
  /// **'Selecciona una especie válida de la lista'**
  String get speciesSearchInvalid;

  /// No description provided for @chartExactDates.
  ///
  /// In es, this message translates to:
  /// **'Fechas exactas'**
  String get chartExactDates;

  /// No description provided for @chartGrowthByRecapture.
  ///
  /// In es, this message translates to:
  /// **'Crecimiento por recaptura'**
  String get chartGrowthByRecapture;

  /// No description provided for @chartGrowthTitle.
  ///
  /// In es, this message translates to:
  /// **'Crecimiento del pez'**
  String get chartGrowthTitle;

  /// No description provided for @collectionRecaptureIndex.
  ///
  /// In es, this message translates to:
  /// **'Recaptura #{index}'**
  String collectionRecaptureIndex(int index);

  /// No description provided for @identifyingPendingCrop.
  ///
  /// In es, this message translates to:
  /// **'No se encontró una detección suficientemente clara. Estamos reintentando automáticamente con más fotogramas...'**
  String get identifyingPendingCrop;

  /// No description provided for @identifyingNeedsManualReview.
  ///
  /// In es, this message translates to:
  /// **'No fue posible detectar el pez después de varios intentos. Vuelve a grabarlo procurando mostrar el cuerpo completo, con buena iluminación y sin cubrirlo con las manos.'**
  String get identifyingNeedsManualReview;

  /// No description provided for @identifyingPollingTimeout.
  ///
  /// In es, this message translates to:
  /// **'La identificación está tardando más de lo esperado. Verifica que el servidor siga activo y pulsa Volver a intentar para consultar nuevamente el resultado.'**
  String get identifyingPollingTimeout;

  /// No description provided for @identifyingResultUnavailable.
  ///
  /// In es, this message translates to:
  /// **'El servidor marcó la identificación como completada, pero el resultado todavía no está disponible. Pulsa Volver a intentar para consultarlo nuevamente.'**
  String get identifyingResultUnavailable;
}

class _AppLocalizationsDelegate extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) => <String>['cs', 'en', 'es'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {


  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'cs': return AppLocalizationsCs();
    case 'en': return AppLocalizationsEn();
    case 'es': return AppLocalizationsEs();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.'
  );
}
