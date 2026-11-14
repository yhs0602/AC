#!/bin/sh
set -eu
cd "$(dirname "$0")"
binary="$PWD/build/Products/Release/assaultcube.app/Contents/MacOS/assaultcube"
if [ ! -x "$binary" ]; then
    echo "Build the game first: ./build-macos.sh" >&2
    exit 1
fi
exec "$binary" --home="$HOME/.assaultcube/v1.3" --init "$@"
