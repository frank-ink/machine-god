#!/usr/bin/env python3
"""Machine God ChatGPT bridge (optional, opt-in).

A small local HTTP service that drives the ChatGPT web UI in its OWN browser window and profile, so Machine God
can send a prompt and read the answer. You log in yourself in that window; the bridge never sees your password
and never touches any other browser, cookie store or profile.

WARNING: automating the ChatGPT web interface may violate OpenAI's terms of use and can get your account
suspended. Use it only if you accept that risk.

- Listens on 127.0.0.1 only, on a free port chosen at start (written to <config>/bridge.json).
- Every route except /health needs "Authorization: Bearer <token>"; the token is a random value created at setup
  and stored in <config>/bridge.token (mode 600).
- Own Chromium profile under <data>/profile (patchright), a visible window.

Routes: GET /health, GET /status, POST /login, POST /ask {prompt, timeout_s, new_chat, wait}, GET /result/{id}, POST /shutdown

Usage: chatgpt_bridge.py serve
Env: MG_CONFIG_DIR, MG_DATA_DIR (relocate), MG_BRIDGE_HEADLESS=1 (no window; ChatGPT may refuse headless browsers)
"""
import asyncio
import hmac
import json
import os
import sys
import time
from urllib.parse import urlsplit

VERSION = "1"
HOSTS = ("chatgpt.com", "www.chatgpt.com")
HOME = os.path.expanduser("~")


def _dirs():
    if sys.platform == "win32":
        cfg = os.path.join(os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming"), "machine-god")
        data = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local"), "machine-god")
    else:
        cfg = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "machine-god")
        data = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "machine-god")
    return os.environ.get("MG_CONFIG_DIR") or cfg, os.environ.get("MG_DATA_DIR") or data


CONFIG_DIR, DATA_DIR = _dirs()
INFO_FILE = os.path.join(CONFIG_DIR, "bridge.json")
TOKEN_FILE = os.path.join(CONFIG_DIR, "bridge.token")
PROFILE_DIR = os.path.join(DATA_DIR, "profile")

# ---- ChatGPT page logic ---------------------------------------------------------------------------------------
# Answer detection (measured against the live UI): the transcript is virtualised and the visible text stays flat while
# a new answer streams in, so a text-only "unchanged for N s" test is not enough. Instead: the last assistant markdown
# node, its message id (attached only once the answer is complete), its turn state (in_progress -> complete) and the
# Stop button.
INPUT_SEL = "#prompt-textarea, div.ProseMirror[contenteditable=true], [role=textbox][contenteditable=true]"
SEND_SEL = ('[data-testid="send-button"], [data-testid="composer-submit-button"], button[aria-label="Send"], '
            'button[aria-label*="Send"], button[aria-label*="Senden"], form button[type=submit]')

PAGE_STATE_JS = """() => ({
  login: !!document.querySelector('[data-testid="login-button"], [data-testid="signup-button"], a[href*="/auth/login"]'),
  box: !!document.querySelector('#prompt-textarea, div.ProseMirror[contenteditable=true], [role=textbox][contenteditable=true]')
})"""

CG_IDS_JS = """() => [...document.querySelectorAll('[data-message-id],[data-chatgpt-selection-message-id],[data-response-body]')]
  .map(e => e.getAttribute('data-message-id') || e.getAttribute('data-chatgpt-selection-message-id') || e.getAttribute('data-response-body'))"""
CG_MINE = """const mine = (el, snip) => { const t = el.closest('[data-virtualized-turn]'); if (!t) return null;
  const u = t.querySelector('[data-user-message-bubble]') || t;   // role="user" is only a "You said:" heading
  const x = (u.innerText || '').replace(/\\s+/g, ' '); return snip.every(k => x.includes(k)); };"""
CG_LAST_JS = """(snip) => { """ + CG_MINE + """
  const a = [...document.querySelectorAll('[data-markdown-text-style="assistant-message"], [data-message-author-role="assistant"]')];
  const m = a[a.length - 1];
  const stop = !!document.querySelector('[data-testid="stop-button"]') || [...document.querySelectorAll('button[aria-label]')]
    .some(b => b.offsetParent !== null && /^(stop|stopp|antwort stoppen)/i.test(b.getAttribute('aria-label')));
  if (!m) return {id: null, text: '', state: null, stop, mine: null};
  const h = m.closest('[data-message-id],[data-chatgpt-selection-message-id],[data-response-body]');
  const id = h ? (h.getAttribute('data-message-id') || h.getAttribute('data-chatgpt-selection-message-id') || h.getAttribute('data-response-body')) : null;
  const t = m.closest('[data-talvt-turn-state]');
  return {id, text: m.innerText || '', state: t ? t.getAttribute('data-talvt-turn-state') : null, stop, mine: mine(m, snip)};
}"""


