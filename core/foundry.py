"""Foundry Local istemcisi.

Endpoint'i sabit port varsaymadan `foundry server status -o json` çıktısından
dinamik olarak bulur, OpenAI-uyumlu istemciyi bu adrese yönlendirir ve model
alias'larını makinede gerçekten yüklü olan modellere çözer (fallback dahil).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request

from openai import OpenAI

# Rol -> tercih sırası. Baştaki model yoksa listede geriye düşülür.
MODEL_TERCIHLERI: dict[str, list[str]] = {
    "hizli": ["qwen2.5-0.5b"],
    "genel": ["qwen3-4b", "qwen3-1.7b", "qwen2.5-1.5b", "qwen2.5-0.5b"],
    "kod": ["qwen2.5-coder-1.5b", "qwen2.5-coder-0.5b", "qwen2.5-0.5b"],
    "embedding": ["qwen3-embedding-0.6b"],
}


class FoundryHatasi(RuntimeError):
    """Foundry Local servisine erişilemediğinde fırlatılır."""


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
    durum = subprocess.run(
        [cli, "server", "status", "-o", "json"],
        capture_output=True, text=True, timeout=60,
    )
    bilgi = _json_ayikla(durum.stdout)
    if not (bilgi and bilgi.get("running") and bilgi.get("webUrls")):
        subprocess.run([cli, "server", "start"], capture_output=True, text=True, timeout=300)
        durum = subprocess.run(
            [cli, "server", "status", "-o", "json"],
            capture_output=True, text=True, timeout=60,
        )
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


def istemci(endpoint: str | None = None) -> OpenAI:
    """Foundry Local'e bağlı OpenAI istemcisi (anahtar gerekmez)."""
    endpoint = endpoint or endpoint_bul()
    return OpenAI(base_url=f"{endpoint}/v1", api_key="lokal")


def sohbet(
    soru: str,
    rol: str = "genel",
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
    yanit = istemci(endpoint).chat.completions.create(
        model=model, messages=mesajlar, **secenekler
    )
    return yanit.choices[0].message.content or ""
