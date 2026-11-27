# XVeon Patch Android

Patch tidak resmi untuk **XVeon Tunnel Pro 9.1** (`com.xveon.tunnelpro`) agar profil VLESS yang sudah valid bisa connect — bukan terus-menerus *reconnect* dengan error:

```
Xray upstream timeout: server connected, but no internet response (Read timed out)
```

Penyebabnya bukan config, bukan server, dan bukan jaringan. Penyebabnya adalah **gate verifikasi internal XVeon** yang membuka stream VLESS sendiri sebelum tunnel dipakai, lalu mengharuskan probe HTTP/DNS di dalam stream itu membalas dalam 1 detik. Gate ini gagal di server yang sehat, sehingga koneksi yang sebenarnya sudah siap selalu dibatalkan.

Patch ini mematikan gate tersebut. Setelah patch, XVeon berperilaku seperti LiteVLESS: handshake selesai → tunnel langsung dipakai.

---

## Daftar isi

- [Status](#status)
- [Bukti hasil](#bukti-hasil)
- [Akar masalah](#akar-masalah)
- [Perbandingan XVeon vs LiteVLESS](#perbandingan-xveon-vs-litevless)
- [Patch yang dipasang](#patch-yang-dipasang)
- [Cara pakai APK rilis](#cara-pakai-apk-rilis)
- [Build sendiri dari APK original](#build-sendiri-dari-apk-original)
- [Known issues](#known-issues)
- [Keamanan & catatan](#keamanan--catatan)
- [Struktur repo](#struktur-repo)
- [Hash artefak](#hash-artefak)
- [Kredit](#kredit)

---

## Status

| Item | Nilai |
|---|---|
| Paket | `com.xveon.tunnelpro` |
| Versi | 9.1 (versionCode 9) |
| minSdk / targetSdk | 21 / 36 |
| Arsitektur | Universal — **tanpa native library**, semua logika di DEX |
| Root | Tidak wajib (hanya untuk fitur ShareNet/tethering) |
| Status patch | Berfungsi, terverifikasi di perangkat fisik |
| APK rilis | `XVeon-9.1-original.apk`, `XVeon-9.1-patched.apk` |

---

## Bukti hasil

Sebelum patch, log berhenti di:

```
Connecting to Xray outbound edu.udemy.com:443...
Xray VLESS handshake & transport ready!
HTTP/1.1 101 Switching Protocols
Xray upstream timeout: server connected, but no internet response (Read timed out)
```

Sesudah patch:

```
[08:19:20] Starting profile 'gatitkici'...
[08:19:20] Initializing Xray Core (VLESS over WebSocket (WS) + TLS)
[08:19:20] Connecting to Xray outbound edu.udemy.com:443...
[08:19:20] Xray VLESS handshake & transport ready!
[08:19:20] DNS: Primary DNS set to 1.1.1.1
[08:19:20] DNS: Secondary DNS set to 1.0.0.1
[08:19:20] VPN CONNECTED (gatitkici - 10.11.12.2/30)
```

Verifikasi dari shell:

```console
$ ip route get 1.1.1.1
1.1.1.1 dev tun0 table tun0 src 10.11.12.2 uid 0

$ curl -o /dev/null -w '%{http_code}\n' http://cp.cloudflare.com/generate_204
204

$ curl -o /dev/null -w '%{http_code}\n' https://example.com
200

$ curl -s https://api.ipify.org
213.163.200.41
```

Kuota yang terpakai adalah kuota jalur server (bukan kuota utama operator) — sama seperti saat memakai LiteVLESS.

---

## Akar masalah

### 1. XVeon punya pre-flight verification yang tidak dimiliki klien lain

Alur connect XVeon:

```
ne (ConnectTask)
 └─ gf.l0(...)        → buka TLS + WebSocket + VLESS handshake
     └─ gf.o0l(J)     → "Verifying Xray VLESS authentication & protocol stream..."
         ├─ buka stream VLESS baru ke probe target
         ├─ kirim request HTTP/DNS
         ├─ tunggu balasan  (timeout_ping_probe_ms_v1 = 1000 ms)
         └─ gagal → lempar IOException → seluruh koneksi dibatalkan
```

`gf.o0l(J)` adalah method di `gf.smali` (Xray engine XVeon). Ia membuka stream VLESS tambahan di atas transport yang sama, lalu mencoba beberapa target:

| Target | Jenis | Port |
|---|---|---|
| `1.1.1.1` | DNS over TCP | 53 |
| `cp.cloudflare.com` | HTTP `204` | 80 |
| `connectivitycheck.gstatic.com` | HTTP `204` | 80 |
| `8.8.8.8` | DNS over TCP | 53 |

Model target ada di class `ue` (`ProbeTarget`): field `I` = kind (`1` = DNS_TCP, `2` = HTTP_204), `l` = host, `O` = HTTP Host header, `o` = port. Constructor satu argumen memakai default kind `1`, port `53`.

Kalau tidak ada probe yang membalas dalam budget waktu, muncul:

```
Xray upstream timeout: server connected, but no internet response (<pesan>)
```

### 2. Client VLESS internal XVeon yang timeout, bukan servernya

Yang gagal adalah `ye` (pembungkus stream: `Socket` + `InputStream` + `OutputStream`) dan `ze` (parser balasan VLESS). Pesan-pesan `ze` menunjukkan ini implementasi VLESS buatan sendiri, bukan libXray:

```
Xray Transport/Payload Mismatch: non-VLESS banner (resp=0x..)
Xray Auth Fail: VLESS server rejected credential (resp=0x..)
VLESS stream closed/rejected by server (resp=0x..)
VLESS truncated response header (EOF)
VLESS stream closed by server (EOF)
```

Bukti tambahan bahwa ini engine kustom: config JSON yang dihasilkan XVeon memakai `"allowInsecure": true`, kunci yang **ditolak** Xray-core resmi v26.x. XVeon punya engine sendiri yang menerimanya.

Pada server ini, handshake dan transport berhasil (`101 Switching Protocols`), tetapi pembacaan balasan di dalam stream verifikasi selalu kena `Read timed out` — kira-kira 2 detik setelah upgrade. Artinya masalahnya ada di cara client kustom XVeon membaca frame balasan, bukan di server, bukan di probe, dan bukan di urutan probe.

### 3. Timeout terlalu ketat

Preferensi XVeon:

```
timeout_xray_connect_sec_v1 = 3
timeout_ping_probe_ms_v1    = 1000
timeout_auto_reconnect_sec_v1 = 3
```

Bahkan bila probe HTTP pertama (`cp.cloudflare.com`) didahulukan, 1000 ms tidak cukup untuk TLS + WS + VLESS + request/response pada jaringan seluler. Menaikkan timeout saja tidak memperbaiki akar masalahnya, karena stream verifikasi memang tidak pernah membalas.

**Kesimpulan:** gate verifikasi harus dilewati. Inilah yang dilakukan LiteVLESS sejak awal — ia tidak punya gate sama sekali.

---

## Perbandingan XVeon vs LiteVLESS

| Aspek | XVeon 9.1 | LiteVLESS |
|---|---|---|
| Engine | Implementasi Xray/VLESS sendiri di Java (`gf`, `ne`, `ye`, `ze`) | **sing-box** (`libbox.so`, `io.nekohasekai.libbox`) |
| Native lib | Tidak ada | `libbox.so` ± 20 MB (arm64-v8a) |
| Pre-flight verify | **Ya** — `gf.o0l(J)`, probe HTTP/DNS | **Tidak ada** |
| Setelah handshake | Verifikasi dulu, gagal → batal | Langsung `BoxService.start()` → connected |
| Transport | WS + TLS, `allowInsecure` | WS + TLS + `utls` fingerprint `chrome` |
| Inbound | `tun` 10.11.12.2/30 | `tun` 172.19.0.1/30, MTU 9000, gvisor |
| DNS | 1.1.1.1 / 1.0.0.1 | 1.1.1.1 / 8.8.8.8 via proxy |
| Route | manual | `ip_is_private` → direct, `final` → proxy |

Config sing-box LiteVLESS dibangun di `k1.D.o(VlessProfile)` lalu dipakai lewat:

```java
Libbox.setup(setupOptions);
BoxService svc = Libbox.newService(configJson, platformInterface);
svc.start();
```

Tidak ada satu pun pemanggilan probe/verifikasi di jalur itu. Karena itu LiteVLESS "langsung jalan" pada config yang sama.

Detail lengkap ada di [`docs/ANALYSIS.md`](docs/ANALYSIS.md).

---

## Patch yang dipasang

Tiga perubahan, semuanya di `smali`. Tidak ada perubahan pada config, server, atau kredensial.

### Patch 1 — lewati integrity gate di `MainActivity.onCreate`

XVeon memeriksa nama paket, lalu memanggil `Le3;->IllIl(Context)` dan `Le3;->lIlIl(Context)` (cek signature/installer), menyimpan hasilnya di `Le3;->o`. Kalau gagal, ia menjalankan blok keras:

```smali
invoke-virtual {v1, v0}, Landroid/content/Context;->stopService(Landroid/content/Intent;)Z
invoke-virtual {v1}, Landroid/app/Activity;->finishAndRemoveTask()V
invoke-static {}, Landroid/os/Process;->myPid()I
invoke-static {v0}, Landroid/os/Process;->killProcess(I)V
```

Karena APK di-re-sign dengan kunci sendiri, cek ini selalu gagal dan aplikasi langsung menutup diri. Patch: cabang yang menuju blok kill dibuat selalu dilewati.

```diff
 :goto_1
-if-nez v0, :cond_4
+goto :cond_4
```

### Patch 2 — matikan `gf.o0l(J)`

Seluruh isi method verifikasi di-*short-circuit*. Ini menghapus gate-nya tanpa menyentuh jalur transport.

```diff
 .method public final o0l(J)V
     .locals 45
 
+    return-void
+
     .line 1
     move-object/from16 v1, p0
```

### Patch 3 — hapus pemanggilan verifikasi di `ne.smali`

Pemanggilan di jalur connect dihapus agar alur tidak menyisakan pemanggilan yang tidak perlu.

```diff
-    move-wide/from16 v2, v19
-    invoke-virtual {v1, v2, v3}, Lgf;->o0l(J)V
-
     sget-object v0, Luc;->I:Luc;
     return-object v0
```

Dokumentasi per patch, termasuk potongan kode lengkap: [`patches/`](patches/).

### Yang **tidak** berhasil

- **Reorder probe** (menaruh `cp.cloudflare.com` di depan). Probe HTTP pertama tetap `Read timed out`.
- **Menaikkan timeout.** Stream verifikasi tidak pernah membalas, jadi waktu tambahan hanya memperlambat kegagalan.
- **Ganti probe ke IP literal / DNS.** Semua jenis probe gagal pada stream yang sama.

---

## Cara pakai APK rilis

1. Unduh `XVeon-9.1-patched.apk` dari halaman **Releases**.
2. Uninstall XVeon versi resmi lebih dulu (signature berbeda, tidak bisa menimpa):
   ```bash
   adb uninstall com.xveon.tunnelpro
   ```
3. Install APK patch:
   ```bash
   adb install XVeon-9.1-patched.apk
   ```
4. Buka app → import/pulihkan profil VLESS → Connect.

> Catatan: setelah install ulang, UID aplikasi berubah. Kalau kamu mem-backup `shared_prefs`, `chown` ulang ke UID baru sebelum dipakai.

---

## Build sendiri dari APK original

Butuh: `apktool`, `zipalign`, `apksigner`, JDK, dan keystore sendiri.

```bash
# 1. decode
apktool d -f XVeon-9.1-original.apk -o build/dec

# 2. terapkan tiga patch (script akan gagal kalau pola tidak cocok)
python3 scripts/apply_patches.py build/dec

# 3. rebuild
apktool b build/dec -o build/unsigned.apk
zipalign -f -p 4 build/unsigned.apk build/aligned.apk

# 4. sign
keytool -genkeypair -keystore my.jks -alias xveon -keyalg RSA -keysize 2048 \
        -validity 10000 -storepass secret -keypass secret -dname "CN=XVeon Patch"
apksigner sign --ks my.jks --ks-pass pass:secret --key-pass pass:secret \
        --out XVeon-9.1-patched.apk build/aligned.apk

# 5. install
adb install -r XVeon-9.1-patched.apk
```

Atau pakai pembungkusnya:

```bash
KS=my.jks KS_PASS=secret KEY_PASS=secret bash scripts/build.sh XVeon-9.1-original.apk
```

> Di Termux, jalankan dengan `bash scripts/build.sh ...` karena shebang `/usr/bin/env` tidak tersedia.

`scripts/apply_patches.py` memverifikasi setiap pola dan berhenti dengan exit code non-zero bila ada yang tidak ketemu — tidak ada patch yang diam-diam terlewat. Script ini mereproduksi `classes.dex` yang **byte-identik** dengan APK rilis:

```
05d66c06eba240a6090c54fd00c47c25ad445ef65f843bd37113d00387d1a3a9  classes.dex
```

---

## Known issues

| Gejala | Status | Penjelasan |
|---|---|---|
| `Xray UDP session warning (...): Read timed out` | **Non-fatal** | Server tidak meneruskan UDP/QUIC. Xray fallback ke TCP:443 (`Xray UDP: QUIC/443 unavailable on server; apps using TCP:443`). Traffic tetap normal. |
| `ShareNet [Root]: Failed to apply su iptables/ip-rule` | Non-fatal | Helper root gagal di sebagian ROM. Hanya memengaruhi tethering/hotspot sharing, bukan VPN utama. |
| Update resmi menimpa patch | Diharapkan | APK ini self-signed. Update dari Play Store/developer akan ditolak sampai versi resmi di-uninstall. |
| `allowInsecure: true` di config | Diharapkan | Engine XVeon menerima kunci ini; Xray-core resmi menolaknya. Jangan pakai config XVeon di core resmi. |

### Log yang wajar muncul

Contoh log saat tunnel sehat:

```
Local IP: 10.11.12.2

[09:21:39] Xray UDP session warning (162.159.192.1:3138): Read timed out
[09:21:40] Xray UDP: QUIC/443 unavailable on server; apps using TCP:443
```

- `Local IP: 10.11.12.2` — alamat interface `tun0` (sama dengan `VPN CONNECTED (… - 10.11.12.2/30)`). Ini baris status, **bukan warning**.
- `Xray UDP session warning (162.159.192.1:3138): Read timed out` — satu sesi UDP dari aplikasi klien tidak mendapat balasan. Alamat tujuan berada di range Cloudflare (`162.159.192.0/24`); IP dan port bisa berbeda tergantung aplikasi yang sedang jalan. XVeon mencatatnya **per sesi** dan tidak memutus tunnel.
- `Xray UDP: QUIC/443 unavailable on server; apps using TCP:443` — fallback otomatis. Transport VLESS di atas WebSocket/TCP pada konfigurasi ini tidak membawa UDP (butuh XUDP/mux), jadi aplikasi yang memakai QUIC/HTTP3 dialihkan ke TCP 443.

Warning UDP bisa berulang tiap beberapa puluh detik selama ada aplikasi yang mencoba UDP. Selama status tetap `CONNECTED` dan `curl` masih membalas `204`/`200`, tunnel tidak bermasalah.

---

## Keamanan & catatan

- **Kredensial disensor.** UUID, host WS, dan SNI di dokumentasi ini sebagian ditutup (`****`). Jangan pernah commit config asli ke repo publik.
- APK original disertakan hanya untuk keperluan backup/diff. Hak cipta tetap milik pembuat XVeon.
- APK LiteVLESS disertakan hanya sebagai bahan pembanding analisis. Itu build debug (`CN=Android Debug`), bukan rilis resmi, dan hak ciptanya tetap milik pembuat LiteVLESS.
- APK patch ditandatangani dengan kunci pengembang repo ini, bukan kunci resmi XVeon. Jangan gunakan untuk berpura-pura sebagai rilis resmi.
- Patch hanya mengubah perilaku verifikasi di sisi klien. Tidak ada traffic yang dikirim ke pihak ketiga, tidak ada telemetri tambahan.

---

## Struktur repo

```
.
├── README.md                  # dokumen ini
├── LICENSE                    # MIT untuk dokumentasi & script
├── docs/
│   └── ANALYSIS.md            # bedah teknis XVeon vs LiteVLESS
├── patches/
│   ├── 01-skip-integrity-gate.md
│   ├── 02-bypass-vless-preflight.md
│   └── 03-remove-duplicate-call.md
└── scripts/
    ├── apply_patches.py       # menerapkan 3 patch + verifikasi
    └── build.sh               # decode → patch → build → sign
```

---

## Hash artefak

| File | Ukuran | SHA-256 |
|---|---|---|
| `XVeon-9.1-original.apk` | 787 KB | `0e15b822f7e150976fd05f0314a569c0f58012f3747efe52bcf97142f1f76167` |
| `XVeon-9.1-patched.apk` | 852 KB | `38e1b686dd5372a49472d04f6a5a69fe42d7882ffd1cb732e6058890c5da9ce4` |
| `LiteVLESS-1.0.0-reference.apk` | 8.3 MB | `29a34f3f481e578a7ddd5d8908bd379a6b6d146bb9dc1ddec20ebdf904681f3a` |

`LiteVLESS-1.0.0-reference.apk` dilampirkan sebagai bahan pembanding untuk [`docs/ANALYSIS.md`](docs/ANALYSIS.md). Aplikasi ini ditandatangani dengan **Android Debug** key (`CN=Android Debug`), jadi ini build debug milik pembuatnya — bukan rilis resmi. Hak cipta tetap milik pembuat LiteVLESS; di repo ini hanya disimpan untuk dokumentasi dan reproduksi analisis.

Signature APK patch:

```
CN=XVeon Patch
SHA-256: ec4eb658aeecb158e01bf9a4a4bc2cfcd9b7059bcd3267e1d039e00ed04121eb
```

---

## Kredit

- XVeon Tunnel Pro — pembuat aplikasi asli.
- Analisis dan patch: [@gilanx04](https://github.com/gilanx04).
- Bedah LiteVLESS memakai `apktool`; bind/hash artefak memakai REA.

Lisensi dokumentasi dan script: [MIT](LICENSE). APK tidak termasuk dalam lisensi tersebut.
