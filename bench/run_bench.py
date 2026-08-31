"""Benchmark v2: retrieval-odaklı Türkçe RAG değerlendirmesi.

İki ayrı ölçüm:
1. RETRIEVAL (model'siz, hızlı): her mod (duz / hibrit) için hit@3 — sorunun
   altın dokümanından bir parça ilk 3'te mi? + domain-dışı red doğruluğu.
   Before/after tablosunun kaynağı budur.
2. UÇTAN UCA (modelli, yavaş): aday modeller hibrit RAG üzerinde cevap
   doğruluğu (anahtar eşleşme) + latency. Soru bazlı checkpoint + --limit ile
   dilimli koşulabilir (bu makinede uzun koşular kesintiye uğrayabiliyor).

Kullanım:
    python -m bench.run_bench --sadece-retrieval
    python -m bench.run_bench --modeller qwen2.5-coder-1.5b qwen3-1.7b
    python -m bench.run_bench --modeller qwen3-1.7b --limit 10
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import foundry, rag
from core.retriever import Retriever

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BENCH_KLASORU = Path(__file__).resolve().parent
TESTSET_YOLU = BENCH_KLASORU / "testset.tr.json"
LEADERBOARD_YOLU = BENCH_KLASORU / "leaderboard.json"
ARA_YOLU = BENCH_KLASORU / ".bench_ara.json"

VARSAYILAN_MODELLER = ["qwen2.5-coder-1.5b", "qwen3-1.7b"]


def _ara_oku() -> dict:
    if ARA_YOLU.exists():
        try:
            return json.loads(ARA_YOLU.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _ara_yaz(ara: dict) -> None:
    ARA_YOLU.write_text(json.dumps(ara, ensure_ascii=False, indent=1), encoding="utf-8")


def cevap_puanla(cevap: str, anahtarlar: list[str], mod: str) -> bool:
    metin = cevap.casefold()
    sonuclar = []
    for anahtar in anahtarlar:
        a = anahtar.casefold()
        if len(a) <= 3 and re.fullmatch(r"\w+", a, re.UNICODE):
            sonuclar.append(
                re.search(rf"(?<!\w){re.escape(a)}(?!\w)", metin, re.UNICODE) is not None
            )
        else:
            sonuclar.append(a in metin)
    return all(sonuclar) if mod == "hepsi" else any(sonuclar)


# --- 1) Retrieval ölçümü (model'siz) -------------------------------------

def retrieval_olc(sorular: list[dict], endpoint: str) -> dict:
    sonuc: dict = {}
    rag_sorulari = [s for s in sorular if s["kategori"] == "rag"]
    red_sorulari = [s for s in sorular if s["kategori"] == "red"]

    for mod in ("duz", "hibrit"):
        retriever = Retriever(mod=mod)
        isabet3 = isabet1 = 0
        kacanlar = []
        for soru in rag_sorulari:
            parcalar = retriever.ara(soru["soru"], k=3, endpoint=endpoint)
            if any(p.kaynak in soru["altin"] for p in parcalar):
                isabet3 += 1
            else:
                kacanlar.append(soru["id"])
            if parcalar and parcalar[0].kaynak in soru["altin"]:
                isabet1 += 1
        red_dogru = 0
        red_kacan = []
        for soru in red_sorulari:
            parcalar = retriever.ara(soru["soru"], k=3, endpoint=endpoint)
            if retriever.reddedilmeli(parcalar):
                red_dogru += 1
            else:
                red_kacan.append(soru["id"])
        sonuc[mod] = {
            "hit1": round(isabet1 / len(rag_sorulari), 3),
            "hit3": round(isabet3 / len(rag_sorulari), 3),
            "isabet": f"{isabet3}/{len(rag_sorulari)}",
            "red_dogru": f"{red_dogru}/{len(red_sorulari)}",
            "kacanlar": kacanlar,
            "red_kacan": red_kacan,
        }
        print(f"  [{mod:6}] hit@1 = {sonuc[mod]['hit1']}, hit@3 = {sonuc[mod]['hit3']} "
              f"({sonuc[mod]['isabet']}), red = {sonuc[mod]['red_dogru']}"
              + (f", kaçan: {kacanlar}" if kacanlar else "")
              + (f", red kaçan: {red_kacan}" if red_kacan else ""))
    return sonuc


# --- 2) Uçtan uca model ölçümü --------------------------------------------

def modeli_skorla(
    alias: str, sorular: list[dict], retriever: Retriever, endpoint: str,
    limit: int | None = None,
) -> dict | None:
    """None dönerse kısmi koşudur; checkpoint'ten devam edilir."""
    print(f"\n=== {alias} ===")
    ara = _ara_oku()
    model_ara: dict = ara.setdefault(alias, {})
    bekleyen = [s for s in sorular if s["id"] not in model_ara]
    if limit:
        bekleyen = bekleyen[:limit]

    if bekleyen:
        foundry.sohbet("Merhaba", rol=alias, endpoint=endpoint, max_tokens=8)  # ısınma

    for soru in bekleyen:
        baslangic = time.perf_counter()
        try:
            sonuc = rag.cevapla(
                soru["soru"], retriever=retriever, rol=alias, endpoint=endpoint
            )
            if soru["kategori"] == "red":
                dogru = sonuc.reddedildi
            else:
                dogru = (not sonuc.reddedildi) and cevap_puanla(
                    sonuc.cevap, soru["anahtarlar"], soru.get("mod", "herhangi")
                )
        except Exception as hata:
            print(f"  [{soru['id']}] HATA: {hata}")
            dogru = False
        sure = time.perf_counter() - baslangic
        model_ara[soru["id"]] = {"dogru": dogru, "sure": round(sure, 2)}
        _ara_yaz(ara)
        print(f"  [{soru['id']}] {'✓' if dogru else '✗'} ({sure:.1f} sn)")

    if len(model_ara) < len(sorular):
        print(f"  ... kısmi: {len(model_ara)}/{len(sorular)}, devam için tekrar çalıştır")
        return None

    rag_kayitlari = [model_ara[s["id"]] for s in sorular if s["kategori"] == "rag"]
    red_kayitlari = [model_ara[s["id"]] for s in sorular if s["kategori"] == "red"]
    sureler = [k["sure"] for k in rag_kayitlari if k["sure"]]
    return {
        "rag_dogruluk": round(sum(k["dogru"] for k in rag_kayitlari) / len(rag_kayitlari), 3),
        "ortalama_sure": round(sum(sureler) / len(sureler), 2) if sureler else None,
        "medyan_sure": round(statistics.median(sureler), 2) if sureler else None,
        "red_dogru": f"{sum(k['dogru'] for k in red_kayitlari)}/{len(red_kayitlari)}",
        "soru_sayisi": len(rag_kayitlari),
    }


