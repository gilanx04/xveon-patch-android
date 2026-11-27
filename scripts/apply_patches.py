#!/usr/bin/env python3
"""
Terapkan tiga patch XVeon 9.1 ke hasil decode apktool.

Pemakaian:
    python3 scripts/apply_patches.py <direktori-hasil-decode>

Script berhenti dengan exit code non-zero bila salah satu pola tidak ditemukan,
sehingga tidak ada patch yang diam-diam terlewat.
"""

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"[GAGAL] {label}: pola ditemukan {count}x di {path} (harus 1x)"
        )
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"[OK]    {label}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)

    root = Path(sys.argv[1])
    if not (root / "smali").is_dir():
        raise SystemExit(f"[GAGAL] {root} bukan hasil decode apktool (smali/ tidak ada)")

    # ---------------------------------------------------------------- patch 0
    # Reorder probe: cp.cloudflare.com ke indeks 0. Ini dead code setelah patch
    # 02 (o0l tidak pernah jalan), dipertahankan agar build identik dengan rilis.
    gf = root / "smali/gf.smali"
    replace_once(
        gf,
        "    aput-object v0, v13, v17\n\n"
        "    .line 148\n    .line 149\n"
        "    aput-object v15, v13, v16\n",
        "    aput-object v15, v13, v17\n\n"
        "    .line 148\n    .line 149\n"
        "    aput-object v0, v13, v16\n",
        "00 reorder probe (dead code, parity rilis)",
    )

    # ---------------------------------------------------------------- patch 1
    main_activity = root / "smali/com/xveon/tunnelpro/MainActivity.smali"
    replace_once(
        main_activity,
        "    :goto_1\n    if-nez v0, :cond_4\n",
        "    :goto_1\n    goto :cond_4\n",
        "01 integrity gate (MainActivity.onCreate)",
    )

    # ---------------------------------------------------------------- patch 2
    gf = root / "smali/gf.smali"
    replace_once(
        gf,
        ".method public final o0l(J)V\n    .locals 45\n\n    .line 1\n",
        ".method public final o0l(J)V\n    .locals 45\n\n    return-void\n\n    .line 1\n",
        "02 bypass pre-flight (gf.o0l)",
    )

    # ---------------------------------------------------------------- patch 3
    ne = root / "smali/ne.smali"
    replace_once(
        ne,
        "    .line 385\n    move-wide/from16 v2, v19\n\n"
        "    .line 386\n    .line 387\n"
        "    invoke-virtual {v1, v2, v3}, Lgf;->o0l(J)V\n\n"
        "    .line 388\n    .line 389\n    .line 390\n",
        "    .line 385\n    .line 386\n    .line 387\n    .line 388\n    .line 389\n    .line 390\n",
        "03 hapus pemanggilan o0l di ne",
    )

    print("\nSemua patch diterapkan. Lanjut: apktool b, zipalign, apksigner.")


if __name__ == "__main__":
    main()
