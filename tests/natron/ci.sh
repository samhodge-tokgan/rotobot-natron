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
    "$natron" -t "$here/tests/natron/roundtrip.py" </dev/null >"$work/$mode.raw" 2>&1 || echo "NatronRenderer exit $?" >>"$work/$mode.raw"
  grep -E '^(source|import|reload|export|PASS|FAIL|RESULT|  |[0-9]+ frame|warning)' "$work/$mode.raw" | tee "$work/$mode.log" || true
  if ! grep -q '^RESULT PASS' "$work/$mode.log"; then
    rc=1
    echo "-- last lines from Natron ($mode):"
    grep -v '^OpenFX: loading' "$work/$mode.raw" | tail -40
  fi
done

# The launcher (rotobot-natron launcher): builds the .ntp, then reopens it.
echo "== launcher"
mkdir -p "$work/launch" && rm -f "$work/launch/"*
cp "$work/synth.json" "$work/launch/shot.json"
PYTHONPATH="$here/src" python3 -m rotobot_natron.cli launcher "$work/launch/shot.json" --package-dir "$here/src" >/dev/null
for run in build reopen; do
  "$natron" -t "$work/launch/shot_natron.py" </dev/null >"$work/launch_$run.raw" 2>&1 || true
  grep '^rotobot-natron: \(spliced\|opened\|could\)' "$work/launch_$run.raw" | tee "$work/launch_$run.log" || true
done
if grep -q 'spliced 3 shapes' "$work/launch_build.log" && grep -q '^rotobot-natron: opened' "$work/launch_reopen.log" \
   && [ -s "$work/launch/shot.ntp" ]; then
  echo "RESULT PASS launcher"
else
  rc=1
  echo "RESULT FAIL launcher"
  grep -v '^OpenFX: loading' "$work/launch_build.raw" | tail -40
fi
exit $rc
