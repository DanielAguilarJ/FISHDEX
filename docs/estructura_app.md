# FishDex app structure

This document describes the structure of the **FISH APP** workspace from top to bottom, separating each module by responsibility and marking which parts are source code, which parts are configuration, and which parts are generated artifacts.

## Project aim

FishDex is a gamified fish identification platform. The goal of the project is to help anglers identify fish from short videos, keep a history of sightings, and turn each catch into a richer experience through progress, collection, ranking, and discovery.

The system combines:

- a Flutter mobile app for capture, identification, collection, and user progress,
- a FastAPI AI backend for video processing and identification,
- Appwrite as the backend service layer for data, auth, and storage,
- a static web portal for cultural content,
- and a training pipeline for model preparation and evaluation.

## User groups and needs

### Recreational anglers
Need fast fish identification, a simple capture flow, location context, and a personal history of catches.

### Competitive or gamified users
Need progression, XP, rankings, achievements, and repeat-encounter tracking.

### Curious explorers
Need maps, nearby spots, species discovery, and a clear visual record of each identification.

### Administrators and maintainers
Need a structured backend, documented setup, reproducible training scripts, and clear deployment instructions.

## Overview

The workspace is split into four main surfaces:

- `ai-server/`: FastAPI backend that receives videos, extracts frames, and runs AI inference.
- `fishdex/`: main Flutter mobile app.
- `cultura climatica/`: standalone static web portal.
- `scripts/`: data, training, and model evaluation pipeline.

In addition, the root contains orchestration and documentation files such as `docker-compose.yml`, `opencode.json`, and `docs/`.

## Top-level tree

```text
FISH APP/
├── docker-compose.yml
├── opencode.json
├── ai-server/
├── cultura climatica/
├── docs/
├── fishdex/
└── scripts/
```

## Workspace root

### `docker-compose.yml`
Orchestrates the local environment. It starts the FastAPI AI server and the Appwrite stack on the same Docker network.

### `opencode.json`
Workspace configuration for OpenCode / Copilot.

### `docs/`
Project operational documentation.

### `scripts/`
Set of scripts used to prepare data, train models, export results, and run the pipeline.

## AI backend: `ai-server/`

This module is the server that handles fish identification.

### Structure

```text
ai-server/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py
│   ├── routers/
│   │   ├── __init__.py
│   │   └── identify.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── inference.py
│   └── utils/
│       ├── __init__.py
│       └── video.py
└── norway fish/
    ├── fin_detector_best.onnx
    ├── fin_detector_best.pt
    ├── train_detector (1).py
    ├── detector_dataset/
    │   └── images/
    └── source_images/
```

### What each part does

- `Dockerfile`: defines the AI server image.
- `requirements.txt`: Python dependencies for the backend.
- `app/main.py`: FastAPI entry point and route registration.
- `app/models/schemas.py`: response schemas and data models.
- `app/routers/identify.py`: HTTP endpoints for fish identification.
- `app/services/inference.py`: inference logic and simulated output generation.
- `app/utils/video.py`: utilities to save video, extract frames, and clean temporary files.
- `norway fish/`: model and data folder related to training or export.
    - `fin_detector_best.onnx`: ONNX export of the model.
    - `fin_detector_best.pt`: PyTorch weights.
    - `train_detector (1).py`: training or test script.
    - `detector_dataset/images/`: image dataset.
    - `source_images/`: source images used during preparation or training.

### Backend flow

1. The Flutter app sends a video to the identification endpoint.
2. `identify.py` validates the file type and size.
3. `video.py` stores the temporary file and extracts frames.
4. `inference.py` selects the result and builds the response.
5. `main.py` exposes service health and the API under `/api/v1`.

### Server file structure and fish storage behavior

The current AI server is structured around code modules and temporary processing files. It does not currently create one permanent folder per fish inside the server filesystem.

The important idea is this:

- uploaded videos are stored temporarily,
- frames are extracted in memory for inference,
- the identification response is returned to the app,
- and persistent history is expected to live in the backend data layer, not in local fish folders.