def snippets(prompt):
    """Head AND tail of our own prompt must appear in the turn's user bubble (tells our turn from an older one)."""
    t = " ".join(prompt.split())
    return [t[:40], t[-40:]]


class Bridge:
    def __init__(self):
        self.pw = None
        self.ctx = None
        self.page = None
        self.lock = asyncio.Lock()
        self.start_lock = asyncio.Lock()
        self.logged_in = None
        self.last_chat = None
        self.results = {}

    # -- browser ---------------------------------------------------------------------------------------------
    async def browser(self):
        async with self.start_lock:
            if self.ctx is not None:
                try:
                    _ = self.ctx.pages
                    return self.ctx
                except Exception:
                    self.ctx = None
            from patchright.async_api import async_playwright
            os.makedirs(PROFILE_DIR, mode=0o700, exist_ok=True)
            if self.pw is None:
                self.pw = await async_playwright().start()
            self.ctx = await self.pw.chromium.launch_persistent_context(
                PROFILE_DIR, headless=os.environ.get("MG_BRIDGE_HEADLESS") == "1", no_viewport=True)
            return self.ctx

    async def tab(self):
        ctx = await self.browser()
        if self.page is None or self.page.is_closed():
            self.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return self.page

    async def probe(self, p):
        """True/False: logged in to ChatGPT in this profile. False also when the page never became usable."""
        end = time.time() + 12
        st = {"login": False, "box": False}
        while time.time() < end:
            if urlsplit(p.url).hostname not in HOSTS:
                return False
            st = await p.evaluate(PAGE_STATE_JS)
            if st["login"] or st["box"]:
                break
            await asyncio.sleep(0.5)
        return bool(st["box"] and not st["login"])

    async def goto(self, p, url):
        await p.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)

    # -- routes' work ------------------------------------------------------------------------------------------
    async def status(self):
        if self.lock.locked():                       # a send is running: do not disturb the tab
            return {"ok": True, "logged_in": self.logged_in, "busy": True}
        async with self.lock:
            p = await self.tab()
            if urlsplit(p.url).hostname not in HOSTS:
                await self.goto(p, "https://chatgpt.com/")
            self.logged_in = await self.probe(p)
        return {"ok": True, "logged_in": self.logged_in, "busy": False}

    async def login(self):
        async with self.lock:
            p = await self.tab()
            await self.goto(p, "https://chatgpt.com/")
            try:
                await p.bring_to_front()
            except Exception:
                pass
        return {"ok": True, "opened": True}

    async def settle(self, p):
        """After a (re)load the transcript mounts late: wait until the set of message ids is stable for 2 s (max 12 s)."""
        last = None
        since = time.time()
        end = time.time() + 12
        while time.time() < end:
            ids = sorted(x for x in await p.evaluate(CG_IDS_JS) if x)
            if ids != last:
                last = ids
                since = time.time()
            elif time.time() - since >= 2:
                break
            await asyncio.sleep(0.4)
        return set(last or [])

    async def ask(self, prompt, tmo, new_chat, out):
        try:
            async with self.lock:
                p = await self.tab()
                target = "https://chatgpt.com/" if (new_chat or not self.last_chat) else self.last_chat
                await self.goto(p, target)
                if not await self.probe(p):
                    self.logged_in = False
                    out.update(ok=False, error="not logged in to ChatGPT in the bridge window", failure="AUTH")
                    return
                self.logged_in = True
                inp = p.locator(INPUT_SEL).first
                try:
                    await inp.wait_for(timeout=15000)
                except Exception:
                    out.update(ok=False, error="prompt box missing", failure="AUTH")
                    return
                seen = await self.settle(p)
                snip = snippets(prompt)
                prev = (await p.evaluate(CG_LAST_JS, snip))["text"]    # a streaming answer has no id yet: tell it from the old one by text
                await inp.click()
                await p.keyboard.insert_text(prompt)
                await asyncio.sleep(0.4)
                sb = p.locator(SEND_SEL)
                if await sb.count():
                    await sb.first.click()
                else:
                    await p.keyboard.press("Enter")
                out["sent"] = True
                deadline = time.time() + tmo
                last = ""
                stable = None
                while time.time() < deadline:
                    await asyncio.sleep(0.7)
                    s = await p.evaluate(CG_LAST_JS, snip)
                    if s["mine"] is False or s["id"] in seen or (s["id"] is None and s["text"] == prev):
                        continue                                       # old answer, or still thinking
                    txt = s["text"]
                    done = s["id"] is not None and (s["state"] == "complete" if s["state"] else not s["stop"])
                    if txt == last and done and txt.strip():
                        stable = stable or time.time()
                        if time.time() - stable >= 2.5:                # same text, complete, no Stop button for 2.5 s
                            if "/c/" in p.url:
                                self.last_chat = p.url.split("?")[0]
                            out.update(ok=True, done=True, content=txt)
                            return
                    else:
                        last = txt
                        stable = None
                out.update(ok=False, error="timeout waiting for answer", failure="TIMEOUT", partial=last[:2000])
        except Exception as e:
            out.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}", failure="SEND_FAILED")
        finally:
            out["finished"] = True

    async def close(self):
        try:
            if self.ctx:
                await self.ctx.close()
            if self.pw:
                await self.pw.stop()
        except Exception:
            pass


