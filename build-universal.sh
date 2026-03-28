#!/bin/bash
set -e

OUTPUT_DIR="${OUTPUT_DIR:-/output}"

echo "=== Building llama.cpp for aarch64 (universal) ==="

# Clone llama.cpp
if [ ! -d "llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
fi

cd llama.cpp

# Cross-compilation environment
export CCACHE_DIR="${CCACHE_DIR:-/ccache}"

cat > /tmp/aarch64-toolchain.cmake <<'EOF'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
EOF

cmake -B build \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE=/tmp/aarch64-toolchain.cmake \
    -DCMAKE_C_COMPILER_LAUNCHER=ccache \
    -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
    -DCMAKE_EXE_LINKER_FLAGS="-static-libstdc++" \
    -DGGML_NATIVE=OFF \
    -DLLAMA_CURL=OFF \
    -DLLAMA_OPENSSL=OFF \
    -DGGML_OPENMP=OFF

cmake --build build --target llama-server llama-cli -j$(nproc)

# Collect output
mkdir -p "$OUTPUT_DIR/lib"

# Binaries
cp build/bin/llama-server "$OUTPUT_DIR/"
cp build/bin/llama-cli "$OUTPUT_DIR/"
aarch64-linux-gnu-strip "$OUTPUT_DIR/llama-server" "$OUTPUT_DIR/llama-cli"

# llama.cpp shared libs only (no glibc — device has ≥2.33)
for soname in libggml-base.so.0 libggml-cpu.so.0 libggml.so.0 libllama.so.0 libmtmd.so.0; do
    real=$(find build/bin -name "${soname}*" ! -type l | head -1)
    if [ -n "$real" ]; then
        cp "$real" "$OUTPUT_DIR/lib/$soname"
    fi
done

chmod +x "$OUTPUT_DIR/llama-server" "$OUTPUT_DIR/llama-cli"

echo "=== Build complete ==="
