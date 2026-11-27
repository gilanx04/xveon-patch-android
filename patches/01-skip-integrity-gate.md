# Patch 01 — Lewati integrity gate di `MainActivity.onCreate`

**File:** `smali/com/xveon/tunnelpro/MainActivity.smali`
**Method:** `onCreate(Landroid/os/Bundle;)V`
**Tujuan:** mencegah aplikasi menutup diri saat APK di-re-sign dengan kunci lain.

---

## Apa yang dilakukan kode asli

`onCreate` menjalankan pemeriksaan identitas aplikasi:

```smali
invoke-virtual {v0}, Landroid/content/Context;->getPackageName()Ljava/lang/String;
move-result-object v5

sget-object v6, Le3;->O:[I
const v7, 0x5a3f8242
invoke-static {v6, v7}, Le3;->llI([II)Ljava/lang/String;
move-result-object v6

invoke-static {v5, v6}, Le3;->O(Ljava/lang/Object;Ljava/lang/Object;)Z
move-result v5

if-eqz v5, :cond_3
invoke-static {v0}, Le3;->IllIl(Landroid/content/Context;)Z
move-result v5
if-eqz v5, :cond_3
invoke-static {v0}, Le3;->lIlIl(Landroid/content/Context;)Z
move-result v0
if-eqz v0, :cond_3

const/4 v0, 0x1
goto :goto_0

:catchall_1
:cond_3
const/4 v0, 0x0

:goto_0
sput-boolean v0, Le3;->o:Z
```

Arti: nama paket harus sama dengan string yang di-deobfuscate, lalu `IllIl(Context)` dan `lIlIl(Context)` harus true. Hasilnya disimpan di `Le3;->o`.

Beberapa baris kemudian:

```smali
:goto_1
if-nez v0, :cond_4          # v0 = hasil integritas; 0 = gagal

:try_start_4
new-instance v0, Landroid/content/Intent;
const-class v2, Lcom/xveon/tunnelpro/vpn/XveonVpnService;
invoke-direct {v0, v1, v2}, Landroid/content/Intent;-><init>(Landroid/content/Context;Ljava/lang/Class;)V
invoke-virtual {v1, v0}, Landroid/content/Context;->stopService(Landroid/content/Intent;)Z

invoke-virtual {v1}, Landroid/app/Activity;->finishAndRemoveTask()V
...
invoke-static {}, Landroid/os/Process;->myPid()I
move-result v0
invoke-static {v0}, Landroid/os/Process;->killProcess(I)V
```

Jadi bila integritas gagal: service dihentikan, task ditutup, proses dibunuh.

Karena APK hasil patch ditandatangani dengan kunci sendiri, `IllIl`/`lIlIl` selalu false → aplikasi langsung mati beberapa milidetik setelah dibuka.

---

## Perubahan

```diff
     .line 87
     :goto_1
-    if-nez v0, :cond_4
+    goto :cond_4
 
     .line 88
     .line 89
     :try_start_4
```

Efeknya: blok kill tidak pernah dieksekusi, eksekusi selalu lanjut ke `:cond_4` (setup UI normal).

---

## Catatan

- `Le3;->o` tetap di-set `false`, tetapi nilainya tidak lagi memblokir startup. Kalau ada fitur lain yang membaca flag ini dan berperilaku berbeda, perilakunya hanya kosmetik.
- Patch ini **wajib** kalau APK di-re-sign. Tanpa patch ini, aplikasi tidak bisa dibuka sama sekali.
- Lokasi baris dapat bergeser bila versi XVeon berubah. Cari pola `:goto_1` yang diikuti `if-nez v0, :cond_4` dan blok `killProcess`.
