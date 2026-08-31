"""Türkçe metin işleme: tokenizasyon, stopword, stemming.

Hibrit retrieval'ın BM25/terim-kapsama sinyalleri bu modülden geçer.
Türkçe'ye özgü iki nokta:
- Büyük/küçük harf: 'İ' -> 'i' ve 'I' -> 'ı' (Python'un lower()'ı 'I' -> 'i'
  yaptığı için önce elle çevrilir).
- Sondan eklemeli dil: hafif stemming (snowballstemmer) olmadan "yönlendirici"
  ile "yönlendiricinin" eşleşmez; BM25 recall'u düşer.
"""

from __future__ import annotations

import re

import snowballstemmer

_STEMMER = snowballstemmer.stemmer("turkish")

# Kompakt Türkçe stopword listesi (arama sinyali taşımayan kelimeler).
STOPWORDS = {
    "acaba", "ama", "ancak", "arada", "aslında", "az", "bazı", "belki", "ben",
    "beni", "benim", "bir", "birçok", "biri", "birkaç", "birşey", "biz", "bize",
    "bu", "buna", "bunda", "bundan", "bunlar", "bunu", "bunun", "burada", "çok",
    "çünkü", "da", "daha", "de", "defa", "diye", "eğer", "en", "gibi", "hem",
    "hep", "hepsi", "her", "hiç", "için", "ile", "ise", "kez", "ki", "kim",
    "mı", "mi", "mu", "mü", "nasıl", "ne", "neden", "nedir", "nerde", "nerede",
    "nereye", "niçin", "niye", "o", "olan", "olarak", "oldu", "olduğu", "olur",
    "on", "ona", "ondan", "onlar", "onların", "onu", "onun", "öyle", "sanki",
    "şey", "siz", "şu", "tüm", "ve", "veya", "ya", "yani", "yapılan", "yapmak",
    "yer", "zaten",
}

_KELIME_DESENI = re.compile(r"[0-9a-zçğıöşü]+")


def kucult(metin: str) -> str:
    """Türkçe-duyarlı küçük harfe çevirme."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def tokenle(metin: str, stopword_at: bool = True, stemle: bool = True) -> list[str]:
    """Metni arama token'larına çevirir: küçült -> böl -> stopword -> stem."""
    kelimeler = _KELIME_DESENI.findall(kucult(metin))
    if stopword_at:
        kelimeler = [k for k in kelimeler if k not in STOPWORDS and len(k) > 1]
    if stemle:
        kelimeler = _STEMMER.stemWords(kelimeler)
    return kelimeler
