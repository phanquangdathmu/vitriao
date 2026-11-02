#!/usr/bin/env python3
"""
genkeys.py - Sinh cặp khóa Ed25519 cho hệ kích hoạt qua server (chạy 1 lần).

    python tools/genkeys.py

In ra:
  • ED25519_SEED_HEX  -> đặt trong server PHP (config.php). GIỮ TUYỆT MẬT.
  • ED25519_PUBLIC_HEX -> dán vào app (licensing.py: PUBLIC_KEY_HEX) hoặc đặt
                          qua biến môi trường VITRIAO_PUBKEY khi build.

Khóa công khai thì lộ cũng không sao; khóa seed thì ai có là ký được giấy phép giả,
nên chỉ để trên server của anh.

(Không có Python? Dùng PHP: xem docs/SERVER-kich-hoat.txt)
"""
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sk = Ed25519PrivateKey.generate()
seed = sk.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                        serialization.NoEncryption())
pub = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

print("ED25519_SEED_HEX   =", seed.hex(), "   (ĐẶT Ở SERVER, GIỮ MẬT)")
print("ED25519_PUBLIC_HEX =", pub.hex(), "   (DÁN VÀO APP)")
