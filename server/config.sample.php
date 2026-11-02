<?php
/**
 * Đổi tên file này thành config.php và điền giá trị thật.
 * KHÔNG đẩy config.php lên GitHub (đã có trong .gitignore).
 */

// Phải TRÙNG với VITRIAO_SECRET dùng ở tools/keygen.py để sinh key bán hàng.
define('VITRIAO_SECRET', 'ĐỔI-CHUỖI-BÍ-MẬT-NÀY');

// Seed Ed25519 (64 ký tự hex) lấy từ: python tools/genkeys.py
define('ED25519_SEED_HEX', 'ĐỔI-BẰNG-SEED-HEX');

// Mã quản trị để gọi admin.php (mở khóa / xem trạng thái key).
define('VITRIAO_ADMIN', 'ĐỔI-MÃ-QUẢN-TRỊ');

// File cơ sở dữ liệu SQLite. Nên đặt NGOÀI thư mục web công khai nếu có thể.
define('VITRIAO_DB', __DIR__ . '/licenses.sqlite');
