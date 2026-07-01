# FishDex - Configuración de Appwrite Console

## Paso 1: Levantar el servicio

```bash
cd "FISH APP"
docker compose up -d
```

Espera 1-2 minutos a que todos los contenedores arranquen. Verifica con:

```bash
docker compose ps
```

## Paso 2: Acceder a la consola

1. Abre http://localhost en tu navegador
2. Crea tu cuenta de administrador (primer acceso)
3. Crea un nuevo proyecto con ID: `fishdex` y nombre: "FishDex"

## Paso 3: Crear la Base de Datos

En el proyecto FishDex, ve a **Databases** > **Create Database**:
- Database ID: `fishdex_db`
- Name: `FishDex Database`

## Paso 4: Crear las Colecciones

### 4.1 Colección: `users`
**Collection ID:** `users`
**Name:** Usuarios
**Permisos:** Read: `role:member` | Create/Update: `user:{userId}`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| name | string(100) | Sí | - | Nombre del usuario |
| avatar_url | string(500) | No | - | URL del avatar |
| level | integer | Sí | 1 | Nivel actual |
| xp | integer | Sí | 0 | Puntos de experiencia |
| xp_to_next_level | integer | Sí | 100 | XP necesaria para subir |
| role | enum["pescador","investigador"] | Sí | pescador | Rol del usuario |
| total_sightings | integer | Sí | 0 | Total de avistamientos |
| unique_species | integer | Sí | 0 | Especies únicas identificadas |
| biggest_fish_cm | float | Sí | 0 | Pez más grande (cm) |
| locations_explored | integer | Sí | 0 | Ubicaciones exploradas |
| days_active | integer | Sí | 0 | Días con actividad |
| joined_at | datetime | Sí | - | Fecha de registro |

**Índices:**
- `idx_xp` → atributo: xp, tipo: key, orden: DESC
- `idx_level` → atributo: level, tipo: key, orden: DESC

---

### 4.2 Colección: `fish_individuals`
**Collection ID:** `fish_individuals`
**Name:** Peces Individuales
**Permisos:** Read: `role:member` | Create: `role:member` | Update: `role:member`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| fish_id | string(20) | Sí | - | ID único del modelo IA |
| species | string(100) | Sí | - | Especie del pez |
| rarity | enum["common","uncommon","rare","legendary"] | Sí | common | Rareza |
| first_seen_date | datetime | Sí | - | Primer avistamiento |
| first_seen_lat | float | No | - | Latitud primer avistamiento |
| first_seen_lng | float | No | - | Longitud primer avistamiento |
| first_seen_by | string(36) | Sí | - | User ID del descubridor |
| estimated_size_cm | float | Sí | - | Último tamaño estimado |
| photo_url | string(500) | No | - | URL foto de referencia |
| total_sightings | integer | Sí | 1 | Veces avistado |
| last_seen_date | datetime | Sí | - | Último avistamiento |
| last_seen_lat | float | No | - | Latitud último avistamiento |
| last_seen_lng | float | No | - | Longitud último avistamiento |

**Índices:**
- `idx_fish_id` → atributo: fish_id, tipo: unique
- `idx_species` → atributo: species, tipo: key
- `idx_rarity` → atributo: rarity, tipo: key
- `idx_total_sightings` → atributo: total_sightings, tipo: key, orden: DESC

---

### 4.3 Colección: `fish_sightings`
**Collection ID:** `fish_sightings`
**Name:** Avistamientos
**Permisos:** Read: `role:member` | Create: `role:member`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| fish_id | string(20) | Sí | - | ID del pez avistado |
| user_id | string(36) | Sí | - | ID del usuario |
| species | string(100) | Sí | - | Especie |
| date | datetime | Sí | - | Fecha del avistamiento |
| latitude | float | No | - | Latitud |
| longitude | float | No | - | Longitud |
| video_file_id | string(36) | No | - | ID del video en Storage |
| photo_file_id | string(36) | No | - | ID de foto en Storage |
| estimated_size_cm | float | Sí | - | Tamaño estimado |
| confidence | float | Sí | - | Confianza del modelo |
| is_new_fish | boolean | Sí | - | Si fue primera vez |
| xp_earned | integer | Sí | - | XP otorgada |
| notes | string(500) | No | - | Notas del pescador |
| spot_id | string(36) | No | - | Fishing spot asociado |

