"""Hızlı test CLI'ı: dokümanlardan Türkçe RAG cevabı.

Kullanım:
    python cli.py "DHCP kiralama süresi nedir?"
    python cli.py --mod duz "..."   # v1 düz kosinüs (karşılaştırma için)
    python cli.py --k 5 "..."       # daha fazla bağlam parçası
"""

import argparse
import sys
import time

from core import foundry, rag
from core.retriever import Retriever

# Windows konsolunda Türkçe karakterlerin bozulmaması için.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Türkçe offline RAG asistanı")
    ayristirici.add_argument("soru", help="Dokümanlara sorulacak soru")
    ayristirici.add_argument(
        "--mod", default="hibrit", choices=["duz", "hibrit"],
        help="Retrieval modu: duz = yalnız kosinüs (v1), hibrit = +BM25+kapsama",
    )
    ayristirici.add_argument("--k", type=int, default=3, help="Bağlam parça sayısı")
    args = ayristirici.parse_args()

    endpoint = foundry.endpoint_bul()
    model = foundry.model_coz("uretim", endpoint)
    print(f"[endpoint] {endpoint}")
    print(f"[model]    {model} (retrieval: {args.mod})")

    retriever = Retriever(mod=args.mod)
    baslangic = time.perf_counter()
    sonuc = rag.cevapla(args.soru, retriever=retriever, k=args.k, endpoint=endpoint)
    sure = time.perf_counter() - baslangic

    for p in sonuc.parcalar:
        print(f"[bağlam]   {p.kaynak} / parça {p.sira} "
              f"(skor {p.skor:.2f}, kosinüs {p.kosinus:.2f}, kapsama {p.kapsama:.2f})")
    if sonuc.reddedildi:
        print("[red]      domain dışı — model çağrılmadı")

    print(f"\n{sonuc.cevap}\n")
    print(f"[süre]     {sure:.1f} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
