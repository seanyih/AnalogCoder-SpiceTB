#!/usr/bin/env bash
# Install the ngspice simulator used by the testbench.
#
#   scripts/install_ngspice.sh            # try the system package manager, else build from source
#   scripts/install_ngspice.sh --source   # always build ngspice from source into third_party/ngspice
#
# A source build downloads the official ngspice release tarball (BSD-3-Clause,
# https://ngspice.sourceforge.io) and installs it into ./third_party/ngspice,
# which the testbench picks up automatically (or set $NGSPICE to any binary).
set -euo pipefail

VERSION="${NGSPICE_VERSION:-42}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="$ROOT/third_party/ngspice"

build_from_source() {
  local work
  work="$(mktemp -d)"
  echo ">> building ngspice-$VERSION from source in $work"
  local base="https://downloads.sourceforge.net/project/ngspice/ng-spice-rework"
  # current releases live in <ver>/, older ones are moved to old-releases/<ver>/
  curl -fL --retry 3 -o "$work/ngspice.tar.gz" "$base/${VERSION}/ngspice-${VERSION}.tar.gz" \
    || curl -fL --retry 3 -o "$work/ngspice.tar.gz" "$base/old-releases/${VERSION}/ngspice-${VERSION}.tar.gz"
  tar -xzf "$work/ngspice.tar.gz" -C "$work"
  cd "$work/ngspice-${VERSION}"
  # batch-mode simulator only: no X11 GUI, no readline needed
  ./configure --prefix="$PREFIX" --without-x --disable-debug --enable-xspice=no \
              --enable-cider=no --with-readline=no >/dev/null
  make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)" >/dev/null
  make install >/dev/null
  cd "$ROOT"
  rm -rf "$work"
  echo ">> installed: $PREFIX/bin/ngspice"
}

if [[ "${1:-}" != "--source" ]]; then
  if command -v ngspice >/dev/null 2>&1; then
    echo ">> ngspice already installed: $(command -v ngspice)"; ngspice -v | head -2; exit 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"
    $SUDO apt-get update -qq && $SUDO apt-get install -y -qq ngspice && exit 0
  elif command -v brew >/dev/null 2>&1; then
    brew install ngspice && exit 0
  elif command -v conda >/dev/null 2>&1; then
    conda install -y -c conda-forge ngspice && exit 0
  fi
  echo ">> no package manager install possible; falling back to a source build"
fi
build_from_source
"$PREFIX/bin/ngspice" -v | head -2
