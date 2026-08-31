"""Hibrit retrieval: anlamsal kosinüs + BM25 + terim kapsama.

- `mod="duz"`: yalnızca embedding kosinüsü (v1 davranışı — before/after
  karşılaştırması için korunuyor).
- `mod="hibrit"`: üç sinyal, sorgu başına min-max normalize edilip
  AGIRLIKLAR ile karıştırılır (kosinüs [-1,1], BM25 sınırsız olduğundan
  normalizasyon şart; yoksa BM25 diğerlerini ezer).

Domain-dışı reddi: sıralama min-max ile yapıldığından en iyi sonucun
normalize skoru her zaman 1'dir; bu yüzden red kararı HAM sinyallere bakar
(en iyi kosinüs + terim kapsama, REDDET_* eşikleri). Eşikler benchmark'ta
kalibre edilir.

Depo: SQLite + NumPy, BM25 bellekte. Harici vektör DB bilinçli olarak yok.
"""

from __future__ import annotations

import math
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core import foundry, metin

DB_YOLU = Path(__file__).resolve().parent.parent / "data" / "indeks.db"

AGIRLIKLAR = {"anlamsal": 0.70, "bm25": 0.22, "kapsama": 0.08}
BM25_K1 = 1.5
BM25_B = 0.75

# Red kararı: (kosinüs, kapsama) düzleminde iki kademeli sınır. Herhangi bir
# (kos_esik, kap_esik) çifti için "en iyi kosinüs < kos_esik VE en iyi kapsama
# < kap_esik" sağlanıyorsa soru domain dışı sayılır. Sinyaller top-k'nin HAM
# maksimumudur (karışım sırasına değil). Kalibrasyon noktaları:
#   - domain-içi zor soru (rag-25):        kos 0.449, kap 0.29 -> CEVAPLA
#   - gri-bölge saha vakası (Chrome):      kos 0.469, kap 0.11 -> REDDET
#   - domain-dışı genel fiilli (baklava):  kos 0.24,  kap 0.33 -> REDDET
#   - domain-dışı tipik (Atatürk, dağ):    kos <= 0.39, kap <= 0.20 -> REDDET
REDDET_KURALLARI = [(0.48, 0.25), (0.40, 0.45)]
RED_MESAJI = "Bu bilgi mevcut dokümanlarda bulunamadı."


@dataclass
class Parca:
    kaynak: str
    sira: int
    metin: str
    skor: float          # sıralamada kullanılan skor (duz: kosinüs, hibrit: karışım)
    kosinus: float = 0.0  # ham anlamsal benzerlik
    kapsama: float = 0.0  # sorgu terimlerinin parçada bulunma oranı


