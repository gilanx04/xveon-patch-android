# Analisis Teknis — XVeon 9.1 vs LiteVLESS

Dokumen ini mencatat cara analisis dilakukan, struktur internal kedua aplikasi, dan bukti yang mendasari patch.

---

## 1. Artefak dan alat

| Artefak | Nama rilis | SHA-256 |
|---|---|---|
| XVeon asli | `XVeon-9.1-original.apk` | `0e15b822f7e150976fd05f0314a569c0f58012f3747efe52bcf97142f1f76167` |
| XVeon patch | `XVeon-9.1-patched.apk` | `38e1b686dd5372a49472d04f6a5a69fe42d7882ffd1cb732e6058890c5da9ce4` |
| LiteVLESS | `LiteVLESS-1.0.0-reference.apk` | `29a34f3f481e578a7ddd5d8908bd379a6b6d146bb9dc1ddec20ebdf904681f3a` |

Semua artefak tersedia di halaman [Releases](https://github.com/gilanx04/xveon-patch-android/releases/tag/v9.1-patch1).

Alat:

- `apktool` untuk decode/rebuild (dipakai untuk kedua APK).
- `aapt`, `apksigner`, `zipalign` untuk metadata dan signing.
- `uiautomator dump` untuk membaca log aplikasi di layar.
- `curl`, `ip route`, `getprop` untuk verifikasi runtime.
- REA untuk bind/hash artefak. Provider Android/JADX milik REA tidak tersedia di host ini:

  ```
  capability_unavailable / unsupported_provider
  Android JADX subprocess ownership is unsupported on android/arm64
  ```

  Karena itu bedah kode dilakukan dengan `apktool`.

---

## 2. XVeon 9.1 — struktur internal

### 2.1 Metadata

```
package      : com.xveon.tunnelpro
versionName  : 9.1
versionCode  : 9
minSdk       : 21
targetSdk    : 36
compileSdk   : 36
native libs  : tidak ada
dex          : 1 (classes.dex)
signer asli  : CN=ImamXveonv7, O=AnimeLovers, OU=Xveonv7, L=Tokyo, ST=Japan, C=JP
```

Tidak adanya native library penting: seluruh engine "Xray" XVeon adalah implementasi ulang di Java/Kotlin, bukan `libXray`/`libbox`.

### 2.2 Class kunci

| Class | Peran |
|---|---|
| `gf` | Engine Xray: transport, TLS/WS, VLESS handshake, verifikasi, watchdog |
| `ne` | Task connect (`Callable`), membangun transport lalu memanggil `gf.o0l(J)` |
| `me` | Runnable timeout untuk connect (`Lc2`), memanggil `gf.o0l(J)` |
| `ye` | Pembungkus stream VLESS: `Socket`, `InputStream`, `OutputStream`, `ef` |
| `ze` | Parser balasan VLESS + pesan error |
| `ue` | `ProbeTarget(kind, host, httpHost, port)` |
| `j9` | Pembangun config JSON Xray |
| `fd`, `g9`, `lllIl` | Parser/penulis URI dan preferensi (`allowInsecure`) |
| `XveonVpnService` | VPN service, watchdog, probe periodik |

### 2.3 Alur connect

```
XveonVpnService.connectInternal(profile)
 └─ gf.l0(...)                       // mulai engine
     ├─ buka TCP ke outbound
     ├─ TLS handshake (SNI)
     ├─ WebSocket upgrade  → "HTTP/1.1 101 Switching Protocols"
     ├─ VLESS handshake    → "Xray VLESS handshake & transport ready!"
     └─ gf.o0l(deadline)   → verifikasi pre-flight
         ├─ untuk setiap ProbeTarget:
         │    ├─ buka stream VLESS ke target
         │    ├─ kirim HEAD /generate_204 (kind 2) atau query DNS (kind 1)
         │    ├─ baca balasan, batas timeout_ping_probe_ms_v1
         │    └─ gagal → IOException
         └─ semua gagal → "Xray upstream timeout: server connected, but no internet response (...)"
```

`gf.o0l(J)` juga dipanggil dari `me.I()` (runnable timeout) dan dari `ne` pada jalur `:cond_10`.

### 2.4 Probe target

Dibangun di `gf.o0l`:

```smali
new-instance v0, Lue;  const-string v15, "1.1.1.1"
invoke-direct {v0, v15}, Lue;-><init>(Ljava/lang/String;)V          # kind 1, port 53

new-instance v15, Lue; const-string v10, "cp.cloudflare.com"
const/16 v5, 0x50
invoke-direct {v15, v10, v9, v10, v5}, Lue;-><init>(...)           # kind 2, port 80

new-instance v10, Lue; const-string v13, "connectivitycheck.gstatic.com"
invoke-direct {v10, v13, v9, v13, v5}, Lue;-><init>(...)           # kind 2, port 80

new-instance v5, Lue;  const-string v13, "8.8.8.8"
invoke-direct {v5, v13}, Lue;-><init>(Ljava/lang/String;)V          # kind 1, port 53
```

`ue` menyimpan: `I` = kind, `l` = host, `O` = HTTP Host header, `o` = port. Kind `1` = DNS over TCP, kind `2` = HTTP 204.

### 2.5 Pesan error sebagai bukti implementasi kustom

Dari `ze`:

```
Xray Transport/Payload Mismatch: non-VLESS banner (resp=0x..)
Xray Auth Fail: VLESS server rejected credential (resp=0x..)
VLESS stream closed/rejected by server (resp=0x..)
VLESS truncated response header (EOF)
VLESS stream closed by server (EOF)
```

Dari `gf`:

```
Xray upstream timeout: server connected, but no internet response (<pesan>)
Xray connect timed out (<detik>s)
Xray Auth Fail: <alasan>
```

Pesan-pesan ini tidak berasal dari Xray-core resmi. Xray-core resmi memakai format log yang berbeda dan tidak punya konsep "upstream timeout" untuk probe internal.

### 2.6 Preferensi timeout

Tersimpan di `shared_prefs/xveonv7_profiles_prefs.xml`:

```
timeout_xray_connect_sec_v1   = 3
timeout_ping_probe_ms_v1      = 1000
timeout_auto_reconnect_sec_v1 = 3
```

Budget 1000 ms dipakai per probe, sementara connect total dibatasi 3 detik.

### 2.7 Config JSON yang dihasilkan

Dibangun oleh `j9`. Bentuknya setara Xray config:

```jsonc
{
  "log": { "level": "info" },
  "inbounds": [ { "protocol": "socks"/"dokodemo-door", ... } ],
  "outbounds": [
    {
      "protocol": "vless",
      "settings": { "vnext": [ { "address": "...", "port": 443,
        "users": [ { "id": "<uuid>", "encryption": "none" } ] } ] },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": { "allowInsecure": true, "serverName": "<sni>" },
        "wsSettings": { "path": "/vless", "headers": { "Host": "<host>" } }
      }
    }
  ]
}
```

`allowInsecure: true` adalah kunci yang **ditolak** Xray-core resmi v26.x. XVeon menerimanya karena parser/engine-nya sendiri (`j9` menulis, `gf` membaca).

### 2.8 Kenapa reorder probe tidak menolong

Percobaan pertama: `cp.cloudflare.com:80` ditaruh paling depan. Hasil tetap:

```
HTTP/1.1 101 Switching Protocols
Xray upstream timeout: server connected, but no internet response (Read timed out)
```

`Read timed out` muncul pada pembacaan balasan di `ye`/`ze`, bukan pada koneksi ke probe. Artinya stream VLESS tambahan yang dibuka gate tidak pernah menghasilkan data yang bisa diparse — urutan target tidak relevan.

Percobaan kedua: menaikkan `timeout_ping_probe_ms_v1`. Hanya memperlambat kegagalan; stream tetap tidak membalas.

Kesimpulan: satu-satunya jalan adalah melewati gate.

---

## 3. LiteVLESS — struktur internal

### 3.1 Metadata

```
package      : com.litevless.app
compileSdk   : 35
native libs  : lib/arm64-v8a/libbox.so (± 20 MB), libandroidx.graphics.path.so
service      : com.litevless.app.service.VlessVpnService
```

### 3.2 Engine: sing-box

```
io.nekohasekai.libbox.Libbox
io.nekohasekai.libbox.BoxService
io.nekohasekai.libbox.SetupOptions
io.nekohasekai.libbox.PlatformInterface
```

Alur di `VlessVpnService.connectInternal()`:

```java
SetupOptions opt = new SetupOptions();
opt.setBasePath(...); opt.setWorkingPath(...); opt.setTempPath(...);
Libbox.setup(opt);

String config = k1.D.o(profile);      // builder config sing-box
Log.d(TAG, "Generated sing-box config:\n" + config);
BoxService svc = Libbox.newService(config, this);
svc.start();                          // langsung connected
```

Tidak ada pemanggilan probe, `generate_204`, atau `1.1.1.1` di jalur connect. String `1.1.1.1` dan `https://www.gstatic.com/generate_204` hanya muncul di bagian lain (DNS/health check opsional), bukan sebagai gate.

### 3.3 Config sing-box

Dibangun di `k1.D.o(VlessProfile)`:

| Bagian | Nilai |
|---|---|
| Inbound `tun` | `172.19.0.1/30`, MTU `9000`, `stack: gvisor`, `auto_route`, `sniff` |
| Inbound `mixed` | `127.0.0.1:20808` (`0x5148`) |
| Outbound | `vless`, `network: tcp`, UUID, `tls.enabled`, `utls.fingerprint: chrome`, `insecure` sesuai setting, `server_name` = SNI |
| Transport | `ws`, `path` dari profil, `headers.Host` dari profil |
| DNS | `1.1.1.1`, `8.8.8.8` melalui proxy; DNS lokal direct |
| Route | `ip_is_private` → `direct`, `final` → `proxy` |

### 3.4 Konsekuensi

Karena tidak ada gate, tunnel dianggap sukses begitu `BoxService.start()` tidak melempar exception. Request pertama dari aplikasi klien yang menentukan apakah server benar-benar meneruskan traffic. Pada server yang sama, hasilnya sukses — membuktikan config dan server valid, dan mempersempit masalah XVeon ke gate verifikasinya.

---

## 4. Perbandingan langsung

| Tahap | XVeon | LiteVLESS |
|---|---|---|
| Buka transport | TCP → TLS → WS | TCP → TLS → WS (utls chrome) |
| Handshake | VLESS custom (`gf`) | sing-box |
| Verifikasi | **probe HTTP/DNS, 1 s/probe, 3 s total** | tidak ada |
| Start tunnel | setelah verifikasi lolos | langsung |
| Kegagalan khas | `Xray upstream timeout` | error dari core saat request pertama |

---

## 5. Reproduksi

```bash
# decode
apktool d -f XVeon-9.1-original.apk -o dec

# lihat gate
grep -n "o0l(J)V" dec/smali/gf.smali
sed -n '/\.method public final o0l(J)V/,/\.end method/p' dec/smali/gf.smali | head -60

# lihat probe
grep -n "cp.cloudflare.com\|connectivitycheck.gstatic.com" dec/smali/gf.smali

# lihat pemanggil
grep -rn "Lgf;->o0l(J)V" dec/smali

# lihat integrity gate
grep -n "killProcess\|finishAndRemoveTask" dec/smali/com/xveon/tunnelpro/MainActivity.smali
```

Untuk LiteVLESS:

```bash
apktool d -f litevless.apk -o lite
sed -n '/connectInternal/,/^\.end method/p' lite/smali/com/litevless/app/service/VlessVpnService.smali | grep -n "Libbox\|BoxService\|config"
sed -n '/\.method public static o(Lcom\/litevless\/app\/model\/VlessProfile;)/,/\.end method/p' lite/smali/k1/D.smali | grep "const-string"
```

---

## 6. Catatan verifikasi runtime

```
$ ip -br addr show tun0
tun0  UNKNOWN  10.11.12.2/30

$ ip route get 1.1.1.1
1.1.1.1 dev tun0 table tun0 src 10.11.12.2 uid 0

$ curl -s -o /dev/null -w '%{http_code} %{time_total}\n' http://cp.cloudflare.com/generate_204
204 0.58

$ curl -s -o /dev/null -w '%{http_code}\n' https://example.com
200

$ curl -s https://api.ipify.org
213.163.200.41
```

Warning UDP yang muncul di log:

```
Local IP: 10.11.12.2
Xray UDP session warning (162.159.192.1:3138): Read timed out
Xray UDP: QUIC/443 unavailable on server; apps using TCP:443
```

`Local IP` adalah alamat `tun0`, bukan error. Warning UDP berasal dari sesi UDP aplikasi klien ke tujuan di range Cloudflare (`162.159.192.0/24`); transport VLESS over WS/TCP pada konfigurasi ini tidak membawa UDP, sehingga sesi tersebut gagal dan Xray fallback ke TCP 443. Dicatat per sesi, tidak memutus tunnel.
