#!/usr/bin/env python3
"""SpruceChat - A local AI chat app for Miyoo A30 running on spruceOS"""

import http.client
import json
import os
import struct
import threading
import time

import sdl2
import sdl2.ext
import sdl2.sdlttf

# ── Constants ──────────────────────────────────────────────────────────────────

SCREEN_W = int(os.environ.get("SCREEN_WIDTH", 640))
SCREEN_H = int(os.environ.get("SCREEN_HEIGHT", 480))
SCREEN_ROTATION = int(os.environ.get("SCREEN_ROTATION", 0))
APP_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = "/mnt/SDCARD/Themes/SPRUCE/nunwen.ttf"
FONT_PATH_FB = "/mnt/SDCARD/App/PixelReader/resources/fonts/DejaVuSans.ttf"
MODEL_PATH = os.path.join(APP_DIR, "models", "qwen2.5-0.5b-instruct-q4_0.gguf")
MODEL_PATH_FB = os.path.join(APP_DIR, "models", "qwen2.5-0.5b-instruct-q2_k.gguf")
SAVES_DIR = "/mnt/SDCARD/Saves/spruce/SpruceChat"
HISTORY_PATH = os.path.join(SAVES_DIR, "chat_history.jsonl")
SERVER_LOG = os.path.join(APP_DIR, "server.log")
MAX_HISTORY = 12
CTX_TOKENS = 1024
MAX_TOKENS = 64
PORT = 8086

# Colors
BG       = (16, 16, 22, 255)
CHAT_BG  = (20, 20, 28, 255)
HEADER   = (24, 24, 34, 255)
LINE     = (50, 50, 70, 255)
C_USER   = (130, 190, 255, 255)
C_AI     = (160, 220, 170, 255)
C_DIM    = (70, 70, 85, 255)
C_TEXT   = (210, 210, 220, 255)
BUB_USER = (30, 40, 58, 255)
BUB_AI   = (28, 38, 32, 255)
KEY_BG   = (32, 32, 46, 255)
KEY_SEL  = (65, 120, 220, 255)
KEY_TXT  = (180, 180, 195, 255)
INPUT_BG = (26, 26, 38, 255)
ACCENT   = (75, 130, 230, 255)

# Input
EVENT_FMT = 'llHHI'
EVENT_SZ = struct.calcsize(EVENT_FMT)
INPUT_DEV = "/dev/input/event3"
KEY_A, KEY_B, KEY_X, KEY_Y = 57, 29, 42, 56
KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT = 103, 108, 105, 106
KEY_L1, KEY_R1, KEY_START, KEY_SELECT, KEY_MENU = 15, 14, 28, 97, 1
EV_KEY, KEY_PRESS = 1, 1

SYSTEM_PROMPT = {
    "role": "system",
    "content": "You are SpruceChat, a tiny AI on a Miyoo A30 handheld. 0.5B parameters of pure spruce energy. Keep responses short. You're on a tiny chip and that's part of the charm."
}

# ── Store ─────────────────────────────────────────────────────────────────────

class Store:
    def __init__(self):
        self.msgs = []
        os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
        try:
            with open(HISTORY_PATH) as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        m = json.loads(ln)
                        if m.get("role") != "system":
                            self.msgs.append(m)
            self.msgs = self.msgs[-MAX_HISTORY:]
        except (OSError, json.JSONDecodeError):
            pass

    def add(self, role, content):
        self.msgs.append({"role": role, "content": content})
        self.msgs = self.msgs[-MAX_HISTORY:]
        try:
            with open(HISTORY_PATH, "w") as f:
                for m in self.msgs:
                    f.write(json.dumps(m) + "\n")
        except OSError:
            pass

    def prompt(self):
        return [SYSTEM_PROMPT] + list(self.msgs)

    def display(self):
        return [("user" if m["role"] == "user" else "ai", m["content"]) for m in self.msgs]

    def clear(self):
        self.msgs = []
        try:
            open(HISTORY_PATH, "w").close()
        except OSError:
            pass

# ── Input ─────────────────────────────────────────────────────────────────────