class Retriever:
    """İndeksi belleğe alır; kosinüs + BM25 + kapsama ile en benzer parçaları bulur."""

    def __init__(self, db_yolu: Path = DB_YOLU, mod: str = "hibrit"):
        if mod not in ("duz", "hibrit"):
            raise ValueError(f"Bilinmeyen mod: {mod!r} ('duz' ya da 'hibrit')")
        self.mod = mod

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
        self.matris = matris / np.linalg.norm(matris, axis=1, keepdims=True)

        # BM25 indeksi (bellekte): parça başına token sayımları + idf tablosu.
        self._parca_tokenleri = [Counter(metin.tokenle(m)) for _, _, m in self.kayitlar]
        self._parca_boylari = np.array(
            [max(1, sum(c.values())) for c in self._parca_tokenleri], dtype=np.float64
        )
        self._ort_boy = float(self._parca_boylari.mean())
        n = len(self.kayitlar)
        dokuman_frekansi: Counter = Counter()
        for sayim in self._parca_tokenleri:
            dokuman_frekansi.update(sayim.keys())
        self._idf = {
            t: math.log(1 + (n - df + 0.5) / (df + 0.5))
            for t, df in dokuman_frekansi.items()
        }

    # --- sinyaller -------------------------------------------------------

    def _bm25(self, sorgu_tokenleri: list[str]) -> np.ndarray:
        skorlar = np.zeros(len(self.kayitlar))
        for t in sorgu_tokenleri:
            idf = self._idf.get(t)
            if idf is None:
                continue
            frekanslar = np.array(
                [c.get(t, 0) for c in self._parca_tokenleri], dtype=np.float64
            )
            payda = frekanslar + BM25_K1 * (
                1 - BM25_B + BM25_B * self._parca_boylari / self._ort_boy
            )
            skorlar += idf * (frekanslar * (BM25_K1 + 1)) / np.maximum(payda, 1e-9)
        return skorlar

    def _kapsama(self, sorgu_tokenleri: list[str]) -> np.ndarray:
        if not sorgu_tokenleri:
            return np.zeros(len(self.kayitlar))
        benzersiz = set(sorgu_tokenleri)
        return np.array([
            len(benzersiz & set(c)) / len(benzersiz) for c in self._parca_tokenleri
        ])

    @staticmethod
    def _minmax(dizi: np.ndarray) -> np.ndarray:
        aralik = dizi.max() - dizi.min()
        if aralik < 1e-9:
            return np.zeros_like(dizi)
        return (dizi - dizi.min()) / aralik

    # --- arama -----------------------------------------------------------

    def ara(self, soru: str, k: int = 3, endpoint: str | None = None) -> list[Parca]:
        soru_vektoru = np.asarray(foundry.goml([soru], endpoint)[0], dtype=np.float32)
        soru_vektoru /= np.linalg.norm(soru_vektoru)
        kosinus = self.matris @ soru_vektoru

        if self.mod == "duz":
            karisim = kosinus
            kapsama = np.zeros_like(kosinus)
        else:
            sorgu_tokenleri = metin.tokenle(soru)
            bm25 = self._bm25(sorgu_tokenleri)
            kapsama = self._kapsama(sorgu_tokenleri)
            karisim = (
                AGIRLIKLAR["anlamsal"] * self._minmax(kosinus)
                + AGIRLIKLAR["bm25"] * self._minmax(bm25)
                + AGIRLIKLAR["kapsama"] * kapsama
            )

        en_iyiler = np.argsort(karisim)[::-1][:k]
        return [
            Parca(
                *self.kayitlar[i],
                skor=float(karisim[i]),
                kosinus=float(kosinus[i]),
                kapsama=float(kapsama[i]),
            )
            for i in en_iyiler
        ]

    def reddedilmeli(self, parcalar: list[Parca]) -> bool:
        """Soru domain dışıysa True: modele hiç gitmeden 'bulunamadı' dönülür."""
        if not parcalar:
            return True
        # Kosinüs: top-k maksimumu (sıralama karışımından bağımsız, gürbüz).
        # Kapsama: en iyi sıradaki parçanın değeri — maksimum alınırsa "yapılır"
        # gibi genel fiil kökleriyle şişen alakasız parçalar redde engel oluyor.
        kosinus = max(p.kosinus for p in parcalar)
        kapsama = parcalar[0].kapsama

        # Embedding yanlış-pozitif freni: "X kimdir/nedir" kalıbı ansiklopedi
        # giriş parçalarına yüksek kosinüs verebiliyor (saha vakası: "fazıl say
        # kimdir" -> alt-ağ girişine 0.565). Sinyaller AYNI parçada buluşmalı:
        # top-k'de hem anlamsal (kosinüs >= 0.40) hem sözcüksel (kapsama >= 0.05)
        # eşiği birlikte geçen tek parça yoksa benzerlik aldatıcıdır, reddet.
        # (Yalnız-BM25 kaçağı da bunu geçemez: "say" kökü eşleşir ama kosinüsü düşüktür.)
        if not any(p.kosinus >= 0.40 and p.kapsama >= 0.05 for p in parcalar):
            return True

        return any(
            kosinus < kos_esik and kapsama < kap_esik
            for kos_esik, kap_esik in REDDET_KURALLARI
        )
