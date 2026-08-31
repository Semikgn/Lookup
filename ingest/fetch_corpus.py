"""Açık lisanslı Türkçe korpus çekici (tek seferlik, internet gerektirir).

Ana kaynak: Türkçe Wikipedia (CC BY-SA 4.0) — action API, düz metin extract.
Ek kaynak: ArchWiki (GFDL 1.3) — İngilizce how-to, az sayıda.

Her koşuda data/SOURCES.md yeniden üretilir (URL + lisans + atıf).

Kullanım:
    python -m ingest.fetch_corpus
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).resolve().parent.parent
VERI = KOK / "data"

# Türkçe Wikipedia maddeleri (redirects=1 ile yönlendirmeler çözülür).
WIKI_TR_MADDELERI = [
    "VLAN",
    "DNS",
    "DHCP",
    "TCP/IP",
    "Alt ağ",
    "Yönlendirme",
    "Güvenlik duvarı",
    "Yük dengeleme",
    "RAID",
    "Secure Shell",
    "HTTP durum kodları",
    "HTTP",
    "Systemd",
    "Ağ anahtarı",
    "IP adresi",
    "Yönlendirici",
    "Ethernet",
    "OSI modeli",
]

# ArchWiki ek how-to sayfaları (İngilizce, GFDL 1.3).
ARCHWIKI_SAYFALARI = [
    "Network configuration",
    "SSH keys",
    "Systemd",
]

KULLANICI_AJANI = "RagRouterTR/2.0 (egitim projesi; https://github.com/Semikgn/Rag-Router-TR)"


def _getir(url: str) -> bytes:
    istek = urllib.request.Request(url, headers={"User-Agent": KULLANICI_AJANI})
    with urllib.request.urlopen(istek, timeout=60) as yanit:
        return yanit.read()


def _dosya_adi(baslik: str, on_ek: str) -> str:
    temiz = re.sub(r"[^0-9a-zçğıöşü]+", "-", baslik.casefold().replace("i̇", "i")).strip("-")
    return f"{on_ek}-{temiz}.txt"


def wiki_tr_cek() -> list[dict]:
    kayitlar = []
    gorulen: set[str] = set()  # farklı başlıklar aynı maddeye yönlenebiliyor
    for baslik in WIKI_TR_MADDELERI:
        parametreler = urllib.parse.urlencode({
            "action": "query", "prop": "extracts", "explaintext": 1,
            "redirects": 1, "format": "json", "titles": baslik,
        })
        veri = json.loads(_getir(f"https://tr.wikipedia.org/w/api.php?{parametreler}"))
        sayfalar = veri["query"]["pages"]
        sayfa = next(iter(sayfalar.values()))
        metin = sayfa.get("extract", "")
        gercek_baslik = sayfa.get("title", baslik)
        if not metin or "missing" in sayfa:
            print(f"  [yok ] tr.wikipedia: {baslik}")
            continue
        if gercek_baslik in gorulen:
            print(f"  [tekrar] {baslik} -> {gercek_baslik} (atlandı)")
            continue
        gorulen.add(gercek_baslik)
        # Kaynakça/dipnot kuyruklarını at.
        metin = re.split(r"\n==+ (Kaynakça|Dış bağlantılar|Ayrıca bakınız)", metin)[0]
        dosya = VERI / _dosya_adi(gercek_baslik, "wiki")
        dosya.write_text(f"# {gercek_baslik}\n\n{metin.strip()}\n", encoding="utf-8")
        kayitlar.append({
            "dosya": dosya.name, "baslik": gercek_baslik, "dil": "tr",
            "url": f"https://tr.wikipedia.org/wiki/{urllib.parse.quote(gercek_baslik.replace(' ', '_'))}",
            "lisans": "CC BY-SA 4.0", "kaynak": "Türkçe Wikipedia",
        })
        print(f"  [tamam] tr.wikipedia: {gercek_baslik} ({len(metin)} karakter)")
        time.sleep(0.5)  # API nezaketi
    return kayitlar


class _EtiketSoyucu(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parcalar: list[str] = []
        self._atla = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script"):
            self._atla += 1
        if tag in ("p", "li", "h2", "h3", "pre"):
            self.parcalar.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self._atla:
            self._atla -= 1

    def handle_data(self, veri):
        if not self._atla:
            self.parcalar.append(veri)


def archwiki_cek() -> list[dict]:
    kayitlar = []
    for sayfa_adi in ARCHWIKI_SAYFALARI:
        parametreler = urllib.parse.urlencode({
            "action": "parse", "page": sayfa_adi, "prop": "text",
            "format": "json", "redirects": 1,
        })
        veri = json.loads(_getir(f"https://wiki.archlinux.org/api.php?{parametreler}"))
        html = veri.get("parse", {}).get("text", {}).get("*", "")
        if not html:
            print(f"  [yok ] archwiki: {sayfa_adi}")
            continue
        soyucu = _EtiketSoyucu()
        soyucu.feed(html)
        metin = re.sub(r"\n{3,}", "\n\n", "".join(soyucu.parcalar)).strip()
        metin = metin[:20000]  # how-to sayfaları çok uzun; ilk ~20k karakter yeter
        dosya = VERI / _dosya_adi(sayfa_adi, "archwiki")
        dosya.write_text(f"# {sayfa_adi} (ArchWiki)\n\n{metin}\n", encoding="utf-8")
        kayitlar.append({
            "dosya": dosya.name, "baslik": sayfa_adi, "dil": "en",
            "url": f"https://wiki.archlinux.org/title/{urllib.parse.quote(sayfa_adi.replace(' ', '_'))}",
            "lisans": "GFDL 1.3", "kaynak": "ArchWiki",
        })
        print(f"  [tamam] archwiki: {sayfa_adi} ({len(metin)} karakter)")
        time.sleep(0.5)
    return kayitlar


def sources_md_yaz(kayitlar: list[dict]) -> None:
    satirlar = [
        "# Korpus Kaynakları",
        "",
        "Bu klasördeki dokümanlar aşağıdaki açık lisanslı kaynaklardan",
        "`ingest/fetch_corpus.py` ile otomatik çekilmiştir. Metinler üzerinde",
        "yalnızca biçimsel temizlik (kaynakça kuyruğu kırpma, HTML soyma) yapılmıştır.",
        "",
        "| Dosya | Başlık | Dil | Kaynak | Lisans |",
        "|---|---|---|---|---|",
    ]
    for k in kayitlar:
        satirlar.append(
            f"| `{k['dosya']}` | [{k['baslik']}]({k['url']}) | {k['dil']} | {k['kaynak']} | {k['lisans']} |"
        )
    satirlar += [
        "",
        "- Türkçe Wikipedia içeriği [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.tr) ile lisanslıdır.",
        "- ArchWiki içeriği [GNU FDL 1.3](https://www.gnu.org/licenses/fdl-1.3.html) ile lisanslıdır.",
        "- Elle yazılmış proje dokümanları (`foundry-local.md`, `rag-mimarisi.md`, `proje-sss.md`) bu repoya aittir.",
    ]
    (VERI / "SOURCES.md").write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def main() -> int:
    VERI.mkdir(exist_ok=True)
    print("[1/2] Türkçe Wikipedia çekiliyor...")
    kayitlar = wiki_tr_cek()
    print("[2/2] ArchWiki çekiliyor...")
    kayitlar += archwiki_cek()
    sources_md_yaz(kayitlar)
    print(f"\nBitti: {len(kayitlar)} doküman + SOURCES.md yazıldı.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
