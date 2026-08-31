"""RAG zinciri: retrieve -> Türkçe prompt -> generate."""

from __future__ import annotations

from dataclasses import dataclass, field

from core import foundry
from core.retriever import Parca, Retriever

RAG_SISTEM_PROMPTU = (
    "Sen Türkçe konuşan bir doküman asistanısın. SADECE sana verilen bağlam "
    "parçalarındaki bilgiyi kullanarak cevap ver. Bağlamda olmayan komut, menü "
    "yolu ya da adım UYDURMA; bağlam soruyu tam karşılamıyorsa hangi kısmın "
    "dokümanlarda olmadığını açıkça söyle. KISA yaz: en fazla 4-5 cümle ya da "
    "3-4 madde. Aynı bilgiyi veya maddeyi asla tekrarlama."
)


@dataclass
class RagCevabi:
    cevap: str
    model: str
    parcalar: list[Parca] = field(default_factory=list)
    reddedildi: bool = False  # domain dışı: modele gidilmedi


def baglam_kur(parcalar: list[Parca]) -> str:
    bloklar = [
        f"[Kaynak: {p.kaynak} / parça {p.sira} / benzerlik {p.skor:.2f}]\n{p.metin}"
        for p in parcalar
    ]
    return "\n\n---\n\n".join(bloklar)


def cevapla(
    soru: str,
    retriever: Retriever | None = None,
    rol: str = "uretim",
    k: int = 3,
    endpoint: str | None = None,
) -> RagCevabi:
    endpoint = endpoint or foundry.endpoint_bul()
    retriever = retriever or Retriever()
    parcalar = retriever.ara(soru, k=k, endpoint=endpoint)

    # Domain-dışı reddi: yeterli sinyal yoksa modele sorup uydurtma.
    from core.retriever import RED_MESAJI
    if retriever.reddedilmeli(parcalar):
        return RagCevabi(
            cevap=RED_MESAJI, model="(model çağrılmadı)",
            parcalar=parcalar, reddedildi=True,
        )

    kullanici_mesaji = (
        f"Bağlam:\n\n{baglam_kur(parcalar)}\n\n---\n\nSoru: {soru}"
    )
    model = foundry.model_coz(rol, endpoint)
    cevap = foundry.chat_tamamla(
        model,
        [
            {"role": "system", "content": RAG_SISTEM_PROMPTU},
            {"role": "user", "content": kullanici_mesaji},
        ],
        endpoint,
    )
    return RagCevabi(cevap=cevap, model=model, parcalar=parcalar)
