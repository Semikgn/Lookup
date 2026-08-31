"""RAG zinciri: retrieve -> Türkçe prompt -> generate."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core import foundry, metin
from core.retriever import Parca, Retriever

RAG_SISTEM_PROMPTU = (
    "Sen Türkçe konuşan bir doküman asistanısın. SADECE sana verilen bağlam "
    "parçalarındaki bilgiyi kullanarak cevap ver. Bağlamda olmayan komut, menü "
    "yolu ya da adım UYDURMA; bağlam soruyu tam karşılamıyorsa hangi kısmın "
    "dokümanlarda olmadığını açıkça söyle. ÇOK KISA yaz: en fazla 3 kısa cümle "
    "ya da 3 madde; sorunun sorduğundan fazlasını anlatma. Aynı bilgiyi veya "
    "maddeyi asla tekrarlama."
)


@dataclass
class RagCevabi:
    cevap: str
    model: str
    parcalar: list[Parca] = field(default_factory=list)
    reddedildi: bool = False  # domain dışı: modele gidilmedi


BAGLAM_PARCA_LIMITI = 600  # karakter; CPU'da prefill süresinin ana kalemi


def _kirp(metin_parcasi: str, soru: str, limit: int = BAGLAM_PARCA_LIMITI) -> str:
    """Parçayı soruyla EN İLGİLİ cümleleri seçerek limite kırpar.

    Kör baş-kırpma parçanın asıl bilgisini atabiliyor (RAID aynalama vakası);
    bunun yerine cümleler soru kökleriyle örtüşmeye göre puanlanır, en iyiler
    orijinal sırayla tutulur. Saf lexical seçim — reranker modeli değil.
    """
    if len(metin_parcasi) <= limit:
        return metin_parcasi
    soru_kokleri = set(metin.tokenle(soru))
    cumleler = [c for c in re.split(r"(?<=[.!?])\s+|\n", metin_parcasi) if c.strip()]
    puanli = []
    for sira, c in enumerate(cumleler):
        ortusme = len(soru_kokleri & set(metin.tokenle(c)))
        puanli.append((-ortusme, sira, c))  # örtüşme çoksa önce; eşitse erken cümle
    secilen: list[int] = []
    uzunluk = 0
    for _, sira, c in sorted(puanli):
        if uzunluk + len(c) > limit and secilen:
            continue
        secilen.append(sira)
        uzunluk += len(c) + 1
    return " ".join(cumleler[i] for i in sorted(secilen))


def baglam_kur(parcalar: list[Parca], soru: str) -> str:
    bloklar = [
        f"[Kaynak: {p.kaynak} / parça {p.sira}]\n{_kirp(p.metin, soru)}"
        for p in parcalar
    ]
    return "\n\n---\n\n".join(bloklar)


# Sohbetin kendisi hakkındaki sorular ("az önce ne sordum") doküman araması
# değil, geçmişe bakma gerektirir; retrieval bu tür cümlelerde yanıltıcı
# şekilde proje dokümanlarını buluyor.
SOHBET_META_DESENLERI = [
    r"az önce", r"\bdemin\b", r"ne sordum", r"ne demiştim", r"ne dedim",
    r"nereden anladın", r"önceki (soru|mesaj|cevab)", r"hangi soruyu",
    r"sohbet(i|in) özetle", r"tekrar (açıkla|anlat|söyle)", r"\bneymiş\b",
    r"bir daha (açıkla|anlat|söyle)",
]

SOHBET_SISTEM_PROMPTU = (
    "Sen Türkçe konuşan bir doküman asistanısın. Bu soruyla ilgili bilgi "
    "dokümanlarda BULUNAMADI. Soru sohbetin kendisiyle ilgiliyse (örneğin "
    "'az önce ne sordum', 'nereden anladın') önceki mesajlara dayanarak KISACA "
    "cevapla. Değilse, bu bilginin mevcut dokümanlarda olmadığını söyle; "
    "uydurma."
)


def _gecmis_metni(gecmis: list[dict] | None) -> str:
    """Son alışverişleri düz transkripte çevirir.

    Küçük modeller chat-rol geçmişini takip edemiyor ('az önce ne sordum'a
    uydurma cevap veriyordu); açık 'Kullanıcı:/Asistan:' transkripti çok daha
    güvenilir. Prompt şişmesin diye kırpılır.
    """
    satirlar = []
    for tur in (gecmis or [])[-3:]:
        if tur.get("soru"):
            satirlar.append(f"Kullanıcı: {str(tur['soru'])[:300]}")
        if tur.get("cevap"):
            satirlar.append(f"Asistan: {str(tur['cevap'])[:300]}")
    return "\n".join(satirlar)


def cevapla(
    soru: str,
    retriever: Retriever | None = None,
    rol: str = "uretim",
    k: int = 2,  # hız/kalite dengesi: hit@2 %96.7, hit@3 %100 (bench k=3 ile ölçer)
    endpoint: str | None = None,
    gecmis: list[dict] | None = None,
) -> RagCevabi:
    endpoint = endpoint or foundry.endpoint_bul()
    retriever = retriever or Retriever()
    model = foundry.model_coz(rol, endpoint)

    # Sohbet-meta soru: dokümanlara hiç gitme, geçmişten cevapla.
    kucuk = soru.casefold()
    if any(re.search(d, kucuk) for d in SOHBET_META_DESENLERI):
        icerik = (
            f"Sohbet geçmişi:\n{_gecmis_metni(gecmis) or '(henüz mesaj yok)'}"
            f"\n\nSoru: {soru}"
        )
        cevap = foundry.chat_tamamla(
            model,
            [{"role": "system", "content": SOHBET_SISTEM_PROMPTU},
             {"role": "user", "content": icerik}],
            endpoint,
            max_tokens=160,
        )
        return RagCevabi(cevap=cevap, model=model, parcalar=[], reddedildi=False)

    parcalar = retriever.ara(soru, k=k, endpoint=endpoint)

    from core.retriever import RED_MESAJI
    if retriever.reddedilmeli(parcalar):
        # Sohbet geçmişi varsa soru sohbetin kendisi hakkında olabilir
        # ("az önce ne sordum"); dokümansız, geçmişe dayalı cevap dene.
        if gecmis:
            icerik = f"Sohbet geçmişi:\n{_gecmis_metni(gecmis)}\n\nSoru: {soru}"
            cevap = foundry.chat_tamamla(
                model,
                [{"role": "system", "content": SOHBET_SISTEM_PROMPTU},
                 {"role": "user", "content": icerik}],
                endpoint,
                max_tokens=160,
            )
            return RagCevabi(cevap=cevap, model=model, parcalar=[], reddedildi=False)
        # Domain-dışı ve geçmiş yok: modele sorup uydurtma.
        return RagCevabi(
            cevap=RED_MESAJI, model="(model çağrılmadı)",
            parcalar=parcalar, reddedildi=True,
        )

    gecmis_blok = (
        f"Önceki sohbet:\n{_gecmis_metni(gecmis)}\n\n---\n\n" if gecmis else ""
    )
    kullanici_mesaji = (
        f"{gecmis_blok}Bağlam:\n\n{baglam_kur(parcalar, soru)}\n\n---\n\nSoru: {soru}"
    )
    cevap = foundry.chat_tamamla(
        model,
        [
            {"role": "system", "content": RAG_SISTEM_PROMPTU},
            {"role": "user", "content": kullanici_mesaji},
        ],
        endpoint,
        max_tokens=256,
    )
    return RagCevabi(cevap=cevap, model=model, parcalar=parcalar)
