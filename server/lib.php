<?php
// Hàm dùng chung cho activate.php và admin.php

function db() {
    static $pdo = null;
    if ($pdo === null) {
        $pdo = new PDO('sqlite:' . VITRIAO_DB);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->exec('CREATE TABLE IF NOT EXISTS licenses (
            lkey TEXT PRIMARY KEY,
            machine TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen TEXT
        )');
    }
    return $pdo;
}

// Giải mã Base32 (RFC4648, bảng A-Z2-7) để khớp base64.b32encode của Python.
function base32_decode($s) {
    $s = strtoupper(preg_replace('/[^A-Z2-7]/i', '', $s));
    $alph = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    $bits = ''; $out = '';
    for ($i = 0; $i < strlen($s); $i++) {
        $v = strpos($alph, $s[$i]);
        if ($v === false) return false;
        $bits .= str_pad(decbin($v), 5, '0', STR_PAD_LEFT);
    }
    for ($i = 0; $i + 8 <= strlen($bits); $i += 8) {
        $out .= chr(bindec(substr($bits, $i, 8)));
    }
    return $out;
}

// Key hợp lệ nếu MAC khớp (HMAC-SHA256 của 4 byte payload, cắt 6 byte).
function key_is_valid($key) {
    $raw = base32_decode($key);
    if ($raw === false || strlen($raw) < 10) return false;
    $payload = substr($raw, 0, 4);
    $mac     = substr($raw, 4, 6);
    $calc    = substr(hash_hmac('sha256', $payload, VITRIAO_SECRET, true), 0, 6);
    return hash_equals($calc, $mac);
}

function normalize_key($k) {
    return strtoupper(preg_replace('/[^A-Za-z0-9-]/', '', trim($k)));
}

// Ký giấy phép: chữ ký Ed25519 trên "VITRIAO|v1|<key>|<machine>".
function sign_token($key, $machine) {
    $seed = hex2bin(ED25519_SEED_HEX);
    $kp   = sodium_crypto_sign_seed_keypair($seed);
    $sk   = sodium_crypto_sign_secretkey($kp);
    $msg  = 'VITRIAO|v1|' . $key . '|' . $machine;
    return bin2hex(sodium_crypto_sign_detached($msg, $sk));
}

function json_out($arr, $code = 200) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($arr, JSON_UNESCAPED_UNICODE);
    exit;
}
