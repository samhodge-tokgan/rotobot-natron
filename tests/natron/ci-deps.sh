#!/usr/bin/env bash
# System libraries the official Natron 2.5.0 Linux build loads from the host
# (everything else is bundled), plus what tests/natron/ci.sh itself uses.
# For a bare Ubuntu 22.04 / Debian 12 container. NatronRenderer -t needs no X
# server, only these client libraries.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  ca-certificates curl xz-utils python3 \
  libgl1 libglu1-mesa libopengl0 libgomp1 libbsd0 \
  libx11-6 libxext6 libxrender1 libxcursor1 libxfixes3 libxinerama1 libxi6 libxrandr2 \
  libsm6 libice6 libasound2 >/dev/null
