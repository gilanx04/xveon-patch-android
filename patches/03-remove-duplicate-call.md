# Patch 03 — Hapus pemanggilan `o0l` di jalur connect `ne`

**File:** `smali/ne.smali`
**Method:** `call()` (task connect)
**Tujuan:** membersihkan alur setelah `gf.o0l(J)` dijadikan no-op.

---

## Konteks

Di `ne`, setelah transport siap:

```smali
new-instance v0, Ljava/lang/StringBuilder;
const-string v2, "Connecting to Xray outbound "
...
invoke-static {v14, v1, v11, v15, v2}, Lgf;->l0(...)V
```

lalu blok verifikasi:

```smali
move-wide/from16 v2, v19

invoke-virtual {v1, v2, v3}, Lgf;->o0l(J)V

sget-object v0, Luc;->I:Luc;
return-object v0
```

`v19` adalah deadline yang dihitung dari `Lgf;->lII()J` + timeout connect.

---

## Perubahan

```diff
-    move-wide/from16 v2, v19
-    invoke-virtual {v1, v2, v3}, Lgf;->o0l(J)V
-
     sget-object v0, Luc;->I:Luc;
     return-object v0
```

---

## Kenapa tetap perlu

Secara fungsional patch 02 sudah cukup (method no-op). Pemanggilan dihapus agar:

1. Tidak ada overhead pemanggilan dan penyiapan argumen.
2. Alur `ne` langsung `return` setelah transport siap, sehingga mudah dibaca saat audit.
3. Tidak ada keraguan apakah gate masih dieksekusi atau tidak.

---

## Verifikasi

Setelah rebuild, `grep -c "Lgf;->o0l(J)V" smali/ne.smali` harus menghasilkan `0`.
