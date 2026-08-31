"""Foundry Local istemcisi.

Endpoint'i sabit port varsaymadan `foundry server status -o json` çıktısından
dinamik olarak bulur, OpenAI-uyumlu istemciyi bu adrese yönlendirir ve model
alias'larını makinede gerçekten yüklü olan modellere çözer (fallback dahil).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request

from openai import OpenAI

# Rol -> tercih sırası. Baştaki model yoksa listede geriye düşülür.
# v2: runtime'da TEK model. Seçim bench/leaderboard.json'daki ölçümle
# kilitlendi (RAG %76.7 @ 42 sn); qwen3-1.7b yalnızca kilitli model diskte
# yoksa devreye giren yedektir. phi-4-mini ve qwen3-4b donanım yüzünden,
# qwen2.5-0.5b kalite yüzünden elendi — gerekçeler leaderboard.json'da.
MODEL_TERCIHLERI: dict[str, list[str]] = {
    "uretim": ["qwen2.5-coder-1.5b", "qwen3-1.7b"],
    "embedding": ["qwen3-embedding-0.6b"],
}


class FoundryHatasi(RuntimeError):
    """Foundry Local servisine erişilemediğinde fırlatılır."""


def _calistir(komut: list[str], timeout: int) -> subprocess.CompletedProcess:
    """foundry CLI'ını Windows kod sayfasına takılmadan (UTF-8) çalıştırır."""
    return subprocess.run(
        komut, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def _foundry_cli() -> str:
    yol = shutil.which("foundry")
    if yol is None:
        raise FoundryHatasi(
            "`foundry` komutu bulunamadı. Foundry Local kurulu mu? "
            "Kurulum: winget install Microsoft.FoundryLocal"
        )
    return yol


def endpoint_bul() -> str:
    """Çalışan Foundry Local servisinin taban URL'ini döndürür.

    Öncelik: FOUNDRY_ENDPOINT ortam değişkeni -> `foundry server status`.
    Servis kapalıysa başlatmayı dener.
    """
    if os.environ.get("FOUNDRY_ENDPOINT"):
        return os.environ["FOUNDRY_ENDPOINT"].rstrip("/")

    cli = _foundry_cli()
    durum = _calistir([cli, "server", "status", "-o", "json"], timeout=60)
    bilgi = _json_ayikla(durum.stdout)
    if not (bilgi and bilgi.get("running") and bilgi.get("webUrls")):
        _calistir([cli, "server", "start"], timeout=300)
        durum = _calistir([cli, "server", "status", "-o", "json"], timeout=60)
        bilgi = _json_ayikla(durum.stdout)
    if not (bilgi and bilgi.get("webUrls")):
        raise FoundryHatasi(
            "Foundry Local servisi başlatılamadı. `foundry server start` çıktısını kontrol et."
        )
    return bilgi["webUrls"][0].rstrip("/")


def _json_ayikla(metin: str) -> dict | None:
    # CLI bazen JSON'dan önce durum satırları basıyor; ilk '{' sonrasını al.
    baslangic = metin.find("{")
    if baslangic == -1:
        return None
    try:
        return json.loads(metin[baslangic:])
    except json.JSONDecodeError:
        return None


def yuklu_modeller(endpoint: str | None = None) -> dict[str, str]:
    """Cache'teki modelleri {alias: gerçek_model_id} olarak döndürür.

    /v1/models çıktısında `parent` alanı katalog alias'ıdır (örn. qwen2.5-0.5b),
    `id` ise servise verilecek gerçek addır (örn. qwen2.5-0.5b-instruct-generic-cpu).
    """
    endpoint = endpoint or endpoint_bul()
    with urllib.request.urlopen(f"{endpoint}/v1/models", timeout=30) as yanit:
        veri = json.load(yanit)
    return {m.get("parent", m["id"]): m["id"] for m in veri.get("data", [])}


def model_coz(rol_veya_alias: str, endpoint: str | None = None) -> str:
    """Rol adını ('genel', 'kod', ...) ya da doğrudan alias'ı gerçek model id'sine çözer.

    Tercih listesindeki ilk yüklü model seçilir; hiçbiri yoksa hata verir.
    """
    mevcut = yuklu_modeller(endpoint)
    adaylar = MODEL_TERCIHLERI.get(rol_veya_alias, [rol_veya_alias])
    for alias in adaylar:
        if alias in mevcut:
            return mevcut[alias]
        if alias in mevcut.values():  # zaten gerçek id verilmiş
            return alias
    raise FoundryHatasi(
        f"'{rol_veya_alias}' için yüklü model yok. Denenenler: {adaylar}. "
        f"İndirmek için: foundry model download <alias>"
    )


def model_yukle(alias: str) -> None:
    """Modeli belleğe yükler (embedding modelleri otomatik yüklenmediği için gerekli)."""
    sonuc = _calistir([_foundry_cli(), "model", "load", alias], timeout=600)
    if sonuc.returncode != 0:
        raise FoundryHatasi(f"'{alias}' yüklenemedi: {sonuc.stderr or sonuc.stdout}")


def model_bosalt(alias: str) -> None:
    """Modeli bellekten çıkarır (sınırlı RAM'de model değiştirirken gerekli)."""
    _calistir([_foundry_cli(), "model", "unload", alias], timeout=120)


def yabanci_karakter_temizle(metin: str) -> str:
    """Küçük qwen modellerinin Türkçe cevaba sızdırdığı CJK karakterleri ayıklar.

    (Saha vakası: 'internet 提供商 ile iletişime geçebilirsiniz'.)
    """
    # CJK noktalama+kana, CJK ideogramları, Hangul, tam genişlik formları.
    temiz = re.sub(
        r"[　-ヿ㐀-鿿가-힯＀-￯]+", "", metin
    )
    return re.sub(r"  +", " ", temiz)


def tekrar_temizle(metin: str) -> str:
    """Küçük modellerin tekrarladığı cümleleri/maddeleri ayıklar.

    Birebir kopyaların yanında paraphrase'li döngüyü de yakalamak için
    cümleler kelime kümesi benzerliğiyle (Jaccard >= 0.7) karşılaştırılır.
    """
    parcalar = re.split(r"(?<=[.!?:])\s+|\n", metin)
    gorulen: list[set[str]] = []
    kisa_gorulen: set[str] = set()
    tutulan: list[str] = []
    for p in parcalar:
        kelimeler = set(re.findall(r"\w+", p.casefold()))
        if len(kelimeler) >= 5:
            tekrar = any(
                len(kelimeler & g) / len(kelimeler | g) >= 0.7 for g in gorulen
            )
            if tekrar:
                continue
            gorulen.append(kelimeler)
        elif kelimeler:
            # Kısa cümleler için birebir eşleşme: "TCP/IP açıklayınız." × 50
            # vakası (3 kelime, Jaccard süzgecinin altında kalıyordu).
            anahtar = " ".join(sorted(kelimeler))
            if anahtar in kisa_gorulen:
                continue
            kisa_gorulen.add(anahtar)
        tutulan.append(p)
    return "\n".join(t for t in tutulan if t.strip()) if "\n" in metin else " ".join(tutulan)


def dusunce_temizle(metin: str) -> str:
    """qwen3 gibi modellerin <think>...</think> bloklarını cevaptan ayıklar."""
    temiz = re.sub(r"<think>.*?</think>", "", metin, flags=re.DOTALL)
    # Kapanmamış think bloğu (max_tokens'a takılmış) varsa tamamen at.
    temiz = re.sub(r"<think>.*", "", temiz, flags=re.DOTALL)
    return temiz.strip()


def goml(metinler: list[str], endpoint: str | None = None) -> list[list[float]]:
    """Metin listesini embedding vektörlerine dönüştürür.

    Sunucu toplu (liste) girişi kabul etmezse tek tek gönderime düşer.
    """
    endpoint = endpoint or endpoint_bul()
    model = model_coz("embedding", endpoint)
    oai = istemci(endpoint)
    try:
        yanit = oai.embeddings.create(model=model, input=metinler)
        return [v.embedding for v in yanit.data]
    except Exception as hata:
        if "not loaded" in str(hata):
            model_yukle("qwen3-embedding-0.6b")
            yanit = oai.embeddings.create(model=model, input=metinler)
            return [v.embedding for v in yanit.data]
        # Toplu giriş desteklenmiyorsa tek tek dene.
        return [
            oai.embeddings.create(model=model, input=m).data[0].embedding
            for m in metinler
        ]


def istemci(endpoint: str | None = None) -> OpenAI:
    """Foundry Local'e bağlı OpenAI istemcisi (anahtar gerekmez)."""
    endpoint = endpoint or endpoint_bul()
    return OpenAI(base_url=f"{endpoint}/v1", api_key="lokal")


def alias_bul(model_id: str, endpoint: str | None = None) -> str:
    """Gerçek model id'sinden katalog alias'ını bulur (yoksa id'yi döndürür)."""
    for alias, mid in yuklu_modeller(endpoint).items():
        if mid == model_id:
            return alias
    return model_id


def chat_tamamla(
    model_id: str,
    mesajlar: list[dict],
    endpoint: str | None = None,
    **secenekler,
) -> str:
    """Chat isteği atar; model bellekte değilse yükleyip bir kez daha dener.

    Bu Foundry sürümünde modeller API isteğiyle otomatik YÜKLENMİYOR;
    önce `foundry model load` gerekiyor.
    """
    endpoint = endpoint or endpoint_bul()
    # 320 token: normal cevaplar ~80-150 token'da bitiyor; tavan yalnızca
    # patolojik döngülerde devreye girip beklemeyi sınırlıyor.
    secenekler.setdefault("max_tokens", 320)
    secenekler.setdefault("temperature", 0.2)
    # NOT: frequency_penalty denendi ve GERİ ALINDI — bu sunucu/model ikilisinde
    # cevabı kısaltmak yerine paraphrase'li döngüye itti. Tekrarlar çıktı
    # katmanında tekrar_temizle ile ayıklanıyor.

    # qwen3 chat modelleri varsayılan olarak <think> bloğuyla düşünür; CPU'da bu,
    # token bütçesini ve süreyi yutuyor. Soft-switch ile kapat.
    if "qwen3" in model_id and "embedding" not in model_id:
        mesajlar = list(mesajlar)
        if mesajlar and mesajlar[0].get("role") == "system":
            mesajlar[0] = {
                "role": "system",
                "content": mesajlar[0]["content"] + " /no_think",
            }
        else:
            mesajlar.insert(0, {"role": "system", "content": "/no_think"})

    oai = istemci(endpoint)
    try:
        yanit = oai.chat.completions.create(
            model=model_id, messages=mesajlar, **secenekler
        )
    except Exception as hata:
        if "not loaded" not in str(hata):
            raise
        model_yukle(alias_bul(model_id, endpoint))
        yanit = oai.chat.completions.create(
            model=model_id, messages=mesajlar, **secenekler
        )
    ham = yanit.choices[0].message.content or ""
    return tekrar_temizle(yabanci_karakter_temizle(dusunce_temizle(ham)))


def sohbet(
    soru: str,
    rol: str = "uretim",
    sistem: str | None = None,
    endpoint: str | None = None,
    **secenekler,
) -> str:
    """Tek soruluk sohbet: rolü modele çözer, Türkçe cevabı döndürür."""
    endpoint = endpoint or endpoint_bul()
    model = model_coz(rol, endpoint)
    mesajlar = []
    if sistem:
        mesajlar.append({"role": "system", "content": sistem})
    mesajlar.append({"role": "user", "content": soru})
    return chat_tamamla(model, mesajlar, endpoint, **secenekler)