class Input:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()
        self.running = True
        self.fd = None
        try:
            self.fd = os.open(INPUT_DEV, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            pass
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        while self.running:
            if not self.fd:
                time.sleep(0.1)
                continue
            try:
                data = os.read(self.fd, EVENT_SZ)
                if len(data) == EVENT_SZ:
                    _, _, t, c, v = struct.unpack(EVENT_FMT, data)
                    if t == EV_KEY and v == KEY_PRESS:
                        with self.lock:
                            self.events.append(c)
            except BlockingIOError:
                time.sleep(0.016)
            except OSError:
                time.sleep(0.05)

    def get(self):
        with self.lock:
            e = list(self.events)
            self.events.clear()
        return e

    def close(self):
        self.running = False
        if self.fd:
            os.close(self.fd)

# ── Graphics ──────────────────────────────────────────────────────────────────

class Gfx:
    def __init__(self):
        sdl2.ext.init(controller=False)
        sdl2.sdlttf.TTF_Init()
        self.rotated = SCREEN_ROTATION == 270
        if self.rotated:
            win_size = (SCREEN_H, SCREEN_W)
        else:
            win_size = (SCREEN_W, SCREEN_H)
        self.win = sdl2.ext.Window("SpruceChat", size=win_size,
                                    flags=sdl2.SDL_WINDOW_FULLSCREEN)
        self.win.show()
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"1")
        self.ren = sdl2.ext.Renderer(self.win, flags=sdl2.SDL_RENDERER_ACCELERATED)
        self.r = self.ren.sdlrenderer

        # Offscreen canvas (always renders at SCREEN_W x SCREEN_H)
        self.canvas = sdl2.SDL_CreateTexture(self.r, sdl2.SDL_PIXELFORMAT_ARGB8888,
                                              sdl2.SDL_TEXTUREACCESS_TARGET, SCREEN_W, SCREEN_H)
        if self.rotated:
            self.rot_tex = sdl2.SDL_CreateTexture(self.r, sdl2.SDL_PIXELFORMAT_ARGB8888,
                                                   sdl2.SDL_TEXTUREACCESS_TARGET, SCREEN_H, SCREEN_W)
        sdl2.SDL_SetRenderTarget(self.r, self.canvas)

        fp = FONT_PATH if os.path.exists(FONT_PATH) else FONT_PATH_FB
        self.f_sm = sdl2.sdlttf.TTF_OpenFont(fp.encode(), 16)
        self.f_md = sdl2.sdlttf.TTF_OpenFont(fp.encode(), 20)
        self.f_lg = sdl2.sdlttf.TTF_OpenFont(fp.encode(), 26)

    def clear(self, c=BG):
        sdl2.SDL_SetRenderTarget(self.r, self.canvas)
        sdl2.SDL_SetRenderDrawColor(self.r, *c)
        sdl2.SDL_RenderClear(self.r)

    def present(self):
        if self.rotated:
            # Rotate canvas into cached texture (A30: 270°)
            sdl2.SDL_SetRenderTarget(self.r, self.rot_tex)
            sdl2.SDL_SetRenderDrawColor(self.r, 0, 0, 0, 255)
            sdl2.SDL_RenderClear(self.r)
            dst = sdl2.SDL_Rect((SCREEN_H - SCREEN_W) // 2, (SCREEN_W - SCREEN_H) // 2,
                                 SCREEN_W, SCREEN_H)
            ctr = sdl2.SDL_Point(SCREEN_W // 2, SCREEN_H // 2)
            sdl2.SDL_RenderCopyEx(self.r, self.canvas, None, dst, 270, ctr, sdl2.SDL_FLIP_NONE)
            sdl2.SDL_SetRenderTarget(self.r, None)
            sdl2.SDL_RenderCopy(self.r, self.rot_tex, None, None)
        else:
            # No rotation — blit canvas directly
            sdl2.SDL_SetRenderTarget(self.r, None)
            sdl2.SDL_RenderCopy(self.r, self.canvas, None, None)
        sdl2.SDL_RenderPresent(self.r)
        sdl2.SDL_SetRenderTarget(self.r, self.canvas)

    def rect(self, x, y, w, h, c):
        sdl2.SDL_SetRenderDrawColor(self.r, *c)
        sdl2.SDL_RenderFillRect(self.r, sdl2.SDL_Rect(int(x), int(y), int(w), int(h)))

    def text(self, s, x, y, font=None, color=C_TEXT, wrap=0):
        if not s:
            return 0, 0
        font = font or self.f_md
        c = sdl2.SDL_Color(*color)
        if wrap > 0:
            sf = sdl2.sdlttf.TTF_RenderUTF8_Blended_Wrapped(font, s.encode('utf-8'), c, int(wrap))
        else:
            sf = sdl2.sdlttf.TTF_RenderUTF8_Blended(font, s.encode('utf-8'), c)
        if not sf:
            return 0, 0
        tx = sdl2.SDL_CreateTextureFromSurface(self.r, sf)
        w, h = sf.contents.w, sf.contents.h
        sdl2.SDL_RenderCopy(self.r, tx, None, sdl2.SDL_Rect(int(x), int(y), w, h))
        sdl2.SDL_DestroyTexture(tx)
        sdl2.SDL_FreeSurface(sf)
        return w, h

    def destroy(self):
        if self.rotated:
            sdl2.SDL_DestroyTexture(self.rot_tex)
        sdl2.SDL_DestroyTexture(self.canvas)
        for f in [self.f_sm, self.f_md, self.f_lg]:
            if f:
                sdl2.sdlttf.TTF_CloseFont(f)
        sdl2.sdlttf.TTF_Quit()
        self.ren.destroy()
        self.win.close()
        sdl2.SDL_Quit()

# ── Keyboard ──────────────────────────────────────────────────────────────────

KB_ROWS = [
    list("1234567890"), list("qwertyuiop"), list("asdfghjkl"),
    list("zxcvbnm.,"), ["SPC", "DEL", "SEND"],
]

class Keyboard:
    def __init__(self):
        self.row, self.col, self.shifted = 2, 4, False
        self.y0 = SCREEN_H - 180

    @property
    def rows(self):
        if not self.shifted:
            return KB_ROWS
        return [
            list("1234567890"), list("QWERTYUIOP"), list("ASDFGHJKL"),
            list("ZXCVBNM!?"), ["SPC", "DEL", "SEND"],
        ]

    def move(self, d):
        rows = self.rows
        if d == "up":    self.row = (self.row - 1) % len(rows)
        elif d == "down":  self.row = (self.row + 1) % len(rows)
        elif d == "left":  self.col = (self.col - 1) % len(rows[self.row])
        elif d == "right": self.col = (self.col + 1) % len(rows[self.row])
        self.col = min(self.col, len(self.rows[self.row]) - 1)

    def press(self):
        k = self.rows[self.row][self.col]
        if k == "SPC": return " "
        if k == "DEL": return "BACKSPACE"
        if k == "SEND": return "SEND"
        if self.shifted: self.shifted = False
        return k

    def draw(self, g):
        rows = self.rows
        g.rect(0, self.y0, SCREEN_W, SCREEN_H - self.y0, BG)
        g.rect(16, self.y0, SCREEN_W - 32, 1, LINE)
        g.text("A:type  B:back  Y:send  X:spc  L1:shift  R1:del",
               16, self.y0 + 4, font=g.f_sm, color=C_DIM)
        ky = self.y0 + 22
        for ri, row in enumerate(rows):
            bottom = ri == len(rows) - 1
            kw = 80 if bottom else 42
            gap = 3
            tw = len(row) * kw + (len(row) - 1) * gap
            sx = (SCREEN_W - tw) // 2
            for ci, key in enumerate(row):
                x = sx + ci * (kw + gap)
                y = ky + ri * 31
                sel = ri == self.row and ci == self.col
                g.rect(x, y, kw, 28, KEY_SEL if sel else KEY_BG)
                g.text(key, x + kw // 2 - len(key) * 4, y + 5,
                       font=g.f_sm, color=(255, 255, 255, 255) if sel else KEY_TXT)

# ── AI Engine ─────────────────────────────────────────────────────────────────

class AI:
    def __init__(self):
        self.generating = False
        self.response = ""
        self.toks = 0
        self.tps = 0.0
        self.t0 = 0
        self._conn = None
        self.ok = self._health()

    def _health(self):
        try:
            c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1)
            c.request("GET", "/health")
            r = c.getresponse()
            c.close()
            return r.status == 200
        except Exception:
            return False

    def generate(self, msgs, on_tok, on_done):
        self.generating = True
        self.response = ""
        self.toks = 0
        self.tps = 0.0
        self.t0 = time.time()
        threading.Thread(target=self._stream, args=(msgs, on_tok, on_done), daemon=True).start()

    def _prompt(self, msgs):
        p = ""
        for m in msgs:
            p += f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n"
        return p + "<|im_start|>assistant\n"

    def _stream(self, msgs, on_tok, on_done):
        payload = json.dumps({
            "prompt": self._prompt(msgs),
            "n_predict": MAX_TOKENS, "temperature": 0.7, "top_k": 20, "top_p": 0.9,
            "stream": True, "stop": ["<|im_end|>", "<|endoftext|>", "<|im_start|>"],
            "cache_prompt": True,
        }).encode()
        first = 0
        try:
            self._conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=300)
            self._conn.request("POST", "/completion", body=payload,
                               headers={"Content-Type": "application/json"})
            resp = self._conn.getresponse()
            buf = b""
            while self.generating:
                ch = resp.read(1)
                if not ch:
                    break
                buf += ch
                if ch == b"\n":
                    line = buf.decode("utf-8", errors="replace").strip()
                    buf = b""
                    if line.startswith("data: "):
                        try:
                            d = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        tok = d.get("content", "")
                        if tok:
                            if not first:
                                first = time.time()
                            self.response += tok
                            self.toks += 1
                            dt = time.time() - first
                            if dt > 0:
                                self.tps = self.toks / dt
                            on_tok(self.response)
                        if d.get("stop"):
                            ts = d.get("timings", {})
                            if ts.get("predicted_per_second"):
                                self.tps = ts["predicted_per_second"]
                            break
            self._conn.close()
        except Exception as e:
            if not self.response:
                self.response = f"[Error: {e}]"
        for t in ["<|im_end|>", "<|endoftext|>", "<|im_start|>"]:
            self.response = self.response.split(t)[0]
        self.response = self.response.strip()
        self.generating = False
        on_done(self.response)

    def cancel(self):
        self.generating = False
        if self._conn:
            try: self._conn.close()
            except: pass

