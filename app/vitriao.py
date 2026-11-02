#!/usr/bin/env python3
"""
Vị trí ảo iPhone - app desktop (Windows / macOS).

Đặt vị trí GPS ảo cho iPhone đã bật Developer Mode, dùng dịch vụ mô phỏng vị trí
chính thức của Apple (giống Xcode / 3uTools) qua thư viện pymobiledevice3.

Chạy khi phát triển:   python vitriao.py        (Windows: CMD quyền Admin; macOS: chạy thường)
Chế độ nội bộ:         vitriao.py --pmd <lệnh pymobiledevice3...>
                       vitriao.py --tunnel-watch <pid>     (macOS, chạy bằng quyền root)
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import licensing

APP_TITLE = "Vị trí ảo iPhone"
APP_VERSION = "1.0.0"

FROZEN = getattr(sys, "frozen", False)
IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
NOWIN = 0x08000000 if IS_WIN else 0          # CREATE_NO_WINDOW: không bật cửa sổ đen trên Windows

# Khi đóng gói onefile, gọi lại chính file chạy kèm cờ ẩn (--pmd) để chạy lệnh pymobiledevice3.
if FROZEN:
    HELPER = [sys.executable]
else:
    HELPER = [sys.executable, os.path.abspath(__file__)]
PMD = HELPER + ["--pmd"]
SIM = ["developer", "dvt", "simulate-location"]
TUNNELD_URL = "http://127.0.0.1:49151"
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", NO_COLOR="1", TERM="dumb")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


# ======================================================================
#  Chạy lệnh pymobiledevice3
# ======================================================================
def run_pmd_inprocess(args):
    from pymobiledevice3.__main__ import main as pmd_main
    sys.argv = ["pymobiledevice3"] + args
    pmd_main()


def pmd(args, timeout=60):
    try:
        r = subprocess.run(PMD + args, capture_output=True, text=True, encoding="utf-8", errors="ignore",
                           timeout=timeout, creationflags=NOWIN, env=CHILD_ENV)
        return r.returncode, ANSI.sub("", r.stdout or ""), ANSI.sub("", r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def pmd_bg(args):
    return subprocess.Popen(PMD + args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=NOWIN, env=CHILD_ENV)


def first_json(text):
    for opener in "[{":
        i = text.find(opener)
        if i >= 0:
            try:
                return json.loads(text[i:])
            except Exception:
                pass
    return None


def is_admin():
    if IS_WIN:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    return os.geteuid() == 0


# ======================================================================
#  Tunnel (iOS 17+)
# ======================================================================
def tunnel_ready():
    try:
        with urllib.request.urlopen(TUNNELD_URL, timeout=2) as r:
            return r.read().strip() not in (b"", b"{}")
    except Exception:
        return False


def tunnel_running():
    try:
        urllib.request.urlopen(TUNNELD_URL, timeout=2).close()
        return True
    except Exception:
        return False


def tunnel_watch(parent_pid):
    """macOS: chạy bằng root, giữ tunneld sống tới khi app chính tắt."""
    p = subprocess.Popen(PMD + ["remote", "tunneld"], env=CHILD_ENV)
    try:
        while p.poll() is None:
            time.sleep(2)
            try:
                os.kill(parent_pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pass
    finally:
        if p.poll() is None:
            p.terminate()


def start_tunnel():
    """Trả về (ok, thông báo lỗi)."""
    if tunnel_running():
        return True, ""
    if IS_MAC and os.geteuid() != 0:
        cmd = " ".join(shlex.quote(x) for x in HELPER + ["--tunnel-watch", str(os.getpid())])
        cmd += " >/tmp/vitriao_tunnel.log 2>&1 &"
        esc = cmd.replace("\\", "\\\\").replace('"', '\\"')
        script = (f'do shell script "{esc}" with prompt "{APP_TITLE} cần quyền quản trị để kết nối với iPhone." '
                  f'with administrator privileges')
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if r.returncode != 0:
            return False, "Cần nhập mật khẩu máy Mac để kết nối iPhone. Bấm Kiểm tra lại để thử lại."
        return True, ""
    if not is_admin():
        return False, "Cần chạy app bằng quyền quản trị (Admin)."
    procs["tunnel"] = pmd_bg(["remote", "tunneld"])
    return True, ""


# ======================================================================
#  Trạng thái + các bước chuẩn bị
# ======================================================================
STEP_DEFS = [
    ("device", "Cắm iPhone vào máy"),
    ("trust", "Tin cậy máy tính này"),
    ("devmode", "Bật Chế độ nhà phát triển"),
    ("tunnel", "Kết nối với iPhone"),
    ("mount", "Chuẩn bị công cụ của Apple"),
]
HELP = {
    "driver": ("Máy chưa có driver iPhone. Mở Microsoft Store, cài ứng dụng \"Apple Devices\" (hoặc iTunes), "
               "rồi rút ra cắm lại iPhone."),
    "device": "Cắm iPhone vào máy bằng cáp USB và mở khóa màn hình iPhone.",
    "trust": "Mở khóa iPhone. Khi iPhone hỏi \"Tin cậy máy tính này?\", bấm Tin cậy rồi nhập mật mã.",
    "devmode": ("Trên iPhone: Cài đặt → Quyền riêng tư & Bảo mật → Chế độ nhà phát triển → Bật. "
                "iPhone sẽ khởi động lại; mở khóa xong chọn Bật một lần nữa."),
    "tunnel": "Đang mở kết nối tới iPhone...",
    "mount": "Lần đầu cần tải khoảng vài trăm MB từ Apple, có thể mất vài phút. Giữ iPhone mở khóa.",
}

state = {"ready": False, "licensed": False, "code": "", "device": "", "active": None, "msg": "",
         "last": None,
         "steps": [{"id": i, "label": l, "st": "wait", "note": ""} for i, l in STEP_DEFS]}
procs = {"tunnel": None, "sim": None}
lock = threading.Lock()
setup_lock = threading.Lock()
stopping = threading.Event()


def step(sid, st, note=""):
    for s in state["steps"]:
        if s["id"] == sid:
            s["st"], s["note"] = st, note


def reset_steps(start_from):
    hit = False
    for s in state["steps"]:
        if s["id"] == start_from:
            hit = True
        if hit:
            s["st"], s["note"] = "wait", ""


def find_device():
    code, out, err = pmd(["usbmux", "list"], 25)
    if code != 0:
        low = (out + err).lower()
        if "usbmux" in low or "refused" in low or "10061" in low or "connect" in low:
            return None, "driver" if IS_WIN else "device"
        return None, "device"
    devs = first_json(out)
    if not isinstance(devs, list):
        return None, "device"
    usb = [d for d in devs if str(d.get("ConnectionType", "USB")).upper() == "USB"]
    devs = usb or devs
    return (devs[0], "ok") if devs else (None, "device")


def setup_loop():
    if not setup_lock.acquire(blocking=False):
        return
    try:
        state["ready"] = False
        revealed = False
        while not stopping.is_set():
            # 1. Thiết bị
            step("device", "run")
            dev, st = find_device()
            if st != "ok":
                step("device", "fail", HELP[st])
                reset_steps("trust")
                stopping.wait(3)
                continue
            step("device", "ok")

            # 2. Tin cậy / ghép đôi
            step("trust", "run")
            code, out, err = pmd(["lockdown", "info"], 40)
            info = first_json(out) if code == 0 else None
            if not isinstance(info, dict) or "ProductVersion" not in info:
                step("trust", "fail", HELP["trust"])
                reset_steps("devmode")
                stopping.wait(3)
                continue
            ver = str(info.get("ProductVersion", "0"))
            major = int(ver.split(".")[0] or 0)
            state["device"] = f"{info.get('DeviceName', 'iPhone')} · iOS {ver}"
            step("trust", "ok", state["device"])

            # 3. Developer Mode (iOS 16+)
            if major >= 16:
                step("devmode", "run")
                code, out, err = pmd(["amfi", "developer-mode-status"], 25)
                if "true" not in out.lower():
                    if not revealed:
                        pmd(["amfi", "reveal-developer-mode"], 25)   # làm hiện mục Developer Mode trong Cài đặt
                        revealed = True
                    step("devmode", "fail", HELP["devmode"])
                    reset_steps("tunnel")
                    stopping.wait(3)
                    continue
                step("devmode", "ok")
            else:
                step("devmode", "skip", "Không cần với iOS " + ver)

            # 4. Tunnel (iOS 17+)
            if major >= 17:
                step("tunnel", "run", HELP["tunnel"])
                ok, why = start_tunnel()
                t0 = time.time()
                while ok and not tunnel_ready() and time.time() - t0 < 60 and not stopping.is_set():
                    time.sleep(1)
                if not ok or not tunnel_ready():
                    step("tunnel", "fail", why or "Không kết nối được. Rút ra cắm lại iPhone, giữ màn hình mở khóa.")
                    stopping.wait(5)
                    continue
                step("tunnel", "ok")
            else:
                step("tunnel", "skip", "Không cần với iOS " + ver)

            # 5. Mount Developer Disk Image
            step("mount", "run", HELP["mount"])
            code, out, err = pmd(["mounter", "auto-mount"], 900)
            text = (out + err).lower()
            if code == 0 or "already" in text:
                step("mount", "ok")
            else:
                step("mount", "warn", "Chưa chắc đã chuẩn bị xong. Vẫn có thể thử đổi vị trí; nếu lỗi, bấm Kiểm tra lại.")
            state["ready"] = True
            return
    finally:
        setup_lock.release()


def recheck():
    threading.Thread(target=setup_loop, daemon=True).start()


# ======================================================================
#  Đặt / trả vị trí
# ======================================================================
def stop_sim():
    p = procs["sim"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    procs["sim"] = None


def set_location(lat, lon):
    if not state["licensed"]:
        return False, "Vui lòng nhập key để kích hoạt trước khi đổi vị trí."
    with lock:
        stop_sim()
        procs["sim"] = pmd_bg(SIM + ["set", "--", str(lat), str(lon)])
        time.sleep(3)
        p = procs["sim"]
        if p.poll() is not None and p.returncode != 0:
            err = ANSI.sub("", p.stderr.read().decode(errors="ignore"))[-250:]
            procs["sim"] = None
            return False, "Không đổi được vị trí. Bấm Kiểm tra lại kết nối rồi thử lần nữa. (" + err.strip() + ")"
        state["active"] = [lat, lon]
        return True, f"Đã đổi vị trí iPhone sang {lat:.6f}, {lon:.6f}"


def restore():
    with lock:
        stop_sim()
        pmd(SIM + ["clear"], 30)
        state["active"] = None
        return True, "Đã trả iPhone về vị trí thật."


def _data_path(name):
    base = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def load_lastloc():
    try:
        return json.load(open(_data_path("lastloc.json"), encoding="utf-8"))
    except Exception:
        return None


def save_lastloc(lat, lon, label=""):
    try:
        with open(_data_path("lastloc.json"), "w", encoding="utf-8") as f:
            json.dump({"lat": lat, "lon": lon, "label": label}, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def _bundled_driver():
    """Tìm trình cài driver Apple để sẵn trong thư mục Driver cạnh app (trên USB)."""
    base = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
    folder = os.path.join(base, "Driver")
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith((".msi", ".exe")):
                return os.path.join(folder, f), folder
    return None, folder


def install_driver():
    if not IS_WIN:
        return True, "macOS không cần driver Apple, cắm iPhone là nhận."
    path, folder = _bundled_driver()
    if path:
        try:
            if path.lower().endswith(".msi"):
                subprocess.Popen(["msiexec", "/i", path])
            else:
                os.startfile(path)
            return True, "Đang mở trình cài driver Apple. Cài xong, rút ra cắm lại iPhone rồi bấm Kiểm tra lại."
        except Exception as e:
            return False, f"Không chạy được trình cài driver: {e}"
    try:
        if os.path.isdir(folder):
            os.startfile(folder)
            return False, "Chưa thấy file driver trong thư mục Driver trên USB."
    except Exception:
        pass
    webbrowser.open("https://apps.microsoft.com/detail/9np83lwlpz9k")   # Apple Devices trên Microsoft Store
    return False, "Không có driver sẵn trên USB. Đã mở trang cài Apple Devices (cần mạng)."


# ======================================================================
#  Giao diện (HTML phục vụ tại 127.0.0.1)
# ======================================================================
PAGE = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vị trí ảo iPhone</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>if (!window.L) document.write('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"><script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"><\/script>');</script>
<style>
  *{box-sizing:border-box} body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;height:100vh;display:flex;flex-direction:column;color:#1f2328}
  header{padding:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#f4f5f7;border-bottom:1px solid #ddd}
  #q{flex:1;min-width:220px;padding:9px 11px;border:1px solid #bbb;border-radius:8px;font-size:15px}
  button{padding:9px 14px;border:0;border-radius:8px;font-size:15px;cursor:pointer}
  #btnSearch{background:#e2e6ea} #btnSet{background:#1a73e8;color:#fff} #btnStop{background:#d93025;color:#fff}
  button:disabled{opacity:.45;cursor:default}
  main{flex:1;position:relative} #map{position:absolute;inset:0}
  #results{position:absolute;top:8px;left:10px;z-index:1001;background:#fff;border-radius:8px;
    box-shadow:0 2px 12px rgba(0,0,0,.2);max-width:560px;width:calc(100% - 20px)}
  #results div{padding:9px 12px;border-bottom:1px solid #eee;cursor:pointer;font-size:14px} #results div:hover{background:#f0f4ff}
  #setup{position:absolute;left:10px;bottom:10px;z-index:1000;background:#fff;border-radius:10px;padding:14px 16px;
    box-shadow:0 2px 14px rgba(0,0,0,.22);width:min(420px,calc(100% - 20px))}
  #setup h3{margin:0 0 8px;font-size:16px} #steps{list-style:none;margin:0 0 8px;padding:0}
  #steps li{padding:4px 0;font-size:14px;display:flex;gap:8px} #steps .ic{width:18px;text-align:center}
  .ok{color:#188038}.fail{color:#d93025}.run{color:#1a73e8}.wait{color:#999}.warn{color:#b06000}.skip{color:#999}
  #help{background:#fff4e5;border-radius:8px;padding:9px 11px;font-size:14px;line-height:1.45;margin-bottom:8px}
  #help:empty{display:none} #btnRecheck{background:#e2e6ea;font-size:14px;padding:7px 12px}
  footer{padding:8px 10px;font-size:14px;background:#f4f5f7;border-top:1px solid #ddd;display:flex;gap:14px;flex-wrap:wrap}
  #coord{font-family:ui-monospace,Consolas,monospace} #dev a{color:#1a73e8;cursor:pointer}
</style></head><body>
<header>
  <input id="q" placeholder="Gõ địa chỉ, tên địa điểm, toạ độ hoặc dán link Google Maps">
  <button id="btnSearch">Tìm</button>
  <button id="btnSet" disabled>Đổi vị trí</button>
  <button id="btnStop">Dừng / Trả về</button>
</header>
<main>
  <div id="map"></div>
  <div id="results"></div>
  <div id="setup">
    <h3>Chuẩn bị kết nối iPhone</h3>
    <ul id="steps"></ul>
    <div id="help"></div>
    <button id="btnRecheck">Kiểm tra lại</button>
    <button id="btnDriver" style="background:#e2e6ea">Cài driver Apple (Windows)</button>
  </div>
  <div id="keypanel" style="position:absolute;left:10px;bottom:10px;z-index:1000;background:#fff;border-radius:10px;
       padding:14px 16px;box-shadow:0 2px 14px rgba(0,0,0,.22);width:min(420px,calc(100% - 20px));display:none">
    <h3 style="margin:0 0 6px">✓ iPhone đã kết nối — nhập key để dùng</h3>
    <p style="margin:0 0 10px;font-size:14px;color:#444">Gõ key được cấp để bắt đầu đổi vị trí. Key gắn với máy này.</p>
    <input id="keyin" placeholder="XXXX-XXXX-XXXX-XXXX" autocomplete="off"
      style="width:100%;padding:10px;border:1px solid #bbb;border-radius:8px;font-size:17px;letter-spacing:1px;text-transform:uppercase;font-family:ui-monospace,Consolas,monospace">
    <div id="keymsg" style="font-size:14px;margin:8px 0;min-height:18px"></div>
    <button id="btnActivate" style="background:#1a73e8;color:#fff;width:100%">Kích hoạt</button>
    <div style="font-size:12px;color:#777;margin-top:9px">Chưa có key? Liên hệ người bán. Mã máy của bạn: <b id="mcode" style="font-family:ui-monospace,Consolas,monospace"></b></div>
  </div>
</main>
<footer>
  <span id="dev">Chưa kết nối iPhone</span>
  <span>Điểm chọn: <span id="coord">chưa chọn</span></span>
  <span id="status"></span>
</footer>
<script>
const $ = id => document.getElementById(id);
if (!window.L) {
  $('map').innerHTML = '<p style="padding:20px">Không tải được bản đồ. Kiểm tra kết nối mạng rồi mở lại app. Vẫn có thể dán toạ độ vào ô tìm kiếm.</p>';
  window.L = {map: () => ({setView(){return this}, on(){}, removeLayer(){}, getCenter(){return {lat:21.03,lng:105.85}}}),
    tileLayer: () => ({addTo(){return this}}), control: null,
    marker: () => ({addTo(){return this}, on(){return this}, setLatLng(){}}),
    circleMarker: () => ({addTo(){return this}, bindTooltip(){return this}})};
}
const map = L.map('map').setView([21.0285, 105.8542], 13);
const layers = {
  'Bản đồ': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    {maxZoom: 19, attribution: '&copy; Esri'}),
  'Vệ tinh': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {maxZoom: 19, attribution: '&copy; Esri'})
};
layers['Bản đồ'].addTo(map);
if (L.control && L.control.layers) L.control.layers(layers).addTo(map);

let pick = null, marker = null, activeMarker = null, ready = false, saveTimer = null, restored = false;
function saveQuiet(p, b) { fetch(p, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)}).catch(() => {}); }
function choose(lat, lon, zoom, skipSave) {
  pick = [lat, lon];
  if (marker) marker.setLatLng(pick); else marker = L.marker(pick, {draggable: true}).addTo(map)
    .on('dragend', e => { const p = e.target.getLatLng(); choose(p.lat, p.lng); });
  if (zoom) map.setView(pick, zoom);
  $('coord').textContent = lat.toFixed(6) + ', ' + lon.toFixed(6);
  $('btnSet').disabled = !(ready && licensed);
  if (!skipSave) {   // ghi nhớ địa điểm cuối (chờ 0.8s để khỏi lưu liên tục khi kéo ghim)
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveQuiet('/saveloc', {lat: pick[0], lon: pick[1], label: $('q').value.trim()}), 800);
  }
}
map.on('click', e => { $('results').innerHTML = ''; choose(e.latlng.lat, e.latlng.lng); });

// ---- Tìm kiếm: Esri (gợi ý khi gõ) + Photon dự phòng, không cần API key ----
const ESRI = 'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer';
const enc = encodeURIComponent;
let timer = null, seq = 0;
function parseCoords(t) {
  const m = t.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/) || t.match(/(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)/);
  return m ? [+m[1], +m[2]] : null;
}
function near() { return map.getCenter(); }
function showList(items) {
  const box = $('results'); box.innerHTML = '';
  if (!items.length) { box.innerHTML = '<div>Không tìm thấy</div>'; return; }
  items.forEach(it => {
    const d = document.createElement('div'); d.textContent = it.label;
    d.onclick = async () => { box.innerHTML = ''; $('q').value = it.label; const p = await it.get(); if (p) choose(p[0], p[1], 17); };
    box.appendChild(d);
  });
}
async function esriFind(text, magicKey, n) {
  const c = near();
  let url = `${ESRI}/findAddressCandidates?f=json&outFields=Match_addr&maxLocations=${n}&location=${c.lng},${c.lat}&SingleLine=${enc(text)}`;
  if (magicKey) url += `&magicKey=${enc(magicKey)}`;
  const j = await (await fetch(url)).json();
  return (j.candidates || []).map(x => ({label: x.address, lat: x.location.y, lon: x.location.x}));
}
async function photon(text) {
  const c = near();
  const j = await (await fetch(`https://photon.komoot.io/api/?limit=8&lat=${c.lat}&lon=${c.lng}&q=${enc(text)}`)).json();
  return (j.features || []).map(f => {
    const p = f.properties, parts = [p.name, p.housenumber && p.street ? p.housenumber + ' ' + p.street : p.street,
      p.district, p.city, p.state, p.country].filter(Boolean);
    return {label: [...new Set(parts)].join(', '), lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0]};
  });
}
async function suggest() {
  const q = $('q').value.trim(), my = ++seq;
  if (q.length < 2 || parseCoords(q)) { $('results').innerHTML = ''; return; }
  try {
    const c = near();
    const j = await (await fetch(`${ESRI}/suggest?f=json&maxSuggestions=8&location=${c.lng},${c.lat}&text=${enc(q)}`)).json();
    if (my !== seq) return;
    showList((j.suggestions || []).map(s => ({label: s.text,
      get: async () => { const r = await esriFind(s.text, s.magicKey, 1); return r[0] && [r[0].lat, r[0].lon]; }})));
  } catch (e) {}
}
async function search() {
  clearTimeout(timer); seq++;
  const q = $('q').value.trim(); if (!q) return;
  const p = parseCoords(q); if (p) { $('results').innerHTML = ''; return choose(p[0], p[1], 17); }
  $('results').innerHTML = '<div>Đang tìm...</div>';
  let list = [];
  try { list = await esriFind(q, null, 8); } catch (e) {}
  if (!list.length) { try { list = await photon(q); } catch (e) {} }
  if (list.length === 1) { $('results').innerHTML = ''; return choose(list[0].lat, list[0].lon, 17); }
  showList(list.map(x => ({label: x.label, get: async () => [x.lat, x.lon]})));
}
$('btnSearch').onclick = search;
$('q').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(suggest, 300); });
$('q').addEventListener('keydown', e => { if (e.key === 'Enter') search(); if (e.key === 'Escape') $('results').innerHTML = ''; });

// ---- Gọi chương trình ----
async function post(path, body) {
  $('status').textContent = 'Đang xử lý...';
  try {
    const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
    const j = await r.json(); $('status').textContent = j.msg || ''; return j;
  } catch (e) { $('status').textContent = 'Mất kết nối với chương trình.'; return {}; }
}
$('btnSet').onclick = async () => {
  if (!pick) return;
  $('btnSet').disabled = true;
  const j = await post('/set', {lat: pick[0], lon: pick[1]});
  $('btnSet').disabled = !ready;
  if (j.ok) {
    if (activeMarker) map.removeLayer(activeMarker);
    activeMarker = L.circleMarker(pick, {radius: 11, color: '#1a73e8', fillOpacity: .35}).addTo(map).bindTooltip('iPhone đang ở đây');
  }
};
$('btnStop').onclick = async () => {
  await post('/stop');
  if (activeMarker) { map.removeLayer(activeMarker); activeMarker = null; }
};
$('btnRecheck').onclick = () => post('/recheck');
$('btnDriver').onclick = () => post('/install-driver');

let licensed = false;
$('btnActivate').onclick = async () => {
  const key = $('keyin').value.trim();
  if (!key) return;
  $('btnActivate').disabled = true; $('keymsg').textContent = 'Đang kích hoạt...'; $('keymsg').style.color = '#444';
  const j = await post('/activate', {key: key});
  $('btnActivate').disabled = false;
  $('keymsg').textContent = j.msg || '';
  $('keymsg').style.color = j.ok ? '#188038' : '#d93025';
};
$('keyin').addEventListener('keydown', e => { if (e.key === 'Enter') $('btnActivate').click(); });

const ICON = {ok: '✓', fail: '✗', run: '⏳', wait: '○', warn: '!', skip: '–'};
function render(s) {
  ready = s.ready; licensed = s.licensed;
  if (!restored && s.last && !pick) {   // mở lại app: về địa điểm tìm lần trước
    restored = true;
    if (s.last.label) $('q').value = s.last.label;
    choose(s.last.lat, s.last.lon, 15, true);
  }
  $('btnSet').disabled = !(ready && licensed && pick);
  $('setup').style.display = ready ? 'none' : 'block';
  $('keypanel').style.display = (ready && !licensed) ? 'block' : 'none';
  $('mcode').textContent = s.code || '';
  $('steps').innerHTML = s.steps.map(x =>
    `<li><span class="ic ${x.st}">${ICON[x.st] || ''}</span><span class="${x.st === 'wait' ? 'wait' : ''}">${x.label}</span></li>`).join('');
  const cur = s.steps.find(x => x.st === 'fail' || x.st === 'run');
  $('help').textContent = cur ? cur.note : '';
  const warn = s.steps.find(x => x.st === 'warn');
  if (!ready) $('dev').innerHTML = 'Chưa kết nối iPhone';
  else if (!licensed) $('dev').innerHTML = '✓ ' + s.device + ' · chờ kích hoạt';
  else $('dev').innerHTML = '✓ ' + s.device + (warn ? ' (có cảnh báo)' : '') + ' · đã kích hoạt · <a id="lnkRe">kiểm tra lại</a>';
  const l = document.getElementById('lnkRe'); if (l) l.onclick = () => post('/recheck');
}
async function poll() {
  try { render(await (await fetch('/status')).json()); } catch (e) {}
  setTimeout(poll, (ready && licensed) ? 4000 : 1200);
}
poll();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            return self.send(200, PAGE, "text/html")
        if self.path == "/status":
            return self.send(200, json.dumps(state))
        self.send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}
        if self.path == "/set":
            if not state["ready"]:
                return self.send(200, json.dumps({"ok": False, "msg": "iPhone chưa sẵn sàng, xem bảng hướng dẫn trên bản đồ."}))
            try:
                lat, lon = float(body["lat"]), float(body["lon"])
                assert -90 <= lat <= 90 and -180 <= lon <= 180
            except Exception:
                return self.send(400, json.dumps({"ok": False, "msg": "Toạ độ không hợp lệ"}))
            ok, msg = set_location(lat, lon)
            return self.send(200, json.dumps({"ok": ok, "msg": msg}))
        if self.path == "/stop":
            ok, msg = restore()
            return self.send(200, json.dumps({"ok": ok, "msg": msg}))
        if self.path == "/recheck":
            recheck()
            return self.send(200, json.dumps({"ok": True, "msg": "Đang kiểm tra lại kết nối..."}))
        if self.path == "/install-driver":
            ok, msg = install_driver()
            return self.send(200, json.dumps({"ok": ok, "msg": msg}))
        if self.path == "/activate":
            ok, msg = licensing.activate(str(body.get("key", "")))
            if ok:
                state["licensed"] = True
            return self.send(200, json.dumps({"ok": ok, "msg": msg}))
        if self.path == "/saveloc":
            try:
                lat, lon = float(body["lat"]), float(body["lon"])
                assert -90 <= lat <= 90 and -180 <= lon <= 180
            except Exception:
                return self.send(400, json.dumps({"ok": False}))
            label = str(body.get("label", ""))[:200]
            save_lastloc(lat, lon, label)
            state["last"] = {"lat": lat, "lon": lon, "label": label}
            return self.send(200, json.dumps({"ok": True}))
        self.send(404, "{}")


# ======================================================================
#  Khởi động
# ======================================================================
def cleanup():
    stopping.set()
    try:
        if state["ready"] or state["active"]:
            restore()
    except Exception:
        pass
    p = procs["tunnel"]
    if p and p.poll() is None:
        p.terminate()


def open_window(url):
    try:
        import webview
        webview.create_window(APP_TITLE, url, width=1150, height=780, min_size=(720, 520))
        webview.start()
        return
    except Exception as e:
        print("Không mở được cửa sổ riêng, dùng trình duyệt:", e)
    webbrowser.open(url)
    print(f"{APP_TITLE} đang chạy tại {url}. Nhấn Ctrl+C để thoát.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main():
    state["licensed"] = licensing.is_activated()
    state["code"] = licensing.short_code()
    state["last"] = load_lastloc()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    recheck()
    try:
        open_window(url)
    finally:
        cleanup()
        server.shutdown()


if __name__ == "__main__":
    argv = sys.argv[1:]
    if argv[:1] == ["--pmd"]:
        run_pmd_inprocess(argv[1:])
    elif argv[:1] == ["--tunnel-watch"]:
        tunnel_watch(int(argv[1]))
    elif argv[:1] == ["--version"]:
        print(APP_VERSION)
    elif argv[:1] == ["--whoami"]:                      # in mã máy, dùng khi hỗ trợ từ xa
        print("Mã máy:", licensing.short_code())
    elif argv[:1] == ["--reset"]:                       # xoá kích hoạt cục bộ trên máy này
        ok = licensing.reset_local()
        print("Đã xoá kích hoạt trên máy này." if ok else "Không xoá được.")
        print("Lưu ý: để dùng lại key trên máy khác, hãy 'unbind' key đó trên server (admin.php).")
    else:
        main()