**Índices:**
- `idx_user_date` → atributos: [user_id, date], tipo: key, orden: DESC
- `idx_fish_id` → atributo: fish_id, tipo: key
- `idx_spot` → atributo: spot_id, tipo: key

---

### 4.4 Colección: `achievements`
**Collection ID:** `achievements`
**Name:** Catálogo de Logros
**Permisos:** Read: `role:member` (solo lectura para todos)

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| name | string(100) | Sí | - | Nombre del logro |
| description | string(300) | Sí | - | Descripción |
| icon | string(50) | Sí | - | Nombre del icono |
| xp_reward | integer | Sí | - | XP de recompensa |
| category | enum["discovery","collection","social","exploration"] | Sí | - | Categoría |
| criteria_type | string(50) | Sí | - | Tipo de criterio |
| criteria_value | integer | Sí | - | Valor del criterio |
| rarity | enum["bronze","silver","gold","platinum"] | Sí | bronze | Nivel del logro |

---

### 4.5 Colección: `user_achievements`
**Collection ID:** `user_achievements`
**Name:** Logros de Usuario
**Permisos:** Read: `role:member` | Create: `role:member`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| user_id | string(36) | Sí | - | ID del usuario |
| achievement_id | string(36) | Sí | - | ID del logro |
| unlocked_at | datetime | Sí | - | Fecha de desbloqueo |
| progress | integer | Sí | 0 | Progreso actual |
| target | integer | Sí | - | Objetivo a alcanzar |

**Índices:**
- `idx_user` → atributo: user_id, tipo: key
- `idx_user_achievement` → atributos: [user_id, achievement_id], tipo: unique

---

### 4.6 Colección: `leaderboards`
**Collection ID:** `leaderboards`
**Name:** Rankings
**Permisos:** Read: `role:member` | Create/Update: `role:member`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| user_id | string(36) | Sí | - | ID del usuario |
| user_name | string(100) | Sí | - | Nombre (denormalizado) |
| user_avatar | string(500) | No | - | Avatar (denormalizado) |
| user_level | integer | Sí | - | Nivel (denormalizado) |
| ranking_type | enum["xp","species","biggest_fish"] | Sí | - | Tipo de ranking |
| period | enum["all_time","weekly","monthly"] | Sí | all_time | Período |
| value | float | Sí | 0 | Valor del ranking |
| position | integer | No | - | Posición calculada |
| updated_at | datetime | Sí | - | Última actualización |

**Índices:**
- `idx_type_period_value` → atributos: [ranking_type, period, value], tipo: key, orden: DESC
- `idx_user_type` → atributos: [user_id, ranking_type, period], tipo: unique

---

### 4.7 Colección: `fishing_spots`
**Collection ID:** `fishing_spots`
**Name:** Spots de Pesca
**Permisos:** Read: `role:member` | Create: `role:member` | Update: `role:member`

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| name | string(100) | Sí | - | Nombre del spot |
| latitude | float | Sí | - | Latitud |
| longitude | float | Sí | - | Longitud |
| water_type | enum["rio","lago","mar","embalse"] | Sí | rio | Tipo de agua |
| total_catches | integer | Sí | 0 | Total capturas en este spot |
| common_species | string(500) | No | "[]" | JSON array de especies comunes |
| last_catch_date | datetime | No | - | Última captura |
| last_catch_photo | string(500) | No | - | Foto última captura |
| created_by | string(36) | Sí | - | Usuario que lo creó |
| description | string(300) | No | - | Descripción |
| has_rare_fish | boolean | Sí | false | Si se han visto peces raros |

**Índices:**
- `idx_location` → atributos: [latitude, longitude], tipo: key
- `idx_catches` → atributo: total_catches, tipo: key, orden: DESC
- `idx_rare` → atributo: has_rare_fish, tipo: key

---

### 4.8 Colección: `model_versions`
**Collection ID:** `model_versions`
**Name:** Versiones del Modelo
**Permisos:** Read: `role:member` (solo admin crea)

