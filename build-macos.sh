#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v brew >/dev/null 2>&1; then
    echo "Install Homebrew, then: brew install sdl2 sdl2_image libogg libvorbis" >&2
    exit 1
fi
brew_prefix="$(brew --prefix)"
for library in sdl2/lib/libSDL2.dylib sdl2_image/lib/libSDL2_image.dylib libogg/lib/libogg.dylib libvorbis/lib/libvorbisfile.dylib sdl3/lib/libSDL3.dylib; do
    if [ ! -f "$brew_prefix/opt/$library" ]; then
        echo "Missing $library. Run: brew install sdl2 sdl2_image libogg libvorbis" >&2
        exit 1
    fi
done
exec xcodebuild \
    -project source/xcode/assaultcube.xcodeproj \
    -target assaultcube \
    -configuration Release \
    SYMROOT="$PWD/build/Products" \
    HOMEBREW_PREFIX="$brew_prefix" \
    CODE_SIGNING_ALLOWED=NO \
    build "$@"
