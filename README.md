# SpruceChat

A tiny AI that lives inside your Miyoo A30.

![SpruceChat running on Miyoo A30](screenshot.jpg)

0.5 billion parameters. No internet. No cloud. Just you and a little language model vibing on a handheld gaming device running spruceOS.

It's slow. It's weird. It's running on a chip meant for playing GBA games. And honestly? That's kind of the whole point.

## What is this

SpruceChat runs [Qwen2.5-0.5B](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) entirely on-device using [llama.cpp](https://github.com/ggerganov/llama.cpp). A persistent server keeps the model loaded in RAM so after the first boot (~60s), each message just... goes. Tokens stream in one by one so you can watch it think.

The AI has the personality of a spruce tree. Patient. Unhurried. Quietly amazed by everything.

## Quick start

Download the [latest release](https://github.com/RED-BASE/SpruceChat/releases/latest) — it includes everything, model and all. Unzip it to `/mnt/SDCARD/App/` on your SD card and launch from the Apps menu.

First boot takes about a minute while the model loads into RAM. After that, you're chatting.

## Controls

| Button | What it does |
|--------|-------------|
| **A** | Open keyboard / type selected key |
| **B** | Backspace / close keyboard / quit |
| **X** | Space |
| **Y** / **START** | Send message |
| **L1** | Shift |
| **R1** | Delete |
| **SELECT** | Clear chat history |
| **MENU** | Quit |
| **D-pad** | Navigate keyboard / scroll chat |

## Performance

On the Miyoo A30 (Cortex-A7, quad-core):

- **Model load**: ~60s (one time per launch)
- **Prompt eval**: ~3 tokens/sec
- **Generation**: ~1-2 tokens/sec

It's not fast. But it streams, so you see each word appear as it thinks. A short response takes 10-30s. Longer context = slower, but it remembers more of the conversation.

## How it works

`launch.sh` boots a persistent `llama-server` with a bundled glibc (the A30's system libraries are ancient). The Python UI connects over localhost HTTP. The model stays in RAM between messages — no reloading from the SD card every time you type something.

The loopback interface isn't configured by default on the A30, so the launch script brings it up. The binaries are cross-compiled for ARMv7 with NEON from a Debian Bookworm toolchain.

## Manual setup (without release zip)

If you'd rather not use the release bundle:

**1.** Clone this repo and copy it to `/mnt/SDCARD/App/SpruceChat/`

**2.** Download the model (~409MB) into `models/`:

```
https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_0.gguf
```

**3.** Launch from the Apps menu.

## Building from source

The included binaries are pre-built for ARMv7+NEON. If you want to build yourself:

```bash
# needs Docker on an x86 host
docker run --rm -v /path/to/llama.cpp:/build debian:bookworm-slim bash -c '
  apt-get update && apt-get install -y cmake make gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf
  cat > /tmp/tc.cmake <<EOF
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)
set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)
set(CMAKE_C_FLAGS "-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2")
set(CMAKE_CXX_FLAGS "-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard -O2")
EOF
  cmake -B build -DCMAKE_TOOLCHAIN_FILE=/tmp/tc.cmake -DCMAKE_BUILD_TYPE=Release \
    -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF -DGGML_OPENMP=OFF
  cmake --build build --target llama-server llama-cli -j$(nproc)
'
```

You'll need to bundle the ARM glibc shared libs from the cross-compiler sysroot into `lib/`.

## Author

Built by [Cassius Oldenburg](mailto:connect@cassius.red)

## License

MIT
