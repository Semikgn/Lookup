"""Hızlı test CLI'ı.

Kullanım:
    python cli.py "Sorunuz buraya"            # varsayılan rol: genel
    python cli.py --rol kod "Python'da ..."   # kod modeline yönlendir
"""

import argparse
import sys
import time

from core import foundry

# Windows konsolunda Türkçe karakterlerin bozulmaması için.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

VARSAYILAN_SISTEM = (
    "Sen Türkçe konuşan yardımcı bir asistansın. Kısa, doğru ve akıcı Türkçe cevap ver."
)


def main() -> int:
    ayristirici = argparse.ArgumentParser(description="Foundry Local hızlı test CLI'ı")
    ayristirici.add_argument("soru", help="Modele sorulacak soru")
    ayristirici.add_argument(
        "--rol", default="genel", choices=["hizli", "genel", "kod"],
        help="Model rolü (varsayılan: genel)",
    )
    ayristirici.add_argument(
        "--rag", action="store_true",
        help="Cevabı data/ dokümanlarından RAG ile üret",
    )
    ayristirici.add_argument(
        "--mod", default="hibrit", choices=["duz", "hibrit"],
        help="Retrieval modu: duz = yalnız kosinüs (v1), hibrit = +BM25+kapsama",
    )
    args = ayristirici.parse_args()

    endpoint = foundry.endpoint_bul()
    model = foundry.model_coz(args.rol, endpoint)
    print(f"[endpoint] {endpoint}")
    print(f"[model]    {model} (rol: {args.rol}{', RAG' if args.rag else ''})")

    baslangic = time.perf_counter()
    if args.rag:
        from core import rag
        from core.retriever import Retriever
        retriever = Retriever(mod=args.mod)
        sonuc = rag.cevapla(args.soru, retriever=retriever, rol=args.rol, endpoint=endpoint)
        cevap = sonuc.cevap
        for p in sonuc.parcalar:
            print(f"[bağlam]   {p.kaynak} / parça {p.sira} "
                  f"(skor {p.skor:.2f}, kosinüs {p.kosinus:.2f}, kapsama {p.kapsama:.2f})")
        if sonuc.reddedildi:
            print("[red]      domain dışı — model çağrılmadı")
    else:
        cevap = foundry.sohbet(
            args.soru, rol=args.rol, sistem=VARSAYILAN_SISTEM, endpoint=endpoint
        )
    sure = time.perf_counter() - baslangic

    print(f"\n{cevap.strip()}\n")
    print(f"[süre]     {sure:.1f} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