# ── App ───────────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        self.g = Gfx()
        self.inp = Input()
        self.kb = Keyboard()
        self.store = Store()
        self.msgs = self.store.display()
        self.text = ""
        self.scroll = 0
        self.state = "chat"
        self.running = True
        self.blink = 0
        self.t0 = 0

        self._boot()
        self.ai = AI()
        if not self.ai.ok:
            self.msgs.append(("ai", "[Server not connected. Restart the app to retry.]"))
        elif not self.msgs:
            self.msgs.append(("ai", "Hey! I'm a tiny AI on your Miyoo. What's up?"))

    def _boot(self):
        start = time.time()
        pos = 0
        lines = []
        mfile = os.path.basename(MODEL_PATH if os.path.exists(MODEL_PATH) else MODEL_PATH_FB)
        progress = 0.0
        tensor_t = 0

        while self.running:
            dt = time.time() - start
            for c in self.inp.get():
                if c in (KEY_B, KEY_MENU):
                    self.running = False
                    return

            # Health check (short timeout so UI stays responsive)
            try:
                c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=0.15)
                c.request("GET", "/health")
                r = c.getresponse()
                c.close()
                if r.status == 200:
                    lines.append("[OK] Ready! ({:.0f}s)".format(dt))
                    progress = 1.0
                    self._draw_boot(mfile, lines, progress, dt, True)
                    time.sleep(0.4)
                    return
            except Exception:
                pass

            # Read server log
            try:
                if os.path.exists(SERVER_LOG):
                    with open(SERVER_LOG) as f:
                        f.seek(pos)
                        new = f.read()
                        pos = f.tell()
                    for ln in new.splitlines():
                        ln = ln.strip()
                        if not ln:
                            continue
                        if "load_tensors:" in ln:
                            tensor_t = time.time()
                            progress = max(progress, 0.4)
                        elif "llama_model_loader" in ln:
                            progress = max(progress, min(0.3, progress + 0.01))
                        elif "print_info:" in ln:
                            progress = max(progress, min(0.4, progress + 0.005))
                        elif "llama_context:" in ln:
                            progress = max(progress, 0.85)
                        elif "model loaded" in ln.lower():
                            progress = max(progress, 0.93)
                        elif "listening" in ln.lower():
                            progress = 0.97
                        if len(ln) > 68:
                            ln = ln[:65] + "..."
                        lines.append(ln)
            except OSError:
                pass

            # Time-based interpolation during tensor loading
            if tensor_t:
                tp = 0.4 + min((time.time() - tensor_t) / 50.0, 1.0) * 0.45
                progress = max(progress, tp)
            elif progress < 0.05:
                progress = 0.02 + 0.01 * (dt % 3)

            self._draw_boot(mfile, lines, progress, dt, False)
            time.sleep(0.15)
            if dt > 180:
                return

    def _draw_boot(self, mfile, lines, progress, dt, ready):
        self.g.clear()
        self.g.text("SpruceChat", SCREEN_W // 2 - 76, 20, font=self.g.f_lg, color=C_TEXT)
        self.g.text(mfile, 24, 60, font=self.g.f_sm, color=C_DIM)

        spin = "|/-\\"[int(dt * 4) % 4]
        pct = int(progress * 100)
        st = "ready" if ready else f"{spin} loading {pct}%  {dt:.0f}s"
        self.g.text(st, 24, 80, font=self.g.f_sm, color=C_AI if ready else C_DIM)

        # Progress bar
        bw = SCREEN_W - 48
        self.g.rect(24, 102, bw, 3, HEADER)
        fw = int(bw * min(progress, 1.0))
        if fw > 0:
            self.g.rect(24, 102, fw, 3, C_AI if ready else ACCENT)

        # Log
        vis = lines[-16:]
        y = 116
        for ln in vis:
            col = C_AI if ln.startswith("[OK]") else (70, 70, 90, 255)
            self.g.text(ln, 20, y, font=self.g.f_sm, color=col)
            y += 16

        self.g.text("B: cancel", 16, SCREEN_H - 20, font=self.g.f_sm, color=C_DIM)
        self.g.present()

    def _input(self):
        for c in self.inp.get():
            if c == KEY_MENU:
                self.ai.cancel(); self.running = False; return
            if self.ai.generating:
                if c == KEY_B:
                    self.ai.cancel(); self.running = False; return
                continue
            if self.state == "keyboard":
                self._kb_input(c)
            else:
                self._chat_input(c)

    def _chat_input(self, c):
        if c == KEY_A: self.state = "keyboard"
        elif c == KEY_B: self.running = False
        elif c == KEY_UP: self.scroll = max(0, self.scroll - 30)
        elif c == KEY_DOWN: self.scroll = max(0, self.scroll + 30)
        elif c == KEY_SELECT:
            self.store.clear()
            self.msgs = [("ai", "Chat cleared.")]
            self.scroll = 0

    def _kb_input(self, c):
        if c == KEY_UP: self.kb.move("up")
        elif c == KEY_DOWN: self.kb.move("down")
        elif c == KEY_LEFT: self.kb.move("left")
        elif c == KEY_RIGHT: self.kb.move("right")
        elif c == KEY_A:
            r = self.kb.press()
            if r == "BACKSPACE": self.text = self.text[:-1]
            elif r == "SEND": self._send()
            else: self.text += r
        elif c == KEY_B:
            if self.text: self.text = self.text[:-1]
            else: self.state = "chat"
        elif c == KEY_X: self.text += " "
        elif c in (KEY_Y, KEY_START): self._send()
        elif c == KEY_L1: self.kb.shifted = not self.kb.shifted
        elif c == KEY_R1: self.text = self.text[:-1]
        elif c == KEY_MENU: self.running = False

    def _send(self):
        t = self.text.strip()
        if not t or self.ai.generating:
            return
        self.text = ""
        self.state = "chat"
        self.msgs.append(("user", t))
        self.store.add("user", t)
        self.msgs.append(("ai", ""))
        self.t0 = time.time()
        self.ai.generate(self.store.prompt(), self._on_tok, self._on_done)

    def _on_tok(self, partial):
        if self.msgs and self.msgs[-1][0] == "ai":
            self.msgs[-1] = ("ai", partial)
        self.scroll = max(0, self._total_h() - self._chat_h())

    def _on_done(self, resp):
        if self.msgs and self.msgs[-1][0] == "ai":
            self.msgs[-1] = ("ai", resp)
        else:
            self.msgs.append(("ai", resp))
        self.store.add("assistant", resp)
        self.scroll = max(0, self._total_h() - self._chat_h())

    def _chat_h(self):
        return (self.kb.y0 - 76) if self.state == "keyboard" else (SCREEN_H - 36)

    def _total_h(self):
        h = 8
        for _, t in self.msgs:
            h += max(1, len(t) // 48 + 1) * 22 + 20
        return h

    def _draw(self):
        self.g.clear()
        self.blink = (self.blink + 1) % 60

        # Header
        self.g.rect(0, 0, SCREEN_W, 34, HEADER)
        self.g.rect(0, 34, SCREEN_W, 1, LINE)

        if self.ai.generating:
            dt = int(time.time() - self.t0) if self.t0 else 0
            sp = "|/-\\"[(self.blink // 4) % 4]
            if self.ai.response:
                self.g.text(f"{sp} {self.ai.toks}tok {self.ai.tps:.1f}t/s {dt}s",
                            14, 7, color=C_AI)
            else:
                self.g.text(f"{sp} thinking... {dt}s", 14, 7, color=C_DIM)
        else:
            self.g.text("SpruceChat", 14, 6, color=C_TEXT)
            if self.state == "chat":
                self.g.text("A:type  B:quit  SEL:clear", SCREEN_W - 220, 10, font=self.g.f_sm, color=C_DIM)

        # Chat area
        top = 36
        bot = self._chat_h() + top
        self.g.rect(0, top, SCREEN_W, bot - top, CHAT_BG)

        y = top + 8 - self.scroll
        mw = SCREEN_W - 40

        for role, txt in self.msgs:
            if y > bot:
                break
            if not txt and role == "ai" and self.ai.generating:
                txt = "..."

            # Estimate height to skip offscreen
            est = max(1, len(txt or " ") // 48 + 1) * 22 + 20
            if y + est < top - 10:
                y += est
                continue

            tc = C_USER if role == "user" else C_AI
            bc = BUB_USER if role == "user" else BUB_AI

            # Label
            lbl = "you" if role == "user" else "spruce"
            self.g.text(lbl, 18, y, font=self.g.f_sm, color=C_DIM)
            y += 15

            # Bubble + text (render once, use height)
            self.g.rect(14, y, SCREEN_W - 28, est - 18, bc)
            _, th = self.g.text(txt or " ", 22, y + 4, color=tc, wrap=mw)
            y += max(th + 8, est - 18) + 6

        # Input bar
        if self.state == "keyboard":
            iy = self.kb.y0 - 38
            self.g.rect(0, iy, SCREEN_W, 1, LINE)
            self.g.rect(0, iy + 1, SCREEN_W, 36, INPUT_BG)
            cur = "_" if self.blink < 30 else " "
            self.g.text(self.text + cur, 16, iy + 8, color=C_TEXT)
            self.kb.draw(self.g)

        self.g.present()

    def run(self):
        try:
            while self.running:
                self._input()
                self._draw()
                time.sleep(0.05)
        finally:
            self.inp.close()
            self.g.destroy()

if __name__ == "__main__":
    App().run()
