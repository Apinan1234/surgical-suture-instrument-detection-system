# -*- coding: utf-8 -*-
"""ถ่ายภาพหน้าจอแท็บ Analytics ของเว็บแอปสดๆ + ดึงตัวเลขจริงจาก /api/analytics

เขียนด้วย stdlib ล้วน (ไม่ติดตั้ง Selenium/Playwright) — ขับ headless Edge ที่มีอยู่แล้วในเครื่อง
ผ่าน Chrome DevTools Protocol (CDP) คุยผ่าน raw WebSocket ที่เขียนเอง เพราะแท็บ Analytics ไม่มี
URL route (ต้องคลิกจริงถึงจะ trigger refreshAnalytics() ใน app.js)

    "..\\..\\..\\01_frame-extractor-tool\\webapp\\.venv\\Scripts\\python.exe" live_screenshot.py

ผลลัพธ์:
  - assets/screenshots-webapp/2026-08-17__14-analytics-live.png
  - tools/analytics-live.json  (ตัวเลขจาก /api/analytics ตรงๆ + ตารางนับต่อคลาสจาก state.json)
"""
import base64
import collections
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DECK_DIR = os.path.abspath(os.path.join(HERE, ".."))
ASSETS_SHOTS = os.path.join(DECK_DIR, "..", "assets", "screenshots-webapp")

VENV_PY = os.path.join(REPO_ROOT, "01_frame-extractor-tool", "webapp", ".venv", "Scripts", "python.exe")
STATE_JSON = os.path.join(REPO_ROOT, "01_frame-extractor-tool", "webapp", "state.json")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

HOST, PORT = "127.0.0.1", 8010
BASE_URL = "http://%s:%d" % (HOST, PORT)
CDP_PORT = 9333
EDGE_PROFILE = os.path.join(os.environ.get("TEMP", HERE), "beam-deck-edge-profile")

OUT_PNG = os.path.join(ASSETS_SHOTS, "2026-08-17__14-analytics-live.png")
OUT_JSON = os.path.join(HERE, "analytics-live.json")


