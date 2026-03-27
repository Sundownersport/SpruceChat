FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    cmake \
    make \
    gcc-arm-linux-gnueabihf \
    g++-arm-linux-gnueabihf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . /build/

RUN cat > /build/arm32-toolchain.cmake <<'TOOLCHAIN'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_C_FLAGS "-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2")
set(CMAKE_CXX_FLAGS "-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2")
TOOLCHAIN

RUN cmake -B build \
    -DCMAKE_TOOLCHAIN_FILE=/build/arm32-toolchain.cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=OFF \
    -DLLAMA_CURL=OFF \
    -DGGML_OPENMP=OFF \
    && cmake --build build --target llama-server llama-cli -j$(nproc)
