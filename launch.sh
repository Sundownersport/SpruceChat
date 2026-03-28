#!/bin/sh
. /mnt/SDCARD/spruce/scripts/helperFunctions.sh

APP_DIR="/mnt/SDCARD/App/SpruceChat"
export HOME="$APP_DIR"
cd "$APP_DIR"

# Platform-specific setup
# helperFunctions.sh sources the platform .cfg which sets
# LD_LIBRARY_PATH, DISPLAY_WIDTH/HEIGHT/ROTATION, B_* button codes, etc.
# Python path and PYSDL2_DLL_PATH must be set per-app.
case "$PLATFORM" in
    "A30")
        SERVER_BIN="$APP_DIR/llama-server32"
        PYTHON="/mnt/SDCARD/spruce/bin/python/bin/python3.10"
        export LD_LIBRARY_PATH="$APP_DIR/lib32:$LD_LIBRARY_PATH"
        export PYSDL2_DLL_PATH="/mnt/SDCARD/spruce/a30/sdl2"
        ;;
    "Brick"|"SmartPro"|"SmartProS")
        SERVER_BIN="$APP_DIR/llama-server"
        PYTHON="/mnt/SDCARD/spruce/flip/bin/python3.10"
        export LD_LIBRARY_PATH="$APP_DIR/lib:$LD_LIBRARY_PATH"
        export PYSDL2_DLL_PATH="/mnt/SDCARD/spruce/brick/sdl2"
        ;;
    *)
        SERVER_BIN="$APP_DIR/llama-server"
        PYTHON="/mnt/SDCARD/spruce/flip/bin/python3.10"
        export LD_LIBRARY_PATH="$APP_DIR/lib:$LD_LIBRARY_PATH"
        export PYSDL2_DLL_PATH="/mnt/SDCARD/spruce/flip/lib"
        ;;
esac

# Pass display info to chat.py (from platform .cfg)
export SCREEN_WIDTH="$DISPLAY_WIDTH"
export SCREEN_HEIGHT="$DISPLAY_HEIGHT"
export SCREEN_ROTATION="${DISPLAY_ROTATION:-0}"

# Ensure loopback is up (some builds don't configure it)
ifconfig lo 127.0.0.1 up 2>/dev/null

MODEL_Q4="$APP_DIR/models/qwen2.5-0.5b-instruct-q4_0.gguf"
MODEL_Q2="$APP_DIR/models/qwen2.5-0.5b-instruct-q2_k.gguf"
PORT=8086

# Pick best available model (Q4_0 is faster on ARM NEON)
if [ -f "$MODEL_Q4" ]; then
    MODEL="$MODEL_Q4"
else
    MODEL="$MODEL_Q2"
fi

# Start persistent llama-server
SERVER_PID=""
if [ -x "$SERVER_BIN" ] && [ -f "$MODEL" ]; then
    "$SERVER_BIN" \
        -m "$MODEL" \
        -c 1024 \
        -t 4 \
        -np 1 \
        -ngl 0 \
        -b 32 \
        --port "$PORT" \
        --host 0.0.0.0 \
        > "$APP_DIR/server.log" 2>&1 &
    SERVER_PID=$!
    # Don't wait here — chat.py shows a loading screen while server starts
fi

"$PYTHON" "$APP_DIR/chat.py" > "$APP_DIR/chat.log" 2>&1

# Cleanup: kill server when app exits
if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
fi
