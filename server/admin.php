<?php
/**
 * Quản trị key (bảo vệ bằng VITRIAO_ADMIN). Dùng khi khách đổi/cài lại máy.
 *
 *   Xem trạng thái:  admin.php?admin=MÃ&action=info&key=XXXX-XXXX-XXXX-XXXX
 *   Mở khóa (gỡ gắn máy, cho kích hoạt lại ở máy mới):
 *                    admin.php?admin=MÃ&action=unbind&key=XXXX-XXXX-XXXX-XXXX
 *   Liệt kê gần đây: admin.php?admin=MÃ&action=list
 */
require __DIR__ . '/config.php';
require __DIR__ . '/lib.php';

if (!hash_equals(VITRIAO_ADMIN, $_GET['admin'] ?? '')) {
    json_out(['ok' => false, 'error' => 'Sai mã quản trị'], 403);
}

$action = $_GET['action'] ?? 'info';
$key    = normalize_key($_GET['key'] ?? '');
$pdo    = db();

if ($action === 'list') {
    $rows = $pdo->query('SELECT lkey, machine, created_at, last_seen FROM licenses ORDER BY created_at DESC LIMIT 200')
                ->fetchAll(PDO::FETCH_ASSOC);
    json_out(['ok' => true, 'count' => count($rows), 'rows' => $rows]);
}

if ($key === '') json_out(['ok' => false, 'error' => 'Thiếu key'], 400);

if ($action === 'unbind') {
    $pdo->prepare('DELETE FROM licenses WHERE lkey = ?')->execute([$key]);
    json_out(['ok' => true, 'msg' => 'Đã mở khóa. Khách nhập lại key là kích hoạt được trên máy mới.']);
}

// info
$st = $pdo->prepare('SELECT machine, created_at, last_seen FROM licenses WHERE lkey = ?');
$st->execute([$key]);
$r = $st->fetch(PDO::FETCH_ASSOC);
json_out(['ok' => true, 'valid_format' => key_is_valid($key), 'binding' => $r ?: null]);
