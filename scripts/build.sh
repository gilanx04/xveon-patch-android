#!/usr/bin/env bash
#
# Build XVeon 9.1 patched APK dari APK original.
#
# Pemakaian:
#   KS=my.jks KS_PASS=secret KEY_PASS=secret ./scripts/build.sh XVeon-9.1-original.apk
#
# Variabel opsional:
#   WORK=build          direktori kerja
#   OUT=XVeon-9.1-patched.apk
#   KS_ALIAS=xveon
#
set -euo pipefail

APK_IN="${1:-XVeon-9.1-original.apk}"
OUT="${OUT:-XVeon-9.1-patched.apk}"
WORK="${WORK:-build}"
KS="${KS:-}"
KS_PASS="${KS_PASS:-}"
KEY_PASS="${KEY_PASS:-$KS_PASS}"
KS_ALIAS="${KS_ALIAS:-xveon}"

die() { echo "[GAGAL] $*" >&2; exit 1; }

command -v apktool  >/dev/null || die "apktool tidak ditemukan"
command -v zipalign >/dev/null || die "zipalign tidak ditemukan"
command -v apksigner >/dev/null || die "apksigner tidak ditemukan"
[ -f "$APK_IN" ] || die "APK input tidak ada: $APK_IN"

if [ -z "$KS" ] || [ ! -f "$KS" ]; then
  die "Keystore belum diset. Buat dulu:
  keytool -genkeypair -keystore my.jks -alias xveon -keyalg RSA -keysize 2048 \\
          -validity 10000 -storepass secret -keypass secret -dname 'CN=XVeon Patch'
lalu jalankan dengan KS=my.jks KS_PASS=secret KEY_PASS=secret"
fi

rm -rf "$WORK"
mkdir -p "$WORK"

echo "==> decode"
apktool d -f "$APK_IN" -o "$WORK/dec" >"$WORK/decode.log" 2>&1 \
  || { tail -20 "$WORK/decode.log"; die "decode gagal"; }

echo "==> patch"
python3 "$(dirname "$0")/apply_patches.py" "$WORK/dec"

echo "==> rebuild"
apktool b "$WORK/dec" -o "$WORK/unsigned.apk" >"$WORK/build.log" 2>&1 \
  || { tail -20 "$WORK/build.log"; die "rebuild gagal"; }

echo "==> zipalign"
zipalign -f -p 4 "$WORK/unsigned.apk" "$WORK/aligned.apk"

echo "==> sign"
apksigner sign \
  --ks "$KS" --ks-key-alias "$KS_ALIAS" \
  --ks-pass "pass:$KS_PASS" --key-pass "pass:$KEY_PASS" \
  --out "$OUT" "$WORK/aligned.apk"

apksigner verify "$OUT" >/dev/null || die "verifikasi signature gagal"

echo
echo "Selesai: $OUT"
ls -lh "$OUT"
sha256sum "$OUT"
