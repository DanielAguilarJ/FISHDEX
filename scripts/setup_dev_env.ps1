$toolsDir = "C:\Users\Student\dev_tools"
if (!(Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir
}

# 1. Download and Extract JDK 17
if (!(Test-Path "$toolsDir\jdk-17")) {
    Write-Host "Downloading JDK 17..."
    $jdkZip = "$toolsDir\jdk17.zip"
    curl.exe -L "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse" -o $jdkZip

    Write-Host "Extracting JDK 17..."
    $jdkTemp = "$toolsDir\jdk_temp"
    Expand-Archive -Path $jdkZip -DestinationPath $jdkTemp -Force
    $jdkFolder = (Get-ChildItem -Path $jdkTemp -Directory)[0].FullName
    Move-Item -Path $jdkFolder -Destination "$toolsDir\jdk-17" -Force
    Remove-Item -Path $jdkTemp -Recurse -Force
    Remove-Item -Path $jdkZip -Force
} else {
    Write-Host "JDK 17 already exists."
}

# 2. Download and Extract Flutter
if (!(Test-Path "$toolsDir\flutter")) {
    Write-Host "Downloading Flutter..."
    $flutterZip = "$toolsDir\flutter.zip"
    curl.exe -L "https://storage.googleapis.com/flutter_infra_release/releases/stable/windows/flutter_windows_3.24.0-stable.zip" -o $flutterZip

    Write-Host "Extracting Flutter..."
    Expand-Archive -Path $flutterZip -DestinationPath $toolsDir -Force
    Remove-Item -Path $flutterZip -Force
} else {
    Write-Host "Flutter already exists."
}

# 3. Download and Extract Android Command Line Tools
$sdkDir = "$toolsDir\android-sdk"
$latestDir = "$sdkDir\cmdline-tools\latest"
if (!(Test-Path $latestDir)) {
    Write-Host "Downloading Android command line tools..."
    $cmdlineZip = "$toolsDir\cmdline.zip"
    curl.exe -L "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -o $cmdlineZip

    Write-Host "Extracting Android command line tools..."
    $cmdlineTemp = "$toolsDir\cmdline_temp"
    Expand-Archive -Path $cmdlineZip -DestinationPath $cmdlineTemp -Force
    New-Item -ItemType Directory -Path $latestDir -Force
    Move-Item -Path "$cmdlineTemp\cmdline-tools\*" -Destination $latestDir -Force
    Remove-Item -Path $cmdlineTemp -Recurse -Force
    Remove-Item -Path $cmdlineZip -Force
} else {
    Write-Host "Android command line tools already exist."
}

Write-Host "Setup completed successfully!"