| Atributo | Tipo | Requerido | Default | Descripción |
|----------|------|-----------|---------|-------------|
| version | string(20) | Sí | - | Número de versión |
| release_date | datetime | Sí | - | Fecha de deploy |
| accuracy | float | Sí | - | Precisión del modelo |
| dataset_size | integer | Sí | - | Tamaño del dataset |
| training_epochs | integer | Sí | - | Épocas de entrenamiento |
| notes | string(500) | No | - | Notas del release |
| is_active | boolean | Sí | true | Si es la versión activa |

---

## Paso 5: Crear Storage Buckets

Ve a **Storage** > **Create Bucket**:

### Bucket: `fish_videos`
- Bucket ID: `fish_videos`
- Name: Videos de Peces
- Max file size: 52428800 (50MB)
- Allowed extensions: mp4, mov, avi
- Permissions: Create/Read: `role:member`
- Encryption: Enabled
- Antivirus: Enabled (si está disponible)

### Bucket: `fish_photos`
- Bucket ID: `fish_photos`
- Name: Fotos de Peces
- Max file size: 10485760 (10MB)
- Allowed extensions: jpg, jpeg, png, webp
- Permissions: Create/Read: `role:member`
- Encryption: Enabled

### Bucket: `user_avatars`
- Bucket ID: `user_avatars`
- Name: Avatares de Usuario
- Max file size: 5242880 (5MB)
- Allowed extensions: jpg, jpeg, png, webp
- Permissions: Create/Read: `role:member`

---

## Paso 6: Crear API Key

Ve a **Overview** > **API Keys** > **Create API Key**:
- Name: `fishdex-server`
- Scopes: Selecciona todos los scopes (para desarrollo)
- Copia la key y pégala en `.env` como `APPWRITE_API_KEY`

---

## Paso 7: Configurar Plataformas

Ve a **Overview** > **Platforms** > **Add Platform**:

### Flutter Android:
- Platform: Android
- Package Name: `com.fishdex.app`

### Flutter iOS:
- Platform: iOS
- Bundle ID: `com.fishdex.app`

---

## Paso 8: Insertar datos iniciales de Logros

Una vez creada la colección `achievements`, inserta estos logros desde la consola:

| name | description | icon | xp_reward | category | criteria_type | criteria_value | rarity |
|------|-------------|------|-----------|----------|---------------|----------------|--------|
| Primer Avistamiento | Identifica tu primer pez | fish | 50 | discovery | total_sightings | 1 | bronze |
| Coleccionista Novato | Identifica 10 peces diferentes | collection | 100 | collection | unique_species | 10 | silver |
| Maestro del Río | Identifica 50 peces diferentes | crown | 500 | collection | unique_species | 50 | gold |
| Pez Trofeo | Encuentra un pez de más de 100cm | trophy | 200 | discovery | biggest_fish | 100 | gold |
| Reencuentro | Identifica el mismo pez en diferentes días | refresh | 75 | discovery | repeat_sightings | 2 | silver |
| Explorador | Registra avistamientos en 5 ubicaciones | map | 150 | exploration | locations | 5 | silver |
| Científico Ciudadano | Contribuye con 100 avistamientos | science | 1000 | social | total_sightings | 100 | platinum |
| Madrugador | Identifica un pez antes de las 6:00 AM | sunrise | 50 | exploration | early_catch | 1 | bronze |
| Cazador Legendario | Encuentra un pez de rareza legendaria | star | 300 | discovery | legendary_catch | 1 | platinum |
| Racha de 7 Días | Usa la app 7 días consecutivos | fire | 100 | social | streak_days | 7 | silver |

---

## Verificación

Después de configurar todo, verifica:
1. ✓ Base de datos `fishdex_db` creada
2. ✓ 8 colecciones con todos sus atributos e índices
3. ✓ 3 storage buckets configurados
4. ✓ API Key creada y copiada al .env
5. ✓ Plataformas Android e iOS registradas
6. ✓ 10 logros iniciales insertados

El siguiente paso es verificar que el AI Server se conecta correctamente:
```bash
# Levantar solo el AI server para probar
docker compose up ai-server -d
# Verificar health
curl http://localhost:8000/health
# Probar identificación de prueba
curl http://localhost:8000/api/v1/identify/test
```