If a new catch is recognized as an existing fish, the normal behavior is to reuse the same `fish_id` and register a new sighting instead of creating a separate fish folder.

If the same fish is caught more than once, the description should be updated as a living record rather than duplicated. In practice, that means:

- keep one canonical fish entity,
- append new catch metadata to its history,
- update the latest description or notes with the most recent catch context,
- and keep previous sightings available in the timeline.

If the product later needs per-fish media storage, the recommended approach is a logical structure such as:

```text
fish-media/
└── {fish_id}/
    ├── images/
    ├── videos/
    └── description.json
```

That structure would be a storage convention, not a current requirement of the existing backend code.

### Notes on repeated recognition

If a new fish is matched with an existing one, the system should not create a duplicate record by default. Instead, it should:

1. reuse the existing fish identifier,
2. attach the new images or frames to the same fish history,
3. increment the sighting count,
4. and decide whether the description should be merged, versioned, or appended.

For two catches of the same fish, the description can be handled in one of three ways:

- append a new sighting note to the same description,
- keep a single latest description and preserve prior notes in history,
- or store a versioned description trail if the product needs an audit log.

## Main Flutter app: `fishdex/`

This is the main mobile app for the project.

### Root structure

```text
fishdex/
├── analysis_options.yaml
├── pubspec.yaml
├── README.md
├── test/
│   └── widget_test.dart
├── android/
├── ios/
├── lib/
├── assets/
└── build/
```

### Configuration files

- `analysis_options.yaml`: Dart static analysis rules.
- `pubspec.yaml`: Flutter dependencies, assets, and project metadata.
- `README.md`: base README generated by Flutter.

### `lib/`: main source code

```text
lib/
├── app.dart
├── main.dart
├── core/
│   ├── constants/
│   │   └── app_constants.dart
│   ├── providers/
│   │   └── appwrite_providers.dart
│   ├── router/
│   │   └── app_router.dart
│   ├── shell/
│   │   └── main_shell.dart
│   └── theme/
│       └── app_theme.dart
├── data/
│   ├── models/
│   │   └── identify_result.dart
│   ├── repositories/
│   │   ├── auth_repository.dart
│   │   ├── fishing_spots_repository.dart
│   │   └── sightings_repository.dart
│   └── services/
│       ├── cache_service.dart
│       ├── gamification_service.dart
│       ├── identify_service.dart
│       ├── notification_service.dart
│       └── realtime_service.dart
├── features/
│   ├── achievements/
│   │   └── presentation/
│   │       └── achievements_screen.dart
│   ├── auth/
│   │   ├── presentation/
│   │   │   ├── login_screen.dart
│   │   │   ├── register_screen.dart
│   │   │   └── splash_screen.dart
│   │   └── providers/
│   │       └── auth_provider.dart
│   ├── camera/
│   │   ├── presentation/
│   │   │   ├── camera_screen.dart
│   │   │   └── video_preview_screen.dart
│   │   ├── providers/
│   │   │   └── camera_provider.dart
│   │   └── widgets/
│   │       ├── ar_overlay.dart
│   │       └── recording_controls.dart
│   ├── collection/
│   │   └── presentation/
│   │       └── collection_screen.dart
│   ├── gallery/
│   │   └── presentation/
│   │       └── gallery_screen.dart
│   ├── identify/
│   │   ├── presentation/
│   │   │   ├── identifying_screen.dart
│   │   │   └── result_screen.dart
│   │   └── widgets/
│   │       ├── confetti_overlay.dart
│   │       ├── fish_card.dart
│   │       ├── reunion_info.dart
│   │       └── xp_animation.dart
│   ├── map/
│   │   ├── presentation/
│   │   │   └── map_screen.dart
│   │   ├── providers/
│   │   │   └── map_providers.dart
│   │   └── widgets/
│   │       ├── nearby_rare_notification.dart
│   │       ├── spot_bottom_sheet.dart
│   │       └── spot_marker.dart
│   ├── onboarding/
│   │   ├── presentation/
│   │   │   ├── onboarding_screen.dart
│   │   │   └── profile_setup_screen.dart
│   ├── profile/
│   │   ├── presentation/
│   │   │   └── profile_screen.dart
│   │   └── providers/
│   │       └── profile_setup_provider.dart
│   ├── ranking/
│   │   ├── data/
│   │   │   └── ranking_repository.dart
│   │   ├── presentation/
│   │   │   └── ranking_screen.dart
│   │   └── providers/
│   │       └── ranking_providers.dart
│   └── spots/
│       └── presentation/
│           └── quick_spot_screen.dart
├── widgets/
│   ├── error_display.dart
│   ├── fish_card_mini.dart
│   ├── loading_overlay.dart
│   └── xp_progress_bar.dart
└── main.dart
```

