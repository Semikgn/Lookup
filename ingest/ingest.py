"""Doküman ingest boru hattı: data/ -> chunk -> embedding -> SQLite.

Kullanım:
    python -m ingest.ingest            # data/ klasörünü indeksler
    python -m ingest.ingest --sifirla  # mevcut indeksi silip baştan kurar
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import foundry

# Windows konsolunda Türkçe karakterlerin bozulmaması için.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).resolve().parent.parent
VERI_KLASORU = KOK / "data"
DB_YOLU = KOK / "data" / "indeks.db"
HEDEF_PARCA_BOYU = 800   # karakter
TOPLU_GONDERIM = 8       # tek istekte embed edilecek parça sayısı


def dokuman_oku(yol: Path) -> str:
    if yol.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(sayfa.extract_text() or "" for sayfa in PdfReader(yol).pages)
    return yol.read_text(encoding="utf-8")


def parcala(metin: str, hedef_boy: int = HEDEF_PARCA_BOYU) -> list[str]:
    """Paragraf sınırlarına saygılı, ~hedef_boy karakterlik parçalara böler."""
    paragraflar = [p.strip() for p in metin.split("\n\n") if p.strip()]
    parcalar: list[str] = []
    aktif = ""
    for p in paragraflar:
        if aktif and len(aktif) + len(p) + 2 > hedef_boy:
            parcalar.append(aktif)
            aktif = p
        else:
            aktif = f"{aktif}\n\n{p}" if aktif else p
    if aktif:
        parcalar.append(aktif)
    return parcalar


def db_ac() -> sqlite3.Connection:
    baglanti = sqlite3.connect(DB_YOLU)
    baglanti.execute(
        """CREATE TABLE IF NOT EXISTS parcalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kaynak TEXT NOT NULL,
            sira INTEGER NOT NULL,
            metin TEXT NOT NULL,
            vektor BLOB NOT NULL
        )"""
    )
    return baglanti


def indeksle(sifirla: bool = False) -> int:
    dosyalar = sorted(
        d for d in VERI_KLASORU.iterdir()
        if d.suffix.lower() in {".txt", ".md", ".pdf"}
        and d.name != "SOURCES.md"  # kaynak listesi metadata'dır, korpus değil
    )
    if not dosyalar:
        print(f"UYARI: {VERI_KLASORU} içinde .txt/.md/.pdf yok.")
        return 0

    baglanti = db_ac()
    if sifirla:
        baglanti.execute("DELETE FROM parcalar")

    endpoint = foundry.endpoint_bul()
    toplam = 0
    for dosya in dosyalar:
        mevcut = baglanti.execute(
            "SELECT COUNT(*) FROM parcalar WHERE kaynak = ?", (dosya.name,)
        ).fetchone()[0]
        if mevcut:
            print(f"[atla] {dosya.name} zaten indeksli ({mevcut} parça)")
            continue

        parcalar = parcala(dokuman_oku(dosya))
        print(f"[embed] {dosya.name}: {len(parcalar)} parça...")
        for i in range(0, len(parcalar), TOPLU_GONDERIM):
            grup = parcalar[i:i + TOPLU_GONDERIM]
            vektorler = foundry.goml(grup, endpoint)
            for sira, (metin, vektor) in enumerate(zip(grup, vektorler), start=i):
                baglanti.execute(
                    "INSERT INTO parcalar (kaynak, sira, metin, vektor) VALUES (?, ?, ?, ?)",
                    (dosya.name, sira, metin,
                     np.asarray(vektor, dtype=np.float32).tobytes()),
                )
        baglanti.commit()
        toplam += len(parcalar)

    sayi = baglanti.execute("SELECT COUNT(*) FROM parcalar").fetchone()[0]
    print(f"Bitti: bu koşuda {toplam} yeni parça, veritabanında toplam {sayi} parça.")
    baglanti.close()
    return toplam


if __name__ == "__main__":
    ayristirici = argparse.ArgumentParser(description="data/ klasörünü indeksler")
    ayristirici.add_argument("--sifirla", action="store_true", help="indeksi baştan kur")
    args = ayristirici.parse_args()
    indeksle(sifirla=args.sifirla)
