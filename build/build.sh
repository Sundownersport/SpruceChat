#!/bin/bash
# Build llama-server and llama-cli for ARMv7 NEON (Miyoo A30)
# Requires Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Cloning llama.cpp ==="
TMPDIR=$(mktemp -d)
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$TMPDIR/llama.cpp"
cp "$SCRIPT_DIR/Dockerfile" "$TMPDIR/llama.cpp/"

echo "=== Building for ARMv7 NEON ==="
cd "$TMPDIR/llama.cpp"
docker build -f Dockerfile -t llama-a30-build .

echo "=== Extracting binaries ==="
CID=$(docker create llama-a30-build)
docker cp "$CID:/build/build/bin/llama-server" "$REPO_DIR/llama-server"
docker cp "$CID:/build/build/bin/llama-cli" "$REPO_DIR/llama-cli"
docker rm "$CID"

echo "=== Extracting shared libraries ==="
mkdir -p "$REPO_DIR/lib"
CID=$(docker create llama-a30-build)
for lib in libggml-base.so.0 libggml-cpu.so.0 libggml.so.0 libllama.so.0 libmtmd.so.0; do
    # Find the versioned file and copy as the soname
    FULL=$(docker run --rm llama-a30-build find /build/build/bin -name "${lib}*" -not -type l | head -1)
    if [ -n "$FULL" ]; then
        docker cp "$CID:$FULL" "$REPO_DIR/lib/$lib"
    fi
done
docker rm "$CID"

# Extract ARM glibc from cross-compiler sysroot
CID=$(docker create llama-a30-build)
for lib in ld-linux-armhf.so.3 libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libgcc_s.so.1; do
    docker cp "$CID:/usr/arm-linux-gnueabihf/lib/$lib" "$REPO_DIR/lib/$lib" 2>/dev/null || true
done
# libstdc++ may be a symlink, get the real file
REAL=$(docker run --rm llama-a30-build readlink -f /usr/arm-linux-gnueabihf/lib/libstdc++.so.6)
docker cp "$CID:$REAL" "$REPO_DIR/lib/libstdc++.so.6"
docker rm "$CID"

echo "=== Cleaning up ==="
rm -rf "$TMPDIR"

echo "=== Done ==="
echo "Binaries: $REPO_DIR/llama-server, $REPO_DIR/llama-cli"
echo "Libraries: $REPO_DIR/lib/"
chmod +x "$REPO_DIR/llama-server" "$REPO_DIR/llama-cli" "$REPO_DIR/lib/ld-linux-armhf.so.3"
