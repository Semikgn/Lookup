"""Model sondası: adayı tam benchmark'a sokmadan önce 5 soruluk hızlı elek.

Ölçülen: soru başına latency (medyan dahil) + sistem kullanılabilir RAM'i +
foundry servis bellek kullanımı. Eleme kriteri (v2 brief): medyan > ~30 sn
ya da swap'e düşme belirtisi.

Kullanım:
    python -m bench.sonda phi-4-mini
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import foundry, rag
from core.retriever import Retriever

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# 2 RAG (bağlamlı, prefill'i zorlar) + 1 kod + 2 genel: gerçek yükün minyatürü.
SORULAR = [
    ("rag", "Bu projede neden vektör veritabanı kullanılmıyor?"),
    ("rag", "Foundry Local servisinin adresi hangi komutla öğrenilir?"),
    ("kod", "Python'da bir sayının faktöriyelini hesaplayan fonksiyon yaz."),
    ("genel", "Yarısı 8 olan sayı kaçtır?"),
    ("genel", "Bir haftada kaç gün vardır?"),
]


def ram_durumu() -> str:
    try:
        import psutil
        bos = psutil.virtual_memory().available / 1e9
        foundry_gb = sum(
            p.memory_info().rss for p in psutil.process_iter(["name"])
            if p.info["name"] and "foundry" in p.info["name"].lower()
        ) / 1e9
        return f"boş RAM {bos:.1f} GB, foundry {foundry_gb:.1f} GB"
    except Exception:
        return "psutil yok"


def main() -> int:
    alias = sys.argv[1] if len(sys.argv) > 1 else "phi-4-mini"
    endpoint = foundry.endpoint_bul()
    print(f"[sonda] {alias} @ {endpoint}")
    print(f"[başlangıç] {ram_durumu()}")

    yukleme_baslangici = time.perf_counter()
    foundry.model_yukle(alias)
    print(f"[yükleme] {time.perf_counter() - yukleme_baslangici:.0f} sn — {ram_durumu()}")

    retriever = Retriever()
    sureler = []
    for kategori, soru in SORULAR:
        baslangic = time.perf_counter()
        try:
            if kategori == "rag":
                cevap = rag.cevapla(soru, retriever=retriever, rol=alias, endpoint=endpoint).cevap
            else:
                cevap = foundry.sohbet(soru, rol=alias, endpoint=endpoint)
            hata = ""
        except Exception as exc:
            cevap, hata = "", f" HATA: {exc}"
        sure = time.perf_counter() - baslangic
        sureler.append(sure)
        print(f"  [{kategori:5}] {sure:6.1f} sn | {ram_durumu()}{hata}")
        print(f"          {cevap[:110]!r}")

    medyan = statistics.median(sureler)
    print(f"\n[sonuç] medyan {medyan:.1f} sn, en yavaş {max(sureler):.1f} sn")
    print("[karar] " + ("ELENDİ (medyan > 30 sn)" if medyan > 30 else "tam benchmark'a girebilir"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
