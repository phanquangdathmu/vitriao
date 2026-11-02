<?php
/**
 * Điểm kích hoạt. App gọi POST JSON {key, machine}.
 * Trả về: {ok:true, token:"<hex>"}  hoặc  {ok:false, error:"..."}
 *
 * Quy tắc 1 key = 1 máy:
 *   - key chưa gắn máy nào  -> gắn vào máy này, cấp token.
 *   - key đã gắn ĐÚNG máy này -> cấp lại token (kích hoạt lại bình thường).
 *   - key đã gắn máy khác   -> từ chối.
 */
require __DIR__ . '/config.php';
require __DIR__ . '/lib.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_out(['ok' => false, 'error' => 'Chỉ nhận POST'], 405);
}

$body    = json_decode(file_get_contents('php://input'), true) ?: [];
$key     = normalize_key($body['key'] ?? '');
$machine = preg_replace('/[^a-f0-9]/i', '', $body['machine'] ?? '');

if ($key === '' || $machine === '') {
    json_out(['ok' => false, 'error' => 'Thiếu key hoặc mã máy'], 400);
}
if (!key_is_valid($key)) {
    json_out(['ok' => false, 'error' => 'Key không hợp lệ']);
}

$now = gmdate('c');
$pdo = db();
$row = $pdo->prepare('SELECT machine FROM licenses WHERE lkey = ?');
$row->execute([$key]);
$cur = $row->fetchColumn();

if ($cur === false) {
    $ins = $pdo->prepare('INSERT INTO licenses (lkey, machine, created_at, last_seen) VALUES (?,?,?,?)');
    $ins->execute([$key, $machine, $now, $now]);
} elseif (hash_equals($cur, $machine)) {
    $pdo->prepare('UPDATE licenses SET last_seen = ? WHERE lkey = ?')->execute([$now, $key]);
} else {
    json_out(['ok' => false, 'error' => 'Key này đã kích hoạt trên một máy khác. Liên hệ người bán để được hỗ trợ.']);
}

json_out(['ok' => true, 'token' => sign_token($key, $machine)]);
