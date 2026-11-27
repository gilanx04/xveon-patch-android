# Patch 02 — Matikan verifikasi pre-flight `gf.o0l(J)`

**File:** `smali/gf.smali`
**Method:** `public final o0l(J)V`
**Tujuan:** menghapus gate yang membuka stream VLESS tambahan dan menuntut balasan HTTP/DNS dalam 1 detik.

---

## Apa yang dilakukan method ini

`o0l(J)` dipanggil setelah handshake VLESS selesai, dengan parameter `J` = deadline (epoch ms). Isinya:

1. Membaca daftar `ProbeTarget` dari `Lia;` (config outbound).
2. Menyiapkan empat target:

   | Target | Kind | Port |
   |---|---|---|
   | `1.1.1.1` | DNS over TCP | 53 |
   | `cp.cloudflare.com` | HTTP 204 | 80 |
   | `connectivitycheck.gstatic.com` | HTTP 204 | 80 |
   | `8.8.8.8` | DNS over TCP | 53 |

3. Untuk tiap target: buka stream VLESS baru, kirim request, baca balasan.
4. Bila tidak ada balasan dalam `timeout_ping_probe_ms_v1` (1000 ms) atau deadline `J` lewat, lempar `IOException` dengan pesan:

   ```
   Xray upstream timeout: server connected, but no internet response (<pesan>)
   ```

5. Exception ini membatalkan seluruh proses connect di `ne`.

Pada server yang diuji, langkah 3 selalu berakhir `Read timed out` meskipun handshake dan transport sukses. Gate tidak pernah lolos.

---

## Perubahan

Sisipkan `return-void` tepat setelah direktif `.locals`, sebelum badan method:

```diff
 .method public final o0l(J)V
     .locals 45
 
+    return-void
+
     .line 1
     move-object/from16 v1, p0
 
     .line 2
```

Method menjadi no-op: seluruh badan lama tetap ada (tidak dihapus) tetapi tidak pernah dieksekusi.

---

## Kenapa `return-void` dan bukan menghapus badan method

- Tidak mengubah `register` count atau label, sehingga aman terhadap verifier DEX.
- Tidak perlu menghitung ulang `.locals`/`.registers`.
- Mudah di-revert: hapus satu baris.
- Tidak menyentuh method lain yang mungkin memakai label yang sama.

---

## Efek samping

- Tidak ada probe konektivitas sebelum tunnel dipakai. Ini sama dengan perilaku LiteVLESS.
- Pesan "Verifying Xray VLESS authentication & protocol stream..." tidak lagi muncul di log.
- Watchdog periodik di `XveonVpnService` tetap berjalan dan tetap bisa memutus koneksi bila traffic benar-benar mati.
