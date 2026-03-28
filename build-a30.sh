#!/bin/bash
set -e

OUTPUT_DIR="${OUTPUT_DIR:-/output}"

echo "=== Building llama.cpp for A30 (armhf / glibc 2.23) ==="

# Clone llama.cpp
if [ ! -d "llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi

cd llama.cpp

# Cross-compilation environment
export CCACHE_DIR="${CCACHE_DIR:-/ccache}"
export PATH="/opt/a30/bin:${PATH}"
SYSROOT=/opt/a30/arm-a30-linux-gnueabihf/sysroot

cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE=/tmp/a30-toolchain.cmake \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DCMAKE_C_FLAGS="-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2" \
    -DCMAKE_CXX_FLAGS="-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2" \
    -DCMAKE_EXE_LINKER_FLAGS="-static-libstdc++" \
    -DGGML_NATIVE=OFF \
    -DLLAMA_CURL=OFF \
    -DLLAMA_OPENSSL=OFF \
    -DGGML_OPENMP=OFF

cmake --build build --target llama-server llama-cli -j$(nproc)

# Collect output
mkdir -p "$OUTPUT_DIR/lib32"

# Binaries (named *32 for multi-arch app layout)
cp build/bin/llama-server "$OUTPUT_DIR/llama-server32"
cp build/bin/llama-cli "$OUTPUT_DIR/llama-cli32"
/opt/a30/bin/arm-a30-linux-gnueabihf-strip "$OUTPUT_DIR/llama-server32" "$OUTPUT_DIR/llama-cli32"

# llama.cpp shared libs
for soname in libggml-base.so.0 libggml-cpu.so.0 libggml.so.0 libllama.so.0 libmtmd.so.0; do
    real=$(find build/bin -name "${soname}*" ! -type l | head -1)
    if [ -n "$real" ]; then
        cp "$real" "$OUTPUT_DIR/lib32/$soname"
    fi
done

# Runtime libs (pre-collected in Dockerfile to avoid buildroot wrapper confusion)
cp /opt/a30-runtime-libs/* "$OUTPUT_DIR/lib32/"

chmod +x "$OUTPUT_DIR/llama-server32" "$OUTPUT_DIR/llama-cli32"

echo "=== Build complete ==="
