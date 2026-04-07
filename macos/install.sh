#!/usr/bin/env bash
# Build and install YtmMediaBridge for macOS AirPods / media key support.
# Usage: ./macos/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SRC="$SCRIPT_DIR/YtmMediaBridge.app"
APP_DST="$HOME/.local/share/YtmMediaBridge.app"
PLIST_NAME="com.justin.ytm-media-bridge"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "Building ytm-media-bridge..."
swiftc -parse-as-library \
    -o "$APP_SRC/Contents/MacOS/ytm-media-bridge" \
    "$APP_SRC/Contents/MacOS/ytm-media-bridge.swift" \
    -framework Cocoa -framework MediaPlayer

echo "Installing to $APP_DST..."
mkdir -p "$(dirname "$APP_DST")"
rm -rf "$APP_DST"
cp -R "$APP_SRC" "$APP_DST"
# Remove source file from installed copy
rm -f "$APP_DST/Contents/MacOS/ytm-media-bridge.swift"

echo "Installing LaunchAgent..."
cat > "$PLIST_DST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$APP_DST</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/ytm-media-bridge.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/ytm-media-bridge.log</string>
</dict>
</plist>
EOF

# Restart the bridge
launchctl bootout "gui/$(id -u)/$PLIST_NAME" 2>/dev/null || true
pkill -f YtmMediaBridge 2>/dev/null || true
sleep 0.5
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

echo "Done. YtmMediaBridge is running."
echo "Logs: /tmp/ytm-media-bridge.log"