### What each layer does

- `main.dart`: Flutter entry point.
- `app.dart`: root widget and `MaterialApp.router` configuration.
- `core/`: shared application infrastructure.
- `data/`: models, repositories, and data/state access services.
- `features/`: functional modules by screen or domain.
- `widgets/`: global reusable components.

### Navigation and shell

- `core/router/app_router.dart`: defines the main routes and navigation with `GoRouter`.
- `core/shell/main_shell.dart`: main shell with bottom navigation.

### Themes and constants

- `core/theme/app_theme.dart`: light and dark themes.
- `core/constants/app_constants.dart`: application constants.

### Appwrite integration

- `core/providers/appwrite_providers.dart`: providers for Appwrite connectivity.
- `data/repositories/*`: access to auth, spots, and sightings.
- `data/services/*`: cache, gamification, notifications, realtime, and identification logic.

### Main screens

- Authentication: `login_screen.dart`, `register_screen.dart`, `splash_screen.dart`.
- Onboarding: `onboarding_screen.dart`, `profile_setup_screen.dart`.
- Camera: `camera_screen.dart`, `video_preview_screen.dart`.
- Identification: `identifying_screen.dart`, `result_screen.dart`.
- Map: `map_screen.dart`.
- Collection: `collection_screen.dart`.
- Ranking: `ranking_screen.dart`.
- Profile: `profile_screen.dart`.
- Gallery: `gallery_screen.dart`.
- Quick spots: `quick_spot_screen.dart`.
- Achievements: `achievements_screen.dart`.

### Screen image placeholders

Add the mobile app screenshots here. These can be hand-drawn mockups if final screenshots are not available yet.

#### Splash screen

![Splash screen placeholder](./assets/screens/splash-screen.png)

#### Login screen

![Login screen placeholder](./assets/screens/login-screen.png)

#### Register screen

![Register screen placeholder](./assets/screens/register-screen.png)

#### Onboarding screen

![Onboarding screen placeholder](./assets/screens/onboarding-screen.png)

#### Camera screen

![Camera screen placeholder](./assets/screens/camera-screen.png)

#### Identification result screen

![Identification result screen placeholder](./assets/screens/result-screen.png)

#### Map screen

![Map screen placeholder](./assets/screens/map-screen.png)

#### Collection screen

![Collection screen placeholder](./assets/screens/collection-screen.png)

#### Profile screen

![Profile screen placeholder](./assets/screens/profile-screen.png)

### Notable widgets

- Camera: `ar_overlay.dart`, `recording_controls.dart`.
- Identification: `confetti_overlay.dart`, `fish_card.dart`, `reunion_info.dart`, `xp_animation.dart`.
- Map: `nearby_rare_notification.dart`, `spot_bottom_sheet.dart`, `spot_marker.dart`.
- Global: `error_display.dart`, `fish_card_mini.dart`, `loading_overlay.dart`, `xp_progress_bar.dart`.

### Android

