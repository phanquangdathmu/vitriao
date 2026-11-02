#!/usr/bin/env python3
"""
keygen.py - Sinh key bán hàng (phía người bán). Tự chứa, không phụ thuộc app.

Key là chuỗi ngắn XXXX-XXXX-XXXX-XXXX, ký bằng HMAC-SHA256 với VITRIAO_SECRET.
Server (activate.php) kiểm tra tính hợp lệ của key bằng CÙNG secret này, nên
secret ở keygen và ở server PHP phải TRÙNG nhau.

Dùng:
    export VITRIAO_SECRET=chuoi-bi-mat-cua-anh
    python tools/keygen.py 20 --out keys.csv            # sinh 20 key
    python tools/keygen.py --check XXXX-XXXX-XXXX-XXXX   # kiểm tra 1 key
"""
import argparse
import base64
import hashlib
import hmac
import os

SECRET = os.environ.get("VITRIAO_SECRET", "ĐỔI-CHUỖI-BÍ-MẬT-NÀY-TRƯỚC-KHI-BUILD").encode("utf-8")
MAC_BYTES = 6
COUNTER = os.path.join(os.path.dirname(__file__), "counter.txt")
_MASK = int.from_bytes(hmac.new(SECRET, b"vitriao-serial-mask", hashlib.sha256).digest()[:4], "big")


def _b32(b):
    return base64.b32encode(b).decode("ascii").rstrip("=")


def _unb32(s):
    s = s.upper().replace("-", "").replace(" ", "")
    s += "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s)


def _sign(payload):
    return hmac.new(SECRET, payload, hashlib.sha256).digest()[:MAC_BYTES]


def make_key(serial):
    payload = ((int(serial) & 0xFFFFFFFF) ^ _MASK).to_bytes(4, "big")
    s = _b32(payload + _sign(payload))
    return "-".join(s[i:i + 4] for i in range(0, len(s), 4))


def verify_key(key):
    try:
        raw = _unb32(key)
        payload, mac = raw[:4], raw[4:4 + MAC_BYTES]
        if len(payload) == 4 and hmac.compare_digest(mac, _sign(payload)):
            return int.from_bytes(payload, "big") ^ _MASK
    except Exception:
        pass
    return None


def _next():
    try:
        return int(open(COUNTER).read().strip())
    except Exception:
        return 1


def main():
    ap = argparse.ArgumentParser(description="Sinh key cho Vị trí ảo iPhone")
    ap.add_argument("count", nargs="?", type=int, default=1)
    ap.add_argument("--out", help="xuất CSV (serial,key)")
    ap.add_argument("--start", type=int, help="bắt đầu từ serial này")
    ap.add_argument("--check", help="kiểm tra một key")
    a = ap.parse_args()

    if "ĐỔI" in SECRET.decode("utf-8", "ignore"):
        print("CẢNH BÁO: đang dùng SECRET mặc định. Đặt VITRIAO_SECRET trước khi sinh key thật.\n")

    if a.check:
        s = verify_key(a.check)
        print(f"HỢP LỆ (serial {s})" if s is not None else "KHÔNG hợp lệ")
        return

    start = a.start if a.start is not None else _next()
    rows = [(n, make_key(n)) for n in range(start, start + a.count)]
    open(COUNTER, "w").write(str(start + a.count))

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write("serial,key\n")
            for n, k in rows:
                f.write(f"{n},{k}\n")
        print(f"Đã ghi {len(rows)} key vào {a.out} (serial {start}..{start + a.count - 1})")
    else:
        for n, k in rows:
            print(f"{n:>5}  {k}")


if __name__ == "__main__":
    main()
