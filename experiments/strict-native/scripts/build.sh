#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BUILD=${XNS_BUILD_DIR:-"$ROOT/build"}
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo 'The guest build requires an x86_64 Linux host; no host interfaces are changed.' >&2
  exit 2
fi
mkdir -p "$BUILD/source" "$BUILD/artifacts"
VERSION=6.12.50
KERNEL_SHA=c435bd74d1c21fc5a950781a50d78bae2b93944144694843359948ad3afc72a5
ARCHIVE="$BUILD/source/linux-$VERSION.tar.xz"
if [[ ! -f "$ARCHIVE" ]]; then
  curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
    "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-$VERSION.tar.xz" -o "$ARCHIVE"
fi
printf '%s  %s\n' "$KERNEL_SHA" "$ARCHIVE" | sha256sum --check
KERNEL="$BUILD/source/linux-$VERSION"
if [[ ! -d "$KERNEL" ]]; then tar -xJf "$ARCHIVE" -C "$BUILD/source"; fi
make -C "$KERNEL" ARCH=x86 KCONFIG_ALLCONFIG="$ROOT/config/strict.config" allnoconfig
python3 "$ROOT/scripts/check_config.py" "$KERNEL/.config"
make -C "$KERNEL" ARCH=x86 -j"${XNS_JOBS:-$(nproc)}" bzImage
python3 "$ROOT/scripts/check_config.py" "$KERNEL/.config" "$KERNEL/include/generated/autoconf.h"
gcc -std=c11 -O2 -Wall -Wextra -static -fno-pie -no-pie \
  -ffunction-sections -fdata-sections -Wl,--gc-sections -DXNS_CRYPTO \
  "$ROOT/src/native-smoke.c" -o "$BUILD/artifacts/native-smoke" -lcrypto -ldl -pthread
"$BUILD/artifacts/native-smoke" --selftest
if readelf -l "$BUILD/artifacts/native-smoke" | grep -q INTERP; then echo 'Unexpected dynamic interpreter' >&2; exit 1; fi
gcc -O2 "$KERNEL/usr/gen_init_cpio.c" -o "$BUILD/gen_init_cpio"
cat > "$BUILD/initramfs.list" <<EOF
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
dir /proc 0755 0 0
dir /sys 0755 0 0
file /init $BUILD/artifacts/native-smoke 0755 0 0
EOF
"$BUILD/gen_init_cpio" -t 0 "$BUILD/initramfs.list" | gzip -n -9 > "$BUILD/artifacts/initramfs.cpio.gz"
cp "$KERNEL/arch/x86/boot/bzImage" "$BUILD/artifacts/bzImage"
cp "$KERNEL/.config" "$BUILD/artifacts/kernel.config"
openssl version -a > "$BUILD/artifacts/openssl-version.txt"
dpkg-query -W gcc libc6-dev libssl-dev qemu-system-x86 > "$BUILD/artifacts/build-packages.txt"
sha256sum "$BUILD/artifacts/"* > "$BUILD/artifacts/build-sha256.txt"
echo 'Build complete. This is not a guest-run result; run scripts/run.py next.'
