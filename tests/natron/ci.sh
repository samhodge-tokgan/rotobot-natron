#!/usr/bin/env bash
# Headless round trip inside the official Natron 2.5.0 Linux build, on the
# synthetic document from tests/synth.py (a B-spline object turning through
# 400 degrees, a Bezier object with a missing frame, a hidden frame).
#
#   tests/natron/ci.sh [WORKDIR]
#
# Downloads Natron once into WORKDIR (default .natron-ci), checks its SHA-256,
# then runs tests/natron/roundtrip.py with both import paths.
set -euo pipefail
here="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-$here/.natron-ci}"
ver=2.5.0
tarball="Natron-$ver-Linux-x86_64-no-installer.tar.xz"
sha=1b423f983e89f6e3811fdabcf08caced3367ca24568dfdfe48a3a86c1ae95fa1
mkdir -p "$work"
if [ ! -x "$work/Natron-$ver-Linux-x86_64-no-installer/NatronRenderer" ]; then
  curl -fsSL -o "$work/$tarball" "https://github.com/NatronGitHub/Natron/releases/download/v$ver/$tarball"
  echo "$sha  $work/$tarball" | sha256sum -c -
  tar -xJf "$work/$tarball" -C "$work"
  rm -f "$work/$tarball"
fi
natron="$work/Natron-$ver-Linux-x86_64-no-installer/NatronRenderer"

python3 -c "import json, sys; sys.path[:0] = ['$here/src', '$here/tests']; import synth; json.dump(synth.document(), open('$work/synth.json', 'w'))"

rc=0
for mode in fast api; do
  echo "== $mode"
  RN_MODE=$mode RN_SRC="$here/src" RN_JSON="$work/synth.json" RN_OUT="$work/out_$mode" \
    "$natron" -t "$here/tests/natron/roundtrip.py" </dev/null 2>&1 \
    | grep -E '^(source|import|reload|export|PASS|FAIL|RESULT|  |[0-9]+ frame|warning)' | tee "$work/$mode.log" || true
  grep -q '^RESULT PASS' "$work/$mode.log" || rc=1
done
exit $rc
