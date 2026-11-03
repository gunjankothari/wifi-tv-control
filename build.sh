#!/bin/sh
# Builds TVRemote.app (menu bar app). Run from the project folder.
set -e
swift build -c release
APP=TVRemote.app
rm -rf $APP && mkdir -p $APP/Contents/MacOS
cp .build/release/TVRemote $APP/Contents/MacOS/
cat > $APP/Contents/Info.plist <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>TVRemote</string>
<key>CFBundleIdentifier</key><string>local.tvremote</string>
<key>CFBundleExecutable</key><string>TVRemote</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
<key>NSMicrophoneUsageDescription</key><string>TV Remote sends your Mac microphone sound to a TV along with the camera.</string>
<key>NSCameraUsageDescription</key><string>TV Remote streams your Mac camera to a TV when you switch it on.</string>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PL
codesign --force --sign - $APP
echo "Built $APP"
