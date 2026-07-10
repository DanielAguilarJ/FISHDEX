$env:JAVA_HOME = "C:\Users\Student\dev_tools\jdk-17"
$env:ANDROID_HOME = "C:\Users\Student\dev_tools\android-sdk"
$sdkManager = "C:\Users\Student\dev_tools\android-sdk\cmdline-tools\latest\bin\sdkmanager.bat"

Write-Host "Installing platform-tools, build-tools, and platform 34..."
# We pass --sdk_root explicitly to avoid any configuration warnings
& $sdkManager --sdk_root=$env:ANDROID_HOME "platform-tools" "build-tools;34.0.0" "platforms;android-34"

Write-Host "Accepting Android SDK licenses..."
# Pipe multiple "y" answers to accept all licenses
, "y" * 30 | & $sdkManager --sdk_root=$env:ANDROID_HOME --licenses

Write-Host "Configuring Flutter Android SDK path..."
$env:PATH = "C:\Users\Student\dev_tools\flutter\bin;C:\Users\Student\dev_tools\jdk-17\bin;$env:PATH"
& flutter config --android-sdk $env:ANDROID_HOME
& flutter config --jdk-dir $env:JAVA_HOME

Write-Host "Running flutter doctor..."
& flutter doctor
