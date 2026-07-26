"""Akıllı model router.

Soruyu önce türüne göre sınıflandırır (kod / rag / genel), sonra o kategoride
en iyi modeli bench/leaderboard.json'daki ÖLÇÜLMÜŞ skorlara göre seçer.
Model seçimi elle yazılmış kurallarla değil, benchmark sonuçlarıyla yapılır;
leaderboard yoksa core.foundry.MODEL_TERCIHLERI'ne geri düşülür.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core import foundry
from core.retriever import Retriever

LEADERBOARD_YOLU = Path(__file__).resolve().parent.parent / "bench" / "leaderboard.json"

# Kod sorusu işaretleri (intent sınıflandırma — model seçimi DEĞİL).
KOD_DESENLERI = [
    r"\bpython\b", r"\bkod\b", r"\bfonksiyon\b", r"\bsınıf tanımla\b", r"\bclass\b",
    r"\bdef\b", r"\blambda\b", r"\bdöngü\b", r"\bliste\b.*\byaz\b", r"```",
    r"\bscript\b", r"\bhata.*yakala\b", r"\bcomprehension\b", r"\byazılım\b",
]
RAG_BENZERLIK_ESIGI = 0.42  # retrieval bu skorun üstünde parça bulursa soru dokümanlarla ilgilidir


@dataclass
class RouterKarari:
    kategori: str
    model_alias: str
    model_id: str
    gerekce: str
    benzerlik: float | None = None


def _leaderboard_oku() -> dict | None:
    if not LEADERBOARD_YOLU.exists():
        return None
    try:
        return json.loads(LEADERBOARD_YOLU.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def kategori_bul(soru: str, retriever: Retriever | None, endpoint: str) -> tuple[str, float | None]:
    """Soruyu kod / rag / genel olarak sınıflandırır."""
    kucuk = soru.casefold()
    for desen in KOD_DESENLERI:
        if re.search(desen, kucuk):
            return "kod", None
    if retriever is not None:
        en_iyi = retriever.ara(soru, k=1, endpoint=endpoint)
        if en_iyi and en_iyi[0].skor >= RAG_BENZERLIK_ESIGI:
            return "rag", en_iyi[0].skor
        return "genel", en_iyi[0].skor if en_iyi else None
    return "genel", None


def model_sec(kategori: str, endpoint: str) -> tuple[str, str, str]:
    """Kategori için (alias, model_id, gerekçe) döndürür.

    Önce leaderboard'a bakar; skoru en yüksek (eşitlikte en hızlı) İNDİRİLMİŞ
    model seçilir. Leaderboard yoksa statik tercih listesine düşülür.
    """
    yuklu = foundry.yuklu_modeller(endpoint)
    leaderboard = _leaderboard_oku()

    if leaderboard and leaderboard.get("modeller"):
        adaylar = []
        for alias, veri in leaderboard["modeller"].items():
            kat = veri.get("kategoriler", {}).get(kategori)
            if kat is None or alias not in yuklu:
                continue
            adaylar.append((
                -kat["dogruluk"],
                kat.get("ortalama_sure") or 9999,
                alias,
                kat,
            ))
        if adaylar:
            adaylar.sort()
            _, _, alias, kat = adaylar[0]
            gerekce = (
                f"Leaderboard'da '{kategori}' kategorisinin en iyisi: "
                f"%{kat['dogruluk'] * 100:.0f} doğruluk, ~{kat.get('ortalama_sure', '?')} sn"
            )
            return alias, yuklu[alias], gerekce

    # Leaderboard yok ya da hiçbir aday inmemiş: statik tercih sırası.
    rol = {"kod": "kod", "rag": "genel", "genel": "genel"}[kategori]
    model_id = foundry.model_coz(rol, endpoint)
    alias = foundry.alias_bul(model_id, endpoint)
    return alias, model_id, (
        "Leaderboard bulunamadığı için varsayılan tercih listesinden seçildi"
    )


def yonlendir(
    soru: str,
    retriever: Retriever | None = None,
    endpoint: str | None = None,
) -> RouterKarari:
    endpoint = endpoint or foundry.endpoint_bul()
    if retriever is None:
        try:
            retriever = Retriever()
        except (FileNotFoundError, ValueError):
            retriever = None  # indeks yoksa RAG kategorisi devre dışı kalır

    kategori, benzerlik = kategori_bul(soru, retriever, endpoint)
    alias, model_id, gerekce = model_sec(kategori, endpoint)

    kategori_adi = {"kod": "kod sorusu", "rag": "doküman sorusu", "genel": "genel soru"}[kategori]
    if benzerlik is not None and kategori == "rag":
        kategori_adi += f" (doküman benzerliği {benzerlik:.2f})"

    return RouterKarari(
        kategori=kategori,
        model_alias=alias,
        model_id=model_id,
        gerekce=f"Soru '{kategori_adi}' olarak sınıflandırıldı. {gerekce}.",
        benzerlik=benzerlik,
    )