def build_app(token):
    from aiohttp import web
    br = Bridge()
    app = web.Application(client_max_size=2 * 1024 * 1024)

    @web.middleware
    async def mw(req, handler):
        if req.path != "/health":
            if not hmac.compare_digest(req.headers.get("Authorization", ""), "Bearer " + token):
                raise web.HTTPUnauthorized()
        try:
            return await handler(req)
        except web.HTTPException:
            raise
        except Exception as e:
            return web.json_response({"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}, status=500)

    app.middlewares.append(mw)

    async def health(req):
        return web.json_response({"ok": True, "version": VERSION, "browser": br.ctx is not None, "logged_in": br.logged_in})

    async def status(req):
        return web.json_response(await br.status())

    async def login(req):
        return web.json_response(await br.login())

    async def ask(req):
        try:
            b = await req.json()
        except Exception:
            b = {}
        prompt = b.get("prompt", "")
        if not isinstance(prompt, str) or not prompt.strip():
            return web.json_response({"ok": False, "error": "prompt required"}, status=400)
        if len(prompt) > 30000:
            return web.json_response({"ok": False, "error": "prompt too long (max 30000 characters)"}, status=400)
        tmo = min(float(b.get("timeout_s", 180)), 1800)
        new_chat = bool(b.get("new_chat", True))
        out = {}
        if b.get("wait", True):
            await br.ask(prompt, tmo, new_chat, out)
            return web.json_response(out, status=200 if out.get("ok") else 409)
        tid = str(int(time.time() * 1000))
        br.results[tid] = out
        for k in list(br.results)[:-50]:
            br.results.pop(k, None)
        asyncio.create_task(br.ask(prompt, tmo, new_chat, out))
        return web.json_response({"ok": True, "task_id": tid})

    async def result(req):
        o = br.results.get(req.match_info["tid"])
        if o is None:
            return web.json_response({"ok": False, "error": "unknown task"}, status=404)
        if o.get("ok") and o.get("done"):
            return web.json_response({"ok": True, "status": "DONE", "content": o["content"]})
        if o.get("finished"):
            return web.json_response({"ok": False, "status": "FAILED", **o})
        return web.json_response({"ok": True, "status": "PENDING"})

    async def shutdown(req):
        asyncio.get_running_loop().call_later(0.2, lambda: os.kill(os.getpid(), 15))
        return web.json_response({"ok": True})

    app.router.add_get("/health", health)
    app.router.add_get("/status", status)
    app.router.add_post("/login", login)
    app.router.add_post("/ask", ask)
    app.router.add_get("/result/{tid}", result)
    app.router.add_post("/shutdown", shutdown)
    return app, br


def _already_running():
    try:
        info = json.load(open(INFO_FILE))
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


async def serve():
    from aiohttp import web
    if _already_running():
        print("bridge already running", file=sys.stderr)
        return 0
    try:
        token = open(TOKEN_FILE).read().strip()
    except OSError:
        print(f"no token file at {TOKEN_FILE} (run Machine God's first-run setup)", file=sys.stderr)
        return 2
    if len(token) < 32:
        print("token too short", file=sys.stderr)
        return 2
    app, br = build_app(token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = INFO_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"port": port, "pid": os.getpid(), "version": VERSION}, f)
    os.replace(tmp, INFO_FILE)
    print(f"machine-god chatgpt bridge on 127.0.0.1:{port}", flush=True)
    stop = asyncio.Event()
    try:
        import signal
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
    except (NotImplementedError, ValueError):
        pass                                                           # Windows: Ctrl-C raises KeyboardInterrupt below
    try:
        await stop.wait()
    finally:
        try:
            os.unlink(INFO_FILE)
        except OSError:
            pass
        await br.close()
        await runner.cleanup()
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] != "serve":
        print(__doc__)
        return 2
    try:
        return asyncio.run(serve())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
