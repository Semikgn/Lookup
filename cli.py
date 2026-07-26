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
    args = ayristirici.parse_args()

    endpoint = foundry.endpoint_bul()
    model = foundry.model_coz(args.rol, endpoint)
    print(f"[endpoint] {endpoint}")
    print(f"[model]    {model} (rol: {args.rol})")

    baslangic = time.perf_counter()
    cevap = foundry.sohbet(args.soru, rol=args.rol, sistem=VARSAYILAN_SISTEM, endpoint=endpoint)
    sure = time.perf_counter() - baslangic

    print(f"\n{cevap.strip()}\n")
    print(f"[süre]     {sure:.1f} sn")
    return 0


if __name__ == "__main__":
    sys.exit(main())