# ── รอ server พร้อม ────────────────────────────────────────────────────────
def wait_http_ok(url, timeout_s):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ── raw WebSocket client (RFC 6455) พอสำหรับคุยกับ CDP เท่านั้น ───────────────
class MiniWS:
    def __init__(self, url):
        assert url.startswith("ws://")
        rest = url[len("ws://"):]
        hostport, _, path = rest.partition("/")
        path = "/" + path
        host, _, port = hostport.partition(":")
        port = int(port or 80)
        self.sock = socket.create_connection((host, port), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: %s\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key)
        )
        self.sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP handshake ปิดก่อนตอบครบ")
            resp += chunk
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise ConnectionError("CDP handshake ไม่สำเร็จ: %r" % resp[:200])
        self._buf = resp.split(b"\r\n\r\n", 1)[1]

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("CDP socket ปิดกลางทาง")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def send_text(self, text):
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        n = len(payload)
        if n < 126:
            header = struct.pack("!BB", 0x81, 0x80 | n)
        elif n < 65536:
            header = struct.pack("!BBH", 0x81, 0x80 | 126, n)
        else:
            header = struct.pack("!BBQ", 0x81, 0x80 | 127, n)
        self.sock.sendall(header + mask + masked)

    def recv_message(self):
        """อ่านหนึ่งข้อความ (รวมเฟรมต่อกันถ้ามี fragmentation)"""
        parts = []
        while True:
            b1, b2 = self._recv_exact(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            n = b2 & 0x7F
            if n == 126:
                (n,) = struct.unpack("!H", self._recv_exact(2))
            elif n == 127:
                (n,) = struct.unpack("!Q", self._recv_exact(8))
            mask_key = self._recv_exact(4) if masked else None
            payload = self._recv_exact(n)
            if mask_key:
                payload = bytes(c ^ mask_key[i % 4] for i, c in enumerate(payload))
            if opcode == 0x8:  # close
                raise ConnectionError("CDP ปิด websocket")
            parts.append(payload)
            if fin:
                break
        return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


class CDP:
    def __init__(self, ws_url):
        self.ws = MiniWS(ws_url)
        self._id = 0

    def call(self, method, params=None, timeout_s=15):
        self._id += 1
        my_id = self._id
        self.ws.send_text(json.dumps({"id": my_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            msg = json.loads(self.ws.recv_message())
            if msg.get("id") == my_id:
                if "error" in msg:
                    raise RuntimeError("CDP %s error: %s" % (method, msg["error"]))
                return msg.get("result", {})
        raise TimeoutError("CDP %s ไม่ตอบใน %ds" % (method, timeout_s))

    def evaluate(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("value")


def find_page_ws_url():
    with urllib.request.urlopen("http://127.0.0.1:%d/json" % CDP_PORT, timeout=5) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page" and BASE_URL in (t.get("url") or ""):
            return t["webSocketDebuggerUrl"]
    # fallback: แท็บแรกที่เป็น page
    for t in targets:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("หา page target ของ Edge ไม่เจอ: %r" % targets)


def tally_state_json():
    with open(STATE_JSON, encoding="utf-8") as f:
        d = json.load(f)
    frames = d["frames"]
    cls = collections.Counter()
    with_dets = 0
    reviewed = 0
    total_dets = 0
    for fr in frames.values():
        dets = fr.get("detections") or []
        if dets:
            with_dets += 1
        if fr.get("reviewed"):
            reviewed += 1
        total_dets += len(dets)
        for det in dets:
            cls[det.get("class_name")] += 1
    return {
        "frames_total": len(frames),
        "frames_with_detections": with_dets,
        "frames_reviewed": reviewed,
        "detections_total": total_dets,
        "by_class": dict(cls.most_common()),
    }


def main():
    print("1/6 เริ่ม uvicorn server ...")
    server = subprocess.Popen(
        [VENV_PY, "-m", "uvicorn", "webapp.server:app", "--host", HOST, "--port", str(PORT),
         "--app-dir", "01_frame-extractor-tool"],
        cwd=REPO_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    edge = None
    try:
        if not wait_http_ok(BASE_URL + "/api/health", 30):
            raise RuntimeError("server ไม่ตอบใน 30 วินาที")
        print("   server พร้อมที่", BASE_URL)

        print("2/6 เปิด headless Edge ...")
        os.makedirs(EDGE_PROFILE, exist_ok=True)
        edge = subprocess.Popen([
            EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--window-size=1600,1100", "--force-device-scale-factor=1",
            "--remote-debugging-port=%d" % CDP_PORT,
            "--user-data-dir=%s" % EDGE_PROFILE,
            BASE_URL + "/",
        ])
        if not wait_http_ok("http://127.0.0.1:%d/json/version" % CDP_PORT, 15):
            raise RuntimeError("Edge CDP ไม่ตอบใน 15 วินาที")
        time.sleep(1.5)  # ให้หน้าโหลด DOM/JS เสร็จก่อนหา target

        print("3/6 ต่อ CDP และคลิกแท็บ Analytics ...")
        ws_url = find_page_ws_url()
        cdp = CDP(ws_url)
        cdp.evaluate('document.querySelector(\'[data-tab="analytics"]\').click()')

        print("4/6 รอข้อมูล Analytics โหลด ...")
        deadline = time.time() + 15
        loaded = False
        while time.time() < deadline:
            val = cdp.evaluate(
                "(document.getElementById('analytics-accept-rate') || {}).textContent || ''"
            )
            if val and val.strip() not in ("", "—", "-"):
                loaded = True
                break
            time.sleep(0.4)
        if not loaded:
            print("   !! คำเตือน: ตัวเลขยังไม่ขึ้นภายใน 15 วิ ถ่ายภาพต่อไปตามสภาพจริง")

        print("5/6 capture screenshot ...")
        shot = cdp.call("Page.captureScreenshot", {"format": "png"}, timeout_s=20)
        os.makedirs(ASSETS_SHOTS, exist_ok=True)
        with open(OUT_PNG, "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("   บันทึกแล้ว:", OUT_PNG)

        print("6/6 ดึง /api/analytics + นับ state.json ...")
        with urllib.request.urlopen(BASE_URL + "/api/analytics", timeout=10) as r:
            analytics_api = json.loads(r.read().decode())
        tally = tally_state_json()
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump({"api_analytics": analytics_api, "state_json_tally": tally}, f,
                       ensure_ascii=False, indent=2)
        print("   บันทึกแล้ว:", OUT_JSON)
        ar = analytics_api.get("accept_rate", {})
        print("\nเสร็จ — rate_pct=%s suggested=%s accepted=%s assist_calls=%s" % (
            ar.get("rate_pct"), ar.get("suggested_total"), ar.get("accepted_total"),
            ar.get("assist_call_count")))

    finally:
        if edge is not None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(edge.pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
