"""SQLite'taki embedding'ler üzerinde kaba kuvvet kosinüs benzerliği araması."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core import foundry

DB_YOLU = Path(__file__).resolve().parent.parent / "data" / "indeks.db"


@dataclass
class Parca:
    kaynak: str
    sira: int
    metin: str
    skor: float


class Retriever:
    """İndeksi belleğe alır, soru vektörüyle en benzer parçaları döndürür."""

    def __init__(self, db_yolu: Path = DB_YOLU):
        if not Path(db_yolu).exists():
            raise FileNotFoundError(
                f"İndeks bulunamadı: {db_yolu}. Önce `python -m ingest.ingest` çalıştır."
            )
        baglanti = sqlite3.connect(db_yolu)
        satirlar = baglanti.execute(
            "SELECT kaynak, sira, metin, vektor FROM parcalar"
        ).fetchall()
        baglanti.close()
        if not satirlar:
            raise ValueError("İndeks boş. Önce `python -m ingest.ingest` çalıştır.")

        self.kayitlar = [(k, s, m) for k, s, m, _ in satirlar]
        matris = np.stack([
            np.frombuffer(v, dtype=np.float32) for _, _, _, v in satirlar
        ])
        # Normları önden hesapla: her sorguda sadece iç çarpım kalır.
        self.matris = matris / np.linalg.norm(matris, axis=1, keepdims=True)

    def ara(self, soru: str, k: int = 3, endpoint: str | None = None) -> list[Parca]:
        soru_vektoru = np.asarray(foundry.goml([soru], endpoint)[0], dtype=np.float32)
        soru_vektoru /= np.linalg.norm(soru_vektoru)
        skorlar = self.matris @ soru_vektoru
        en_iyiler = np.argsort(skorlar)[::-1][:k]
        return [
            Parca(*self.kayitlar[i], skor=float(skorlar[i]))
            for i in en_iyiler
        ]
