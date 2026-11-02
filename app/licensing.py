#!/usr/bin/env python3
"""
licensing.py - Kích hoạt bằng KEY qua server (1 key = 1 máy), dùng offline sau đó.

Luồng:
  - App chạy tự do qua các bước cài/kết nối iPhone (không cần key).
  - iPhone kết nối xong -> app hiện màn nhập key.
  - Nhập key -> app gửi {key, mã máy} tới server (CẦN MẠNG lần này).
    Server kiểm tra key và quy tắc 1-key-1-máy, rồi trả về "giấy phép" đã ký
    (chữ ký Ed25519). App xác minh chữ ý bằng KHÓA CÔNG KHAI rồi lưu license.dat.
  - Lần sau: app tự xác minh license.dat OFFLINE, không gọi server nữa.

App chỉ chứa KHÓA CÔNG KHAI nên không thể tự tạo giấy phép giả. Khóa bí mật
nằm ở server của người bán.

Cấu hình trước khi build (đặt qua biến môi trường hoặc sửa trực tiếp):
  VITRIAO_ACTIVATE_URL : URL tới activate.php trên server của anh
  VITRIAO_PUBKEY       : khóa công khai Ed25519 (hex), lấy từ tools/genkeys.py
"""
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import uuid

def _cfg(attr, env, default):
    # Ưu tiên app/appconfig.py (sinh lúc build), rồi biến môi trường, rồi mặc định.
    try:
        import appconfig
        v = getattr(appconfig, attr, None)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(env, default)


ACTIVATE_URL = _cfg("ACTIVATE_URL", "VITRIAO_ACTIVATE_URL", "https://ĐỔI-TÊN-MIỀN/activate.php")
PUBLIC_KEY_HEX = _cfg("PUBLIC_KEY_HEX", "VITRIAO_PUBKEY", "ĐỔI-BẰNG-KHÓA-CÔNG-KHAI-HEX")
LIC_NAME = "license.dat"


# ----------------------------------------------------------------------
#  Vân tay máy
# ----------------------------------------------------------------------
def _raw_machine_id():
    try:
        if os.name == "nt":
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                               0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            val, _ = winreg.QueryValueEx(k, "MachineGuid")
            k.Close()
            if val:
                return str(val)
        elif sys.platform == "darwin":
            out = subprocess.check_output(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                          text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
    except Exception:
        pass
    return str(uuid.getnode())


def fingerprint():
    raw = (_raw_machine_id() or "").strip().lower()
    return hashlib.sha256(("vitriao|" + raw).encode("utf-8")).hexdigest()


def short_code(fp=None):
    """Mã máy ngắn để khách gửi cho người bán khi cần hỗ trợ."""
    return (fp or fingerprint())[:12].upper()


# ----------------------------------------------------------------------
#  Xác minh giấy phép (Ed25519, offline)
# ----------------------------------------------------------------------
def _message(key, fp):
    return ("VITRIAO|v1|" + key + "|" + fp).encode("utf-8")


def _verify_sig(key, fp, sig_hex):
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        pub.verify(bytes.fromhex(sig_hex), _message(key, fp))
        return True
    except Exception:
        return False


def normalize_key(k):
    return "".join(c for c in (k or "").strip().upper() if c.isalnum() or c == "-")


def _lic_path():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, LIC_NAME)


def _hide(path):
    if os.name == "nt":
        try:
            subprocess.run(["attrib", "+h", "+s", path], creationflags=0x08000000, check=False)
        except Exception:
            pass


def _read_lic():
    try:
        return json.load(open(_lic_path(), encoding="utf-8"))
    except Exception:
        return None


def is_activated():
    lic = _read_lic()
    if not lic:
        return False
    fp = fingerprint()
    return lic.get("m") == fp and _verify_sig(lic.get("key", ""), fp, lic.get("sig", ""))


def status():
    return "ok" if is_activated() else "need_key"


# ----------------------------------------------------------------------
#  Dùng thử 1 ngày
# ----------------------------------------------------------------------
TRIAL_SECONDS = 24 * 3600


def _trial_path():
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "trial.dat")


def _trial_start():
    try:
        return float(json.load(open(_trial_path(), encoding="utf-8")).get("start", 0))
    except Exception:
        return 0


def trial_used():
    return _trial_start() > 0


def trial_remaining():
    """Số giây dùng thử còn lại (0 nếu chưa bắt đầu hoặc đã hết)."""
    import time
    st = _trial_start()
    if st <= 0:
        return 0
    left = st + TRIAL_SECONDS - time.time()
    return int(left) if left > 0 else 0


def trial_active():
    return trial_remaining() > 0


def start_trial():
    """Bắt đầu dùng thử 1 ngày. Chỉ cho bắt đầu một lần. (ok, thông báo)."""
    import time
    if trial_active():
        return True, "Đang trong thời gian dùng thử."
    if trial_used():
        return False, "Bản dùng thử 1 ngày đã hết. Vui lòng nhập key để tiếp tục."
    try:
        p = _trial_path()
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"start": time.time()}, f)
        _hide(p)
    except Exception as e:
        return False, f"Không ghi được dữ liệu dùng thử lên USB. {e}"
    return True, "Đã bật dùng thử 1 ngày. Chúc bạn trải nghiệm vui vẻ!"


def can_use():
    return is_activated() or trial_active()


# ----------------------------------------------------------------------
#  Kích hoạt qua server
# ----------------------------------------------------------------------
def activate(key):
    """Gửi key + mã máy tới server, nhận giấy phép đã ký, lưu lại. (ok, thông báo)."""
    key = normalize_key(key)
    if len(key) < 8:
        return False, "Key không đúng định dạng."
    fp = fingerprint()
    payload = json.dumps({"key": key, "machine": fp}).encode("utf-8")
    req = urllib.request.Request(ACTIVATE_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            res = json.load(e)
        except Exception:
            return False, f"Máy chủ báo lỗi ({e.code}). Thử lại sau."
    except Exception:
        return False, "Không kết nối được máy chủ kích hoạt. Kiểm tra mạng rồi thử lại (chỉ lần đầu mới cần mạng)."

    if not res.get("ok"):
        return False, res.get("error", "Kích hoạt không thành công.")
    sig = res.get("token", "")
    if not _verify_sig(key, fp, sig):
        return False, "Giấy phép trả về không hợp lệ. Liên hệ người bán."
    try:
        p = _lic_path()
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"key": key, "m": fp, "sig": sig}, f)
        _hide(p)
    except Exception as e:
        return False, f"Không ghi được kích hoạt lên USB (USB có khóa chống ghi không?). {e}"
    return True, "Kích hoạt thành công! Giờ bạn có thể đổi vị trí."


def reset_local():
    """Xoá kích hoạt trên MÁY NÀY (file cục bộ). Lưu ý: muốn dùng lại key trên
    máy khác thì người bán phải 'unbind' key đó trên server (admin.php)."""
    try:
        p = _lic_path()
        if os.path.exists(p):
            if os.name == "nt":
                subprocess.run(["attrib", "-h", "-s", p], creationflags=0x08000000, check=False)
            os.remove(p)
        return True
    except Exception:
        return False
