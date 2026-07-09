import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get appTitle => 'FishDex';

  @override
  String get appTagline => 'Identifica peces con IA';

  @override
  String get loading => 'Cargando...';

  @override
  String get save => 'Guardar';

  @override
  String get cancel => 'Cancelar';

  @override
  String get retry => 'Reintentar';

  @override
  String get skip => 'Saltar';

  @override
  String get next => 'Siguiente';

  @override
  String get back => 'Atrás';

  @override
  String get close => 'Cerrar';

  @override
  String get delete => 'Eliminar';

  @override
  String get edit => 'Editar';

  @override
  String get confirm => 'Confirmar';

  @override
  String get comingSoon => 'Próximamente';

  @override
  String get error => 'Error';

  @override
  String get success => 'Éxito';

  @override
  String get noConnection => 'Sin conexión. Verifica tu internet';

  @override
  String get unknownError => 'Error desconocido';

  @override
  String get serverError => 'Error del servidor. Inténtalo más tarde';

  @override
  String get navMap => 'Mapa';

  @override
  String get navCollection => 'Colección';

  @override
  String get navRanking => 'Ranking';

  @override
  String get navProfile => 'Perfil';

  @override
  String get navGallery => 'Galería';

  @override
  String get navIdentify => 'Identificar';

  @override
  String get navSpot => 'Spot';

  @override
  String get loginTitle => 'INICIAR SESIÓN';

  @override
  String get loginSubtitle => 'Bienvenido de vuelta, pescador';

  @override
  String get loginButton => 'ENTRAR';

  @override
  String get loginDemoMode => 'MODO DEMO (sin servidor)';

  @override
  String get loginNoAccount => '¿No tienes cuenta? ';

  @override
  String get loginRegister => 'Regístrate';

  @override
  String get loginPinging => 'Pinging...';

  @override
  String get loginSendPing => 'Send a ping';

  @override
  String get loginError => 'Error al iniciar sesión';

  @override
  String get loginWrongCredentials => 'Email o contraseña incorrectos';

  @override
  String get loginTooManyAttempts => 'Demasiados intentos. Espera un momento';

  @override
  String get registerTitle => 'CREAR CUENTA';

  @override
  String get registerSubtitle => 'Únete a la comunidad de pescadores';

  @override
  String get registerResearcherSubtitle => 'Registro como investigador';

  @override
  String get registerButton => 'CREAR CUENTA';

  @override
  String get registerResearcherButton => 'SOLICITAR ACCESO';

  @override
  String get registerHasAccount => '¿Ya tienes cuenta? ';

  @override
  String get registerLogin => 'Inicia Sesión';

  @override
  String get registerWelcomeXp => '+50 XP de bienvenida';

  @override
  String get registerApprovalRequired => 'Requiere aprobación de administrador';

  @override
  String get registerEmailAlreadyExists => 'Este email ya está registrado';

  @override
  String get fieldEmail => 'Email';

  @override
  String get fieldEmailInstitutional => 'Email institucional';

  @override
  String get fieldEmailEnter => 'Ingresa tu email';

  @override
  String get fieldEmailInvalid => 'Email no válido';

  @override
  String get fieldPassword => 'Contraseña';

  @override
  String get fieldPasswordEnter => 'Ingresa una contraseña';

  @override
  String get fieldPasswordMin => 'Mínimo 8 caracteres';

  @override
  String get fieldPasswordConfirm => 'Confirmar Contraseña';

  @override
  String get fieldPasswordMismatch => 'Las contraseñas no coinciden';

  @override
  String get fieldName => 'Nombre de Pescador';

  @override
  String get fieldNameFull => 'Nombre completo';

  @override
  String get fieldNameEnter => 'Ingresa tu nombre';

  @override
  String get fieldNameMin => 'Mínimo 3 caracteres';

  @override
  String get fieldInstitution => 'Institución / Universidad';

  @override
  String get fieldInstitutionEnter => 'Ingresa tu institución';

  @override
  String get fieldInstitutionHint => 'Ej: Universidad de Barcelona';

  @override
  String get fieldReason => 'Motivo de uso';

  @override
  String get fieldReasonHint => 'Describe brevemente para qué necesitas acceso a los datos completos';

  @override
  String get fieldReasonMin => 'Mínimo 20 caracteres';

  @override
  String get onboardingSkip => 'Saltar';

  @override
  String get onboardingChooseRole => 'Elegir mi rol';

  @override
  String get onboardingPage1Title => 'Identifica Peces';

  @override
  String get onboardingPage1Desc => 'Usa la cámara para grabar peces en su hábitat natural. Nuestra IA identifica cada pez individualmente, como una huella dactilar submarina.';

  @override
  String get onboardingPage2Title => 'Colecciona y Compite';

  @override
  String get onboardingPage2Desc => 'Construye tu FishDex como un Pokédex acuático. Descubre especies raras, gana XP, sube de nivel y compite en el ranking con otros exploradores.';

  @override
  String get onboardingPage3Title => 'Contribuye a la Ciencia';

  @override
  String get onboardingPage3Desc => 'Cada avistamiento ayuda a los investigadores a rastrear migración, crecimiento y salud de los ecosistemas marinos. Tus datos hacen la diferencia.';

  @override
  String get onboardingRoleTitle => '¿Cuál es tu perfil?';

  @override
  String get onboardingRoleSubtitle => 'Esto define qué datos puedes ver en la app';

  @override
  String get onboardingFishermanTitle => 'Soy Pescador';

  @override
  String get onboardingFishermanDesc => 'Registra tus capturas, colecciona especies y compite en el ranking. Acceso inmediato.';

  @override
  String get onboardingResearcherTitle => 'Soy Investigador';

  @override
  String get onboardingResearcherDesc => 'Accede a datos completos de ubicación, historial y estadísticas. Requiere aprobación de un admin.';

  @override
  String get onboardingRequiresApproval => 'Requiere aprobación';

  @override
  String get pendingApprovalTitle => 'Solicitud Enviada';

  @override
  String get pendingApprovalDesc => 'Tu solicitud como investigador está siendo revisada por un administrador.';

  @override
  String get pendingApprovalNote => 'Te notificaremos automáticamente cuando sea aprobada. No necesitas cerrar la app.';

  @override
  String get pendingApprovalStatus => 'Pendiente de aprobación';

  @override
  String get pendingApprovalApproved => 'Tu cuenta ha sido aprobada!';

  @override
  String get pendingApprovalRejected => 'Tu solicitud ha sido rechazada. Contacta al administrador.';

  @override
  String get pendingApprovalLogout => 'Cerrar sesión';

  @override
  String get profileTitle => 'Perfil';

  @override
  String get profileEditButton => 'Editar perfil';

  @override
  String get profileLogout => 'Cerrar sesión';

  @override
  String get profileLogoutConfirm => '¿Seguro que quieres cerrar sesión?';

  @override
  String get profileLogoutTitle => 'Cerrar sesión';

  @override
  String get profileStatsTitle => 'ESTADÍSTICAS';

  @override
  String get profileQuickAccess => 'ACCESOS RÁPIDOS';

  @override
  String get profileSummary => 'RESUMEN';

  @override
  String get profileLastActivity => 'Última actividad';

  @override
  String get profileTotalCaptures => 'Total capturas';

  @override
  String get profileUniqueSpecies => 'Especies únicas';

  @override
  String get profileTotalXp => 'XP total';

  @override
  String get profileAdminPanel => 'Panel de Administración';

  @override
  String get profileNoActivity => 'Sin actividad reciente';

  @override
  String profileMinutesAgo(int minutes) {
    return 'Hace $minutes min';
  }

  @override
  String profileHoursAgo(int hours) {
    return 'Hace ${hours}h';
  }

  @override
  String profileDaysAgo(int days) {
    return 'Hace $days días';
  }

  @override
  String levelTitle(int level) {
    return 'NV. $level';
  }

  @override
  String get levelBeginner => 'Principiante';

  @override
  String get levelApprentice => 'Aprendiz';

  @override
  String get levelIntermediate => 'Intermedio';

  @override
  String get levelAdvanced => 'Avanzado';

  @override
  String get levelVeteran => 'Veterano';

  @override
  String get levelExpert => 'Experto';

  @override
  String get levelMaster => 'Maestro';

  @override
  String get levelGrandMaster => 'Gran Maestro';

  @override
  String get levelLegendaryMaster => 'Maestro Legendario';

  @override
  String get statsCaptures => 'Capturas';

  @override
  String get statsSpecies => 'Especies';

  @override
  String get statsRare => 'Raros';

  @override
  String get statsLegendary => 'Legendarios';

  @override
  String get roleAdmin => 'Administrador';

  @override
  String get roleFisherman => 'Pescador';

  @override
  String get roleResearcher => 'Investigador';

  @override
  String profileSetupStep(int current, int total) {
    return 'Paso $current de $total';
  }

  @override
  String get profileSetupUsername => 'Elige tu nombre de pescador';

  @override
  String get profileSetupUsernameSubtitle => 'Este nombre te identificará en la comunidad';

  @override
  String get profileSetupUsernameLabel => 'Nombre de usuario';

  @override
  String get profileSetupUsernameHint => 'ej: PescadorPro123';

  @override
  String get profileSetupUsernameHelper => 'Mínimo 3 caracteres, sin espacios';

  @override
  String get profileSetupUsernameRequired => 'Ingresa un nombre de usuario';

  @override
  String get profileSetupUsernameMinChars => 'Mínimo 3 caracteres';

  @override
  String get profileSetupUsernameNoSpaces => 'No se permiten espacios';

  @override
  String get profileSetupAvatar => 'Foto de perfil';

  @override
  String get profileSetupAvatarSet => '¡Se ve genial! Puedes cambiarla cuando quieras';

  @override
  String get profileSetupAvatarEmpty => 'Muestra tu mejor cara de pescador';

  @override
  String get profileSetupAvatarTap => 'Toca para elegir';

  @override
  String get profileSetupAvatarGallery => 'Galería';

  @override
  String get profileSetupAvatarCamera => 'Cámara';

  @override
  String get profileSetupAvatarRemove => 'Eliminar foto';

  @override
  String get profileSetupAvatarSkip => 'Omitir este paso';

  @override
  String get profileSetupSelectPhoto => 'Seleccionar foto';

  @override
  String get profileSetupLocation => 'Tu ubicación';

  @override
  String get profileSetupLocationSubtitle => 'Ayuda a otros pescadores cercanos a encontrarte';

  @override
  String get profileSetupDetectingLocation => 'Detectando...';

  @override
  String get profileSetupDetectLocation => 'Detectar mi ubicación automáticamente';

  @override
  String get profileSetupCityLabel => 'Ciudad o región';

  @override
  String get profileSetupCityHint => 'ej: Cancún, México';

  @override
  String get profileSetupShareLocation => 'Compartir mi ubicación aproximada con la comunidad';

  @override
  String get profileSetupPermissions => 'Permisos necesarios';

  @override
  String get profileSetupPermissionsSubtitle => 'Para brindarte la mejor experiencia, necesitamos algunos permisos';

  @override
  String get profileSetupPermCamera => 'Cámara';

  @override
  String get profileSetupPermCameraDesc => 'Para identificar peces en tiempo real';

  @override
  String get profileSetupPermLocation => 'Ubicación';

  @override
  String get profileSetupPermLocationDesc => 'Para registrar avistamientos en el mapa';

  @override
  String get profileSetupPermGallery => 'Fotos / Galería';

  @override
  String get profileSetupPermGalleryDesc => 'Para tu foto de perfil y galería de peces';

  @override
  String get profileSetupPermissionsGranted => 'Permisos concedidos';

  @override
  String get profileSetupGrantPermissions => 'Conceder permisos';

  @override
  String get profileSetupSkipForNow => 'Omitir por ahora';

  @override
  String get profileSetupDoneTitle => '¡Todo listo!';

  @override
  String get profileSetupDoneSubtitle => 'Tu perfil está configurado.\nEs hora de explorar el mundo acuático.';

  @override
  String get profileSetupStartButton => 'EMPEZAR A PESCAR!';

  @override
  String get profileSetupViewProfile => 'Ver mi perfil';

  @override
  String get mapTitle => 'MAPA DE PESCA';

  @override
  String get mapSpots => 'Spots';

  @override
  String get mapActivateLocation => 'Activar ubicación para ver spots cercanos';

  @override
  String get mapGettingLocation => 'Obteniendo ubicación...';

  @override
  String mapGpsError(String error) {
    return 'Error GPS: $error';
  }

  @override
  String get mapAnonymousTitle => 'Pez registrado anteriormente';

  @override
  String mapAnonymousDesc(String species) {
    return 'Este pez ($species) ya fue registrado por otro explorador en esta zona. La ubicación exacta no está disponible para proteger la privacidad de otros usuarios.';
  }

  @override
  String get mapDataProtected => 'Datos protegidos';

  @override
  String get mapFishDate => 'Fecha';

  @override
  String get mapFishId => 'Fish ID';

  @override
  String get mapCoordinates => 'Coordenadas';

  @override
  String get spotWaterRiver => 'Río';

  @override
  String get spotWaterLake => 'Lago';

  @override
  String get spotWaterSea => 'Mar';

  @override
  String get spotWaterReservoir => 'Embalse';

  @override
  String get spotRareFish => 'Peces raros';

  @override
  String get spotCaptures => 'Capturas';

  @override
  String get spotSpecies => 'Especies';

  @override
  String get spotLastCatch => 'Última captura';

  @override
  String get spotCommonSpecies => 'ESPECIES COMUNES';

  @override
  String get spotFishHere => 'PESCAR AQUÍ';

  @override
  String get spotToday => 'Hoy';

  @override
  String get spotYesterday => 'Ayer';

  @override
  String spotDaysAgo(int days) {
    return 'Hace ${days}d';
  }

  @override
  String get quickSpotTitle => 'MARCAR SPOT';

  @override
  String get quickSpotSubtitle => 'Guarda este lugar de pesca en el mapa';

  @override
  String get quickSpotNameLabel => 'Nombre del spot';

  @override
  String get quickSpotNameHint => 'Ej: Río Lozoya - Poza norte';

  @override
  String get quickSpotWaterType => 'Tipo de agua';

  @override
  String get quickSpotDescription => 'Descripción (opcional)';

  @override
  String get quickSpotDescriptionHint => 'Notas sobre este spot...';

  @override
  String get quickSpotLocationCurrent => 'Ubicación GPS actual';

  @override
  String get quickSpotLocationNone => 'Sin señal GPS';

  @override
  String get quickSpotLocationGetting => 'Obteniendo GPS...';

  @override
  String get quickSpotLocationError => 'Error al obtener ubicación';

  @override
  String get quickSpotSaving => 'Guardando...';

  @override
  String get quickSpotSaveButton => 'GUARDAR SPOT';

  @override
  String quickSpotSavedDemo(String name) {
    return '¡Spot \"$name\" marcado (modo demo)!\nRegistra una cuenta para guardarlo permanentemente.';
  }

  @override
  String quickSpotSaved(String name) {
    return '¡Spot \"$name\" guardado en el mapa!';
  }

  @override
  String get quickSpotErrorGps => 'No se pudo obtener tu ubicación GPS.\nActiva el GPS e inténtalo de nuevo.';

  @override
  String get quickSpotErrorName => 'Ponle un nombre al spot para poder guardarlo.';

  @override
  String quickSpotErrorSave(String error) {
    return 'Error al guardar el spot.\n$error';
  }

  @override
  String get quickSpotWaterRiver => 'Río';

  @override
  String get quickSpotWaterReservoir => 'Embalse';

  @override
  String get quickSpotWaterLake => 'Lago';

  @override
  String get quickSpotWaterSea => 'Mar';

  @override
  String get collectionTitle => 'MI COLECCIÓN';

  @override
  String collectionDiscovered(int count) {
    return '$count especies descubiertas';
  }

  @override
  String get collectionFilterAll => 'Todos';

  @override
  String get collectionFilterCommon => 'Comunes';

  @override
  String get collectionFilterUncommon => 'Poco comunes';

  @override
  String get collectionFilterRare => 'Raros';

  @override
  String get collectionFilterLegendary => 'Legendarios';

  @override
  String get collectionUndiscovered => 'No descubierto';

  @override
  String collectionTimesSpotted(int count) {
    return '${count}x';
  }

  @override
  String get collectionSizeLabel => 'Tamaño';

  @override
  String get collectionSightingsLabel => 'Avistamientos';

  @override
  String get collectionRarityLabel => 'Rareza';

  @override
  String get collectionHistoryTitle => 'HISTORIAL DE AVISTAMIENTOS';

  @override
  String get collectionFirstSighting => 'Primer avistamiento';

  @override
  String get rankingTitle => 'RANKING';

  @override
  String get rankingTabXp => 'XP TOTAL';

  @override
  String get rankingTabSpecies => 'ESPECIES';

  @override
  String get rankingTabBiggest => 'PEZ MAYOR';

  @override
  String get rankingPeriodGlobal => 'Global';

  @override
  String get rankingPeriodWeekly => 'Semanal';

  @override
  String get rankingPeriodMonthly => 'Mensual';

  @override
  String get rankingYourPosition => 'Tu posición:';

  @override
  String get rankingLoginToSee => 'Inicia sesión para ver tu posición';

  @override
  String get rankingEmpty => 'Sé el primero en el ranking';

  @override
  String get rankingEmptySubtitle => '¡Identifica tu primer pez!';

  @override
  String get rankingNoConnection => 'Sin conexión';

  @override
  String get rankingYouBadge => 'TÚ';

  @override
  String rankingLevel(int level) {
    return 'Nv. $level';
  }

  @override
  String rankingValueXp(int value) {
    return '$value XP';
  }

  @override
  String rankingValueSpecies(int value) {
    return '$value spp';
  }

  @override
  String rankingValueBiggest(String value) {
    return '$value cm';
  }

  @override
  String get cameraLoading => 'Iniciando cámara...';

  @override
  String get cameraNoCameras => 'No se encontraron cámaras disponibles';

  @override
  String cameraInitError(String error) {
    return 'Error al inicializar la cámara: $error';
  }

  @override
  String get cameraRecordError => 'Error al iniciar grabación';

  @override
  String get cameraStopError => 'Error al detener grabación';

  @override
  String get cameraRetry => 'Reintentar';

  @override
  String get videoPreviewTitle => '¿Se ve bien tu captura?';

  @override
  String get videoPreviewSubtitle => 'Asegúrate de que el pez se vea claramente';

  @override
  String get videoPreviewRetake => 'REGRABAR';

  @override
  String get videoPreviewIdentify => 'IDENTIFICAR';

  @override
  String get identifyingProcessing => 'Procesando video...';

  @override
  String get identifyingExtractingFrames => 'Extrayendo frames...';

  @override
  String get identifyingAnalyzing => 'Analizando con IA...';

  @override
  String get identifyingSuccess => '¡Pez identificado!';

  @override
  String get identifyingError => 'Error';

  @override
  String get identifyingUnexpectedError => 'Error inesperado al identificar';

  @override
  String get identifyingRetry => 'Volver a intentar';

  @override
  String get resultNewDiscovery => '¡NUEVO DESCUBRIMIENTO!';

  @override
  String get resultReunion => '¡REENCUENTRO!';

  @override
  String get resultDetails => 'Detalles del avistamiento';

  @override
  String get resultFishId => 'ID del pez';

  @override
  String get resultSpecies => 'Especie';

  @override
  String get resultEstimatedSize => 'Tamaño estimado';

  @override
  String get resultAiConfidence => 'Confianza IA';

  @override
  String get resultViewCollection => 'VER EN MI COLECCIÓN';

  @override
  String get resultBackToMap => 'VOLVER AL MAPA';

  @override
  String get fishCardNew => 'NUEVO';

  @override
  String get fishCardRarity => 'RAREZA';

  @override
  String get fishCardAiConfidence => '% IA';

  @override
  String get reunionHistory => 'Historial del pez';

  @override
  String reunionTimesSeen(int count) {
    return '${count}x visto';
  }

  @override
  String get reunionFirstSighting => 'Primer avistamiento';

  @override
  String get reunionFirstLocation => 'Primera ubicación';

  @override
  String get reunionLastSighting => 'Último avistamiento';

  @override
  String get reunionUnknown => 'Desconocida';

  @override
  String get reunionGrown => '¡Ha crecido!';

  @override
  String get reunionGrowthLabel => 'cm';

  @override
  String get captureFormTitle => 'Identificación Manual';

  @override
  String get captureFormTitleComplete => 'Completar Captura';

  @override
  String get captureFormTitleRegister => 'Registrar Captura';

  @override
  String get captureFormLowConfidence => 'Identificación no concluyente';

  @override
  String captureFormLowConfidenceDesc(int percent) {
    return 'La IA no pudo identificar el pez con suficiente confianza ($percent%). Por favor, completa la información manualmente.';
  }

  @override
  String captureFormAiBanner(String species) {
    return 'IA: $species';
  }

  @override
  String captureFormAiBannerDesc(int percent) {
    return 'Confianza: $percent% - Puedes agregar datos adicionales abajo.';
  }

  @override
  String get captureFormSaveButton => 'GUARDAR CAPTURA';

  @override
  String get captureFormSaved => 'Captura guardada exitosamente!';

  @override
  String get captureFormSelectCondition => 'Selecciona la condición del pez';

  @override
  String get captureFieldSpecies => 'Especie / Descripción visual *';

  @override
  String get captureFieldSpeciesHint => 'Ej: Trucha Arcoíris, pez plateado con manchas...';

  @override
  String get captureFieldSpeciesRequired => 'Campo obligatorio';

  @override
  String get captureFieldLength => 'Longitud estimada (cm) *';

  @override
  String get captureFieldLengthHint => 'Ej: 35.5';

  @override
  String get captureFieldLengthRequired => 'Campo obligatorio';

  @override
  String get captureFieldLengthInvalid => 'Ingresa un número válido';

  @override
  String get captureFieldWeight => 'Peso estimado (kg)';

  @override
  String get captureFieldWeightHint => 'Ej: 2.3';

  @override
  String get captureFieldColor => 'Color predominante';

  @override
  String get captureFieldColorHint => 'Ej: Plateado con reflejos azules';

  @override
  String get captureFieldCondition => 'Condición al momento de captura *';

  @override
  String get captureConditionAlive => 'Vivo';

  @override
  String get captureConditionReleased => 'Liberado';

  @override
  String get captureConditionDead => 'Muerto';

  @override
  String get captureFieldFeatures => 'Características físicas';

  @override
  String get captureFieldFeaturesHint => 'Ej: Aleta dorsal prominente, cola bifurcada...';

  @override
  String get captureFieldNotes => 'Notas adicionales';

  @override
  String get captureFieldNotesHint => 'Cualquier observación adicional...';

  @override
  String get captureFieldGps => 'Ubicación GPS';

  @override
  String get captureFieldLatitude => 'Latitud';

  @override
  String get captureFieldLongitude => 'Longitud';

  @override
  String get galleryTitle => 'Abriendo galería';

  @override
  String get gallerySubtitle => 'Selecciona un video de tu pez\npara identificarlo con IA';

  @override
  String get galleryCancel => 'Cancelar';

  @override
  String galleryError(String error) {
    return 'No se pudo acceder a la galería: $error';
  }

  @override
  String get achievementsCategory => 'Logros';

  @override
  String get achievementsDiscovery => 'Descubrimiento';

  @override
  String get achievementsCollection => 'Colección';

  @override
  String get achievementsSocial => 'Social';

  @override
  String get achievementsExploration => 'Exploración';

  @override
  String get achievementsUnlocked => '¡Logro desbloqueado!';

  @override
  String get achievementsBronze => 'Bronce';

  @override
  String get achievementsSilver => 'Plata';

  @override
  String get achievementsGold => 'Oro';

  @override
  String get achievementsPlatinum => 'Platino';

  @override
  String achievementsProgressLabel(int current, int target) {
    return '$current/$target';
  }

  @override
  String get adminPanelTitle => 'PANEL DE ADMIN';

  @override
  String get adminPendingRequests => 'Solicitudes Pendientes';

  @override
  String get adminStats => 'Estadísticas';

  @override
  String get adminNoPending => 'No hay solicitudes pendientes';

  @override
  String get adminApprove => 'Aprobar';

  @override
  String get adminReject => 'Rechazar';

  @override
  String get adminApproved => 'Investigador aprobado correctamente';

  @override
  String get adminRejected => 'Solicitud rechazada';

  @override
  String adminErrorLoading(String error) {
    return 'Error al cargar solicitudes: $error';
  }

  @override
  String get adminStatsPending => 'Pendientes';

  @override
  String get adminStatsCapturesDay => 'Capturas Hoy';

  @override
  String get adminStatsUsers => 'Usuarios';

  @override
  String get adminStatsSpecies => 'Especies';

  @override
  String get demoModeBanner => 'Modo demo activo. Crea una cuenta para guardar tu progreso.';

  @override
  String get demoModeCreateAccount => 'Crear cuenta';

  @override
  String get rarityCommon => 'Común';

  @override
  String get rarityUncommon => 'Poco común';

  @override
  String get rarityRare => 'Raro';

  @override
  String get rarityLegendary => 'Legendario';

  @override
  String get conditionAlive => 'Vivo';

  @override
  String get conditionReleased => 'Liberado';

  @override
  String get conditionDead => 'Muerto';

  @override
  String get cameraGuideSkip => 'Omitir';

  @override
  String get cameraGuideNext => 'Siguiente';

  @override
  String get cameraGuideStart => 'Iniciar cámara';

  @override
  String get cameraGuideOrientationTitle => 'Orientación correcta';

  @override
  String get cameraGuideOrientationDesc => 'Coloca siempre el pez con la CABEZA apuntando hacia la DERECHA y la COLA apuntando hacia la IZQUIERDA. Esto asegura una identificación consistente.';

  @override
  String get cameraGuideOrientationTip => 'Misma orientación = mejor precisión';

  @override
  String get cameraGuidePositionTitle => 'Cuerpo completo visible';

  @override
  String get cameraGuidePositionDesc => 'Asegúrate de que todo el cuerpo del pez sea visible en el encuadre, desde la boca hasta la cola. Deja pequeños márgenes en todos los lados. Distancia: 30-50 cm.';

  @override
  String get cameraGuidePositionTip => 'Cuerpo completo = patrones analizados correctamente';

  @override
  String get cameraGuideTechniqueTitle => 'Consejos de grabación';

  @override
  String get cameraGuideTechniqueDesc => 'Coloca el pez sobre una superficie plana (una alfombrilla de medición es ideal). Minimiza la cobertura con las manos. Un video estable de 5-10 segundos es perfecto.';

  @override
  String get cameraGuideDoFlat => 'Colocar el pez plano sobre la alfombrilla';

  @override
  String get cameraGuideDoLight => 'Usar buena luz natural';

  @override
  String get cameraGuideDoSteady => 'Grabar 5-10 segundos de forma estable';

  @override
  String get cameraGuideDontHands => 'Sostener el pez cubriendo el cuerpo';

  @override
  String get cameraGuideDontDark => 'Grabar en condiciones muy oscuras';

  @override
  String get cameraGuideReadyTitle => '¡Listo para capturar!';

  @override
  String get cameraGuideReadyDesc => 'La cámara mostrará una guía con la silueta de un pez. Alinea el pez con el contorno y presiona el botón de grabar. ¡La IA identificará tu captura!';

  @override
  String get cameraGuideReadySettings => 'Siempre puedes acceder a esta guía desde los ajustes de la cámara.';

  @override
  String get arAlignSilhouette => 'Alinea el pez con la silueta';

  @override
  String get arHeadLeftBodyVisible => 'Cabeza hacia la DERECHA • Cuerpo completo visible';

  @override
  String get arHeadLabel => 'CABEZA';

  @override
  String get arTailLabel => 'COLA';

  @override
  String get arHorizontal => 'Horizontal';

  @override
  String get arDistance => '30-50cm';

  @override
  String get arGoodLight => 'Buena luz';

  @override
  String get recordingStateRecording => 'Grabando... Mantén estable';

  @override
  String recordingStatePressToRecord(int seconds) {
    return 'Pulsa para grabar (${seconds}s máx)';
  }

  @override
  String get sheetOwnCapture => 'MI CAPTURA';

  @override
  String get sheetFieldDate => 'Fecha';

  @override
  String get sheetFieldTime => 'Hora';

  @override
  String get sheetFieldFishId => 'Fish ID';

  @override
  String get sheetFieldCaptureId => 'Capture ID';

  @override
  String get sheetFieldUser => 'Usuario';

  @override
  String get sheetFieldCoordinates => 'Coordenadas exactas';

  @override
  String get sheetHistoryTitle => 'Historial del pez';

  @override
  String get sheetHistorySubtitle => 'Ver todas las capturas de este pez';

  @override
  String timelineSummary(int captures, int locations) {
    return '$captures capturas en $locations ubicaciones';
  }

  @override
  String timelineLocationZone(String label) {
    return 'Zona $label';
  }

  @override
  String get timelineStatusNew => 'Nuevo';

  @override
  String get timelineStatusReunion => 'Reencuentro';

  @override
  String get timelineEmpty => 'No hay historial disponible para este pez';

  @override
  String timelineError(Object error) {
    return 'Error al cargar historial: $error';
  }

  @override
  String get quickSpotFishingAreaLabel => 'Coto de Pesca (Revír)';

  @override
  String get quickSpotLoadingAreas => 'Cargando cotos cercanos...';

  @override
  String get quickSpotSearchAreaHint => 'Buscar coto por nombre o código...';

  @override
  String get quickSpotNoAreasNearby => 'No se encontraron cotos cercanos. Intenta aumentar el radio.';

  @override
  String get quickSpotNoAreasMatching => 'Sin cotos que coincidan. Intenta otra búsqueda.';
}