```text
android/
├── build.gradle
├── gradle.properties
├── settings.gradle
├── gradle/
│   └── wrapper/
│       └── gradle-wrapper.properties
└── app/
    ├── build.gradle
    └── src/
        ├── debug/
        │   └── AndroidManifest.xml
        ├── main/
        │   ├── AndroidManifest.xml
        │   ├── kotlin/
        │   │   └── com/fishdex/app/MainActivity.kt
        │   └── res/
        │       ├── drawable/
        │       │   └── launch_background.xml
        │       ├── drawable-v21/
        │       │   └── launch_background.xml
        │       ├── mipmap-hdpi/ic_launcher.png
        │       ├── mipmap-mdpi/ic_launcher.png
        │       ├── mipmap-xhdpi/ic_launcher.png
        │       ├── mipmap-xxhdpi/ic_launcher.png
        │       ├── mipmap-xxxhdpi/ic_launcher.png
        │       └── values/
        │           └── styles.xml
        │       └── values-night/
        │           └── styles.xml
        └── profile/
            └── AndroidManifest.xml
```

### iOS

```text
ios/
├── Flutter/
│   ├── flutter_export_environment.sh
│   └── Generated.xcconfig
└── Runner/
    ├── GeneratedPluginRegistrant.h
    └── GeneratedPluginRegistrant.m
```

### Assets

```text
assets/
├── animations/
├── icons/
└── images/
```

### Build

`build/` contains generated artifacts from Flutter and native packages. It is not hand-written source code, but it is part of the generated workspace output during compilation.

Visible subtrees in this workspace:

- `build/0c1363a44f94d0604429c0b7e0fbf610/`
- `build/app/`
- `build/camera_android_camerax/`
- `build/device_info_plus/`
- `build/flutter_local_notifications/`
- `build/flutter_plugin_android_lifecycle/`
- `build/flutter_web_auth_2/`
- `build/geocoding_android/`
- `build/geolocator_android/`
- `build/image_picker_android/`
- `build/package_info_plus/`
- `build/path_provider_android/`
- `build/permission_handler_android/`
- `build/shared_preferences_android/`
- `build/sqflite_android/`
- `build/url_launcher_android/`
- `build/video_player_android/`

## Static web portal: `cultura climatica/`

This directory contains a static website that is independent from the rest of the system.

### Structure

```text
cultura climatica/
├── app.js
├── index.html
├── styles.css
└── assets/
    ├── equipo.jpeg
    └── logo.png
```

### What each part does

- `index.html`: base page structure.
- `styles.css`: portal visual styles.
- `app.js`: interface logic and portal data.
- `assets/`: static graphic resources.

## Documentation: `docs/`

```text
docs/
└── appwrite_setup.md
```

### `appwrite_setup.md`

Appwrite Console setup guide for the FishDex project.
It includes:

- project creation,
- database,
- collections,
- storage buckets,
- API key,
- deployment platforms,
- initial setup steps.

## Scripts: `scripts/`

```text
scripts/
├── deploy_model.sh
├── evaluate.py
├── export_data.py
├── preprocess.py
├── requirements.txt
├── run_pipeline.sh
└── train.py
```

### What each script does

- `deploy_model.sh`: model deployment.
- `evaluate.py`: model or pipeline evaluation.
- `export_data.py`: data export for training or analysis.
- `preprocess.py`: data cleaning and preprocessing.
- `requirements.txt`: Python pipeline dependencies.
- `run_pipeline.sh`: chained pipeline execution.
- `train.py`: main model training.

## How everything connects

1. `fishdex/` is the app used by the end user.
2. `ai-server/` processes videos and returns identifications.
3. `docker-compose.yml` starts the AI backend and Appwrite locally.
4. `scripts/` prepares and trains the model that powers the server.
5. `cultura climatica/` works as an independent portal.
6. `docs/` documents the environment setup and operation.

## Scope note

This document prioritizes the structure that is useful for development and maintenance. The generated artifacts inside `build/` can grow significantly during future compilations; for that reason, only the currently visible subtrees are listed here and that folder is marked as generated.
