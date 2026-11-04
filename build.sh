#!/bin/sh
# Builds TVRemote.app (menu bar app). Run from the project folder.
#   ./build.sh            quick build that uses the helper in helper/.venv (for development)
#   ./build.sh --bundle   also bundles the helper inside the app (needs: pip install -r helper/requirements.txt pyinstaller)
#   VERSION=1.2.3 ./build.sh --bundle   stamps the version into the app
set -e
VERSION=${VERSION:-0.0.0}
swift build -c release
APP=TVRemote.app
rm -rf $APP && mkdir -p $APP/Contents/MacOS $APP/Contents/Resources
cp .build/release/TVRemote $APP/Contents/MacOS/
if [ "$1" = "--bundle" ]; then
  PY=${PYTHON:-python3}
  (cd helper && $PY -m PyInstaller --noconfirm --name tvd --distpath ../.build/helper-dist --workpath ../.build/helper-work \
     --specpath ../.build/helper-work --paths . --add-data "$PWD/web:web" \
     --collect-all pychromecast --collect-all androidtvremote2 --collect-all zeroconf --collect-submodules adb_shell tvd.py)
  cp -R .build/helper-dist/tvd $APP/Contents/Resources/tvd
fi
cat > $APP/Contents/Info.plist <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>TVRemote</string>
<key>CFBundleIdentifier</key><string>local.tvremote</string>
<key>CFBundleExecutable</key><string>TVRemote</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>LSUIElement</key><true/>
<key>NSMicrophoneUsageDescription</key><string>TV Remote sends your Mac microphone sound to a TV along with the camera.</string>
<key>NSCameraUsageDescription</key><string>TV Remote streams your Mac camera to a TV when you switch it on.</string>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PL
codesign --force --deep --sign - $APP
echo "Built $APP $VERSION"
