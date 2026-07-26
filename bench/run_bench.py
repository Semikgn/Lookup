"""Türkçe benchmark koşucusu: modelleri testset.tr.json ile skorlar.

Her model için üç kategoride (rag, kod, genel) doğruluk ve gecikme ölçer,
sonucu bench/leaderboard.json'a yazar. Router bu dosyaya göre model seçer.

Kullanım:
    python -m bench.run_bench                          # varsayılan modeller
    python -m bench.run_bench --modeller qwen2.5-0.5b  # tek model
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import foundry, rag
from core.retriever import Retriever

BENCH_KLASORU = Path(__file__).resolve().parent
TESTSET_YOLU = BENCH_KLASORU / "testset.tr.json"
LEADERBOARD_YOLU = BENCH_KLASORU / "leaderboard.json"

VARSAYILAN_MODELLER = ["qwen2.5-0.5b", "qwen2.5-coder-1.5b", "qwen3-4b"]

GENEL_SISTEM = (
    "Sen Türkçe konuşan yardımcı bir asistansın. Kısa ve net cevap ver."
)


def cevap_puanla(cevap: str, anahtarlar: list[str], mod: str) -> bool:
    """Anahtar ifade eşleşmesi. Kısa/sayısal anahtarlarda kelime sınırı aranır."""
    metin = cevap.casefold()
    sonuclar = []
    for anahtar in anahtarlar:
        a = anahtar.casefold()
        if len(a) <= 3 and re.fullmatch(r"\w+", a, re.UNICODE):
            eslesme = re.search(rf"(?<!\w){re.escape(a)}(?!\w)", metin, re.UNICODE)
            sonuclar.append(eslesme is not None)
        else:
            sonuclar.append(a in metin)
    return all(sonuclar) if mod == "hepsi" else any(sonuclar)


def soruyu_calistir(
    soru: dict, model_alias: str, retriever: Retriever, endpoint: str
) -> tuple[bool, float, str]:
    """Tek soruyu koşturur: (doğru mu, süre, cevap) döndürür."""
    baslangic = time.perf_counter()
    if soru["kategori"] == "rag":
        sonuc = rag.cevapla(
            soru["soru"], retriever=retriever, rol=model_alias, endpoint=endpoint
        )
        cevap = sonuc.cevap
    else:
        cevap = foundry.sohbet(
            soru["soru"], rol=model_alias, sistem=GENEL_SISTEM, endpoint=endpoint
        )
    sure = time.perf_counter() - baslangic
    dogru = cevap_puanla(cevap, soru["anahtarlar"], soru.get("mod", "herhangi"))
    return dogru, sure, cevap


def modeli_skorla(
    model_alias: str, sorular: list[dict], retriever: Retriever, endpoint: str
) -> dict:
    print(f"\n=== {model_alias} ===")
    # Isınma: model yüklensin, ilk isteğin yükleme süresi ölçüme karışmasın.
    foundry.sohbet("Merhaba", rol=model_alias, endpoint=endpoint, max_tokens=8)

    kategoriler: dict[str, dict] = {}
    for soru in sorular:
        try:
            dogru, sure, _ = soruyu_calistir(soru, model_alias, retriever, endpoint)
        except Exception as hata:
            print(f"  [{soru['id']}] HATA: {hata}")
            dogru, sure = False, 0.0
        k = kategoriler.setdefault(
            soru["kategori"], {"dogru": 0, "toplam": 0, "sureler": []}
        )
        k["toplam"] += 1
        k["dogru"] += int(dogru)
        if sure:
            k["sureler"].append(sure)
        print(f"  [{soru['id']}] {'✓' if dogru else '✗'} ({sure:.1f} sn)")

    ozet = {}
    for ad, k in kategoriler.items():
        ozet[ad] = {
            "dogruluk": round(k["dogru"] / k["toplam"], 3),
            "ortalama_sure": round(sum(k["sureler"]) / len(k["sureler"]), 2)
            if k["sureler"] else None,
            "soru_sayisi": k["toplam"],
        }
    toplam_dogru = sum(k["dogru"] for k in kategoriler.values())
    toplam_soru = sum(k["toplam"] for k in kategoriler.values())
    return {
        "kategoriler": ozet,
        "genel_dogruluk": round(toplam_dogru / toplam_soru, 3),
    }


def tablo_yazdir(leaderboard: dict) -> None:
    print("\n" + "=" * 72)
    print(f"{'Model':<22} {'RAG':>8} {'Kod':>8} {'Genel':>8} {'Toplam':>8} {'~sn':>6}")
    print("-" * 72)
    for model, veri in sorted(
        leaderboard["modeller"].items(),
        key=lambda x: -x[1]["genel_dogruluk"],
    ):
        kat = veri["kategoriler"]
        sureler = [
            k["ortalama_sure"] for k in kat.values() if k.get("ortalama_sure")
        ]
        ort_sure = sum(sureler) / len(sureler) if sureler else 0
        print(
            f"{model:<22}"
            f" {kat.get('rag', {}).get('dogruluk', '-'):>8}"
            f" {kat.get('kod', {}).get('dogruluk', '-'):>8}"
            f" {kat.get('genel', {}).get('dogruluk', '-'):>8}"
            f" {veri['genel_dogruluk']:>8}"
            f" {ort_sure:>6.1f}"
        )
    print("=" * 72)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Türkçe benchmark koşucusu")
    ayristirici.add_argument(
        "--modeller", nargs="+", default=VARSAYILAN_MODELLER,
        help="Skorlanacak model alias'ları",
    )
    args = ayristirici.parse_args()

    sorular = json.loads(TESTSET_YOLU.read_text(encoding="utf-8"))["sorular"]
    endpoint = foundry.endpoint_bul()
    retriever = Retriever()
    yuklu = foundry.yuklu_modeller(endpoint)

    leaderboard = {
        "olusturulma": datetime.now(timezone.utc).isoformat(),
        "testset": TESTSET_YOLU.name,
        "modeller": {},
    }
    for alias in args.modeller:
        if alias not in yuklu:
            print(f"[atla] {alias} indirilmemiş (foundry model download {alias})")
            continue
        leaderboard["modeller"][alias] = modeli_skorla(
            alias, sorular, retriever, endpoint
        )
        # Sıradaki modele RAM açmak için bu modeli bellekten çıkar.
        try:
            foundry.model_bosalt(alias)
        except Exception:
            pass

    LEADERBOARD_YOLU.write_text(
        json.dumps(leaderboard, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nLeaderboard yazıldı: {LEADERBOARD_YOLU}")
    tablo_yazdir(leaderboard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