def tablo_yazdir(leaderboard: dict) -> None:
    r = leaderboard.get("retrieval", {})
    if r:
        print("\nRetrieval (hit@3):")
        for mod, veri in r.items():
            print(f"  {mod:8} {veri['hit3']:>6}  (isabet {veri['isabet']}, red {veri['red_dogru']})")
    if leaderboard.get("modeller"):
        print(f"\n{'Model':<24} {'RAG doğruluk':>12} {'medyan sn':>10} {'red':>6}")
        print("-" * 56)
        for ad, v in sorted(
            leaderboard["modeller"].items(), key=lambda x: -x[1]["rag_dogruluk"]
        ):
            print(f"{ad:<24} {v['rag_dogruluk']:>12} {v['medyan_sure']:>10} {v['red_dogru']:>6}")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Türkçe RAG benchmark v2")
    ayristirici.add_argument("--modeller", nargs="+", default=VARSAYILAN_MODELLER)
    ayristirici.add_argument("--limit", type=int, default=None,
                             help="bu koşuda işlenecek en fazla soru")
    ayristirici.add_argument("--sadece-retrieval", action="store_true",
                             help="yalnız hit@3/red ölç, model koşturma")
    args = ayristirici.parse_args()

    sorular = json.loads(TESTSET_YOLU.read_text(encoding="utf-8"))["sorular"]
    endpoint = foundry.endpoint_bul()

    leaderboard = {
        "olusturulma": datetime.now(timezone.utc).isoformat(),
        "testset": TESTSET_YOLU.name,
        "retrieval": {},
        "modeller": {},
    }
    if LEADERBOARD_YOLU.exists():
        try:
            eski = json.loads(LEADERBOARD_YOLU.read_text(encoding="utf-8"))
            leaderboard["retrieval"] = eski.get("retrieval", {})
            leaderboard["modeller"] = eski.get("modeller", {})
        except (OSError, json.JSONDecodeError):
            pass

    print("[1] Retrieval ölçümü (duz vs hibrit)...")
    leaderboard["retrieval"] = retrieval_olc(sorular, endpoint)
    LEADERBOARD_YOLU.write_text(
        json.dumps(leaderboard, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if not args.sadece_retrieval:
        print("\n[2] Uçtan uca model ölçümü (hibrit mod)...")
        retriever = Retriever(mod="hibrit")
        yuklu = foundry.yuklu_modeller(endpoint)
        for alias in args.modeller:
            if alias not in yuklu:
                print(f"[atla] {alias} indirilmemiş")
                continue
            if alias in leaderboard["modeller"]:
                print(f"[atla] {alias} zaten skorlanmış")
                continue
            sonuc = modeli_skorla(alias, sorular, retriever, endpoint, limit=args.limit)
            if sonuc is None:
                continue
            leaderboard["modeller"][alias] = sonuc
            LEADERBOARD_YOLU.write_text(
                json.dumps(leaderboard, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                foundry.model_bosalt(alias)
            except Exception:
                pass

    print(f"\nLeaderboard yazıldı: {LEADERBOARD_YOLU}")
    tablo_yazdir(leaderboard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
