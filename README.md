# Vị trí ảo iPhone

Đặt vị trí GPS ảo cho iPhone đã bật **Developer Mode**, qua dịch vụ mô phỏng vị
trí chính thức của Apple (giống Xcode / 3uTools) bằng thư viện
[`pymobiledevice3`](https://github.com/doronz88/pymobiledevice3). Giao diện bản
đồ chạy trong một cửa sổ app, không cần gõ lệnh. Bản phát hành khóa theo một máy
(node-locking), kích hoạt một lần.

> Chỉ dùng để mô phỏng vị trí trên thiết bị của chính mình (test app, chụp ảnh,
> điều hướng…). Việc dùng để gian lận chấm công, app gọi xe/giao hàng, hay game
> có thể khiến tài khoản bị khóa và vi phạm điều khoản của các dịch vụ đó.

## Cấu trúc

```
app/        vitriao.py (app chính), licensing.py (kích hoạt qua server), requirements.txt
server/     activate.php, admin.php, lib.php, config.sample.php (đặt lên hosting PHP)
tools/      keygen.py (sinh key bán), genkeys.py (sinh cặp khóa Ed25519)
build/      vitriao.spec (cấu hình PyInstaller onefile)
docs/       HUONG-DAN.txt (người dùng cuối), SERVER-kich-hoat.txt, DRIVER-cho-nguoi-phat-hanh.txt
.github/workflows/build.yml   (tự build .exe + .app trên GitHub)
```

## Chạy thử khi phát triển

```bash
pip install -r app/requirements.txt
# Windows: mở CMD bằng quyền Admin trước (iOS 17+ cần quyền này để tạo tunnel)
python app/vitriao.py
```

## Build bản phát hành bằng GitHub Actions (miễn phí)

1. Tạo repo **public** trên GitHub (tài khoản thường là đủ, Actions miễn phí
   không giới hạn với repo public), đẩy toàn bộ thư mục này lên.
2. Đặt 2 khóa bí mật trong **Settings → Secrets and variables → Actions → New
   repository secret**:
   - `VITRIAO_SECRET`: chuỗi ngẫu nhiên dài, giữ kín. Dùng để ký `license.dat`;
     ai có chuỗi này mới giả được giấy phép.
   - `VITRIAO_ADMIN`: mã quản trị để reset máy (xem dưới).
3. Vào tab **Actions**, workflow **Build** chạy và tạo bản build cho **Windows**
   và **macOS**. Tải ở mục **Artifacts**.
4. Muốn tạo bản Release tải về công khai: đẩy một tag, ví dụ
   `git tag v1.0.0 && git push --tags`.

> Không thể build chéo: `.exe` phải build trên Windows, `.app` phải build trên
> macOS. GitHub Actions lo cả hai nên không cần có sẵn hai máy.

## Phát hành ra USB

Chép ra USB: file chạy (`VitriAo.exe` hoặc `Vị trí ảo iPhone.app`) + `HUONG-DAN.txt`
+ thư mục `Driver/` (chứa trình cài driver Apple cho Windows).
- **Windows cần driver Apple một lần.** Nhét sẵn trình cài vào `Driver/` trên
  USB; app có nút "Cài driver Apple" tự chạy file đó, không cần mạng. Cách lấy
  file driver: xem `docs/DRIVER-cho-nguoi-phat-hanh.txt`. macOS nhận iPhone sẵn.
- Không ký số (bản miễn phí) nên lần đầu sẽ có cảnh báo SmartScreen (Windows) /
  Gatekeeper (macOS). `HUONG-DAN.txt` đã chỉ cách bỏ qua.

## Cơ chế kích hoạt bằng key (qua server, 1 key = 1 máy)

- App chạy tự do qua các bước cài driver / kết nối iPhone — **không cần key**.
  Khách xác nhận máy mình dùng được rồi mới cần nhập key → giảm hẳn khiếu nại
  "mua key xong không cài được".
- iPhone kết nối xong → app hiện **màn nhập key**. App gửi `{key, mã máy}` tới
  `activate.php` (**cần mạng lần này**). Server kiểm tra key + quy tắc 1-key-1-máy,
  trả về giấy phép đã ký (Ed25519). App xác minh chữ ký bằng **khóa công khai**
  rồi lưu `license.dat` (ẩn, trên USB).
- Lần sau app tự xác minh `license.dat` **offline**, không gọi server nữa.
- Key đó mang sang máy khác → server từ chối (đã gắn máy cũ). "Đổi vị trí" bị
  khóa tới khi kích hoạt thành công.

App chỉ chứa **khóa công khai** nên không thể tự tạo giấy phép giả; khóa bí mật
(seed Ed25519) nằm ở server của anh.

### Dựng server + sinh key

Xem `docs/SERVER-kich-hoat.txt`. Tóm tắt:

```bash
python tools/genkeys.py                           # sinh seed (cho server) + pubkey (cho app)
export VITRIAO_SECRET=chuoi-bi-mat-cua-anh         # trùng với config.php trên server
python tools/keygen.py 50 --out keys.csv           # sinh 50 key để bán
```

Build trên GitHub cần 2 secret: `VITRIAO_ACTIVATE_URL` (URL activate.php) và
`VITRIAO_PUBKEY` (khóa công khai). Workflow sẽ nhúng vào app.

### Mở khóa cho máy mới (khách đổi/cài lại máy)

Gọi admin trên server (thay MÃ, KEY):

```
admin.php?admin=MÃ&action=info&key=KEY      # xem key đang gắn máy nào
admin.php?admin=MÃ&action=unbind&key=KEY    # gỡ, cho kích hoạt lại ở máy mới
```

Trên máy khách, `VitriAo.exe --reset` chỉ xoá kích hoạt cục bộ; muốn dùng lại key
ở máy khác thì phải `unbind` trên server như trên. `--whoami` in mã máy.

### Giới hạn (nói thẳng)

File onefile vẫn có thể bị dịch ngược và vá bỏ bước kiểm tra — không hệ chống
sao chép offline nào tuyệt đối. Nhưng với khóa công khai + server, một key không
thể dùng trên hai máy, và app không thể bị "chế" key giả nếu không có seed.
Muốn khó dịch ngược hơn: thêm [PyArmor](https://pyarmor.dev) trước PyInstaller.
