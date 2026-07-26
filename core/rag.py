"""RAG zinciri: retrieve -> Türkçe prompt -> generate."""

from __future__ import annotations

from dataclasses import dataclass, field

from core import foundry
from core.retriever import Parca, Retriever

RAG_SISTEM_PROMPTU = (
    "Sen Türkçe konuşan bir doküman asistanısın. SADECE sana verilen bağlam "
    "parçalarındaki bilgiyi kullanarak cevap ver. Cevap bağlamda yoksa bunu "
    "açıkça söyle; uydurma. Kısa ve net Türkçe cevap ver."
)


@dataclass
class RagCevabi:
    cevap: str
    model: str
    parcalar: list[Parca] = field(default_factory=list)


def baglam_kur(parcalar: list[Parca]) -> str:
    bloklar = [
        f"[Kaynak: {p.kaynak} / parça {p.sira} / benzerlik {p.skor:.2f}]\n{p.metin}"
        for p in parcalar
    ]
    return "\n\n---\n\n".join(bloklar)


def cevapla(
    soru: str,
    retriever: Retriever | None = None,
    rol: str = "genel",
    k: int = 3,
    endpoint: str | None = None,
) -> RagCevabi:
    endpoint = endpoint or foundry.endpoint_bul()
    retriever = retriever or Retriever()
    parcalar = retriever.ara(soru, k=k, endpoint=endpoint)

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
