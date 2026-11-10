#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../aeroscope_0.3.72_all.deb}"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT
mkdir -p "$TEMP/DEBIAN" "$TEMP/usr/lib/aeroscope" "$TEMP/usr/bin" \
         "$TEMP/usr/share/applications" "$TEMP/usr/share/icons/hicolor/scalable/apps" \
         "$TEMP/usr/share/doc/aeroscope" \
         "$TEMP/usr/share/locale/pt_BR/LC_MESSAGES"
cp -r "$ROOT/aeroscope" "$TEMP/usr/lib/aeroscope/"
find "$TEMP/usr/lib/aeroscope" -type d -name __pycache__ -prune -exec rm -rf {} +
cp -r "$ROOT/assets" "$TEMP/usr/lib/aeroscope/"
cp "$ROOT/aeroscope/locale/pt_BR/LC_MESSAGES/aeroscope.mo" "$TEMP/usr/share/locale/pt_BR/LC_MESSAGES/aeroscope.mo"
cp "$ROOT/assets/io.github.ehstbr.Aeroscope.desktop" "$TEMP/usr/share/applications/"
cp "$ROOT/assets/io.github.ehstbr.Aeroscope.svg" "$TEMP/usr/share/icons/hicolor/scalable/apps/"
cp "$ROOT/README.md" "$TEMP/usr/share/doc/aeroscope/README.md"
cp "$ROOT/LICENSE" "$TEMP/usr/share/doc/aeroscope/copyright"
cat > "$TEMP/usr/bin/aeroscope" <<'PYCODE'
#!/usr/bin/python3
import sys
sys.path.insert(0, '/usr/lib/aeroscope')
from aeroscope.ui import main
main()
PYCODE
chmod 0755 "$TEMP/usr/bin/aeroscope"
cat > "$TEMP/DEBIAN/control" <<'CONTROL'
Package: aeroscope
Version: 0.3.72
Section: science
Priority: optional
Architecture: all
Maintainer: AeroScope Contributors <noreply@localhost>
Conflicts: aeroscope-gtk
Replaces: aeroscope-gtk
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-shumate-1.0
Recommends: gir1.2-webkit-6.0, gir1.2-geoclue-2.0, geoclue-2.0
Suggests: gnome-shell-extension-appindicator
Description: AeroScope — Linux aircraft radar with Libadwaita
 Free and open-source aircraft tracker with ADSB.lol live data,
 ADSB.aero archival tracks and optional aircraft photos.
CONTROL
chmod 0644 "$TEMP/DEBIAN/control"
dpkg-deb --build --root-owner-group "$TEMP" "$OUT"
echo "$OUT"
