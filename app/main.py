"""RAG Router TR web uygulaması.

Çalıştırma:
    uvicorn app.main:app --port 8000

Tek sayfalık arayüz: Sohbet + Leaderboard sekmeleri. Her cevabın yanında
"bu soru şu modele gitti çünkü..." açıklaması gösterilir. Tüm inference
Foundry Local üzerinde, tamamen çevrimdışıdır.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import foundry, rag, router
from core.retriever import Retriever

app = FastAPI(title="RAG Router TR")

_retriever: Retriever | None = None


def retriever_al() -> Retriever | None:
    global _retriever
    if _retriever is None:
        try:
            _retriever = Retriever()
        except (FileNotFoundError, ValueError):
            return None
    return _retriever


class Soru(BaseModel):
    soru: str


@app.post("/api/sor")
def sor(istek: Soru) -> dict:
    endpoint = foundry.endpoint_bul()
    retriever = retriever_al()
    karar = router.yonlendir(istek.soru, retriever=retriever, endpoint=endpoint)

    baslangic = time.perf_counter()
    parcalar = []
    if karar.kategori == "rag" and retriever is not None:
        sonuc = rag.cevapla(
            istek.soru, retriever=retriever, rol=karar.model_alias, endpoint=endpoint
        )
        cevap = sonuc.cevap
        parcalar = [
            {"kaynak": p.kaynak, "sira": p.sira, "skor": round(p.skor, 2)}
            for p in sonuc.parcalar
        ]
    else:
        sistem = (
            "Sen Türkçe konuşan yardımcı bir asistansın. Kısa ve net cevap ver."
        )
        cevap = foundry.sohbet(
            istek.soru, rol=karar.model_alias, sistem=sistem, endpoint=endpoint
        )
    sure = time.perf_counter() - baslangic

    return {
        "cevap": cevap,
        "model": karar.model_alias,
        "kategori": karar.kategori,
        "gerekce": karar.gerekce,
        "parcalar": parcalar,
        "sure": round(sure, 1),
    }


@app.get("/api/leaderboard")
def leaderboard() -> dict:
    yol = router.LEADERBOARD_YOLU
    if not yol.exists():
        return {"modeller": {}}
    return json.loads(yol.read_text(encoding="utf-8"))


SAYFA = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG Router TR</title>
<style>
  :root { --mavi: #2563eb; --gri: #f3f4f6; --koyu: #111827; }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "Segoe UI", system-ui, sans-serif; background: var(--gri);
         color: var(--koyu); max-width: 860px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.3rem; margin: 8px 0 16px; }
  h1 small { color: #6b7280; font-weight: normal; font-size: .8rem; }
  .sekmeler { display: flex; gap: 8px; margin-bottom: 16px; }
  .sekmeler button { padding: 8px 20px; border: none; border-radius: 8px;
                     background: #e5e7eb; cursor: pointer; font-size: 1rem; }
  .sekmeler button.aktif { background: var(--mavi); color: white; }
  .panel { display: none; } .panel.aktif { display: block; }
  #mesajlar { display: flex; flex-direction: column; gap: 12px; min-height: 300px;
              max-height: 60vh; overflow-y: auto; padding: 4px; }
  .mesaj { padding: 10px 14px; border-radius: 12px; max-width: 85%;
           white-space: pre-wrap; line-height: 1.45; }
  .kullanici { background: var(--mavi); color: white; align-self: flex-end; }
  .asistan { background: white; align-self: flex-start; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  .rota { font-size: .78rem; color: #6b7280; background: #eef2ff; border-radius: 8px;
          padding: 6px 10px; align-self: flex-start; max-width: 85%; }
  .kaynaklar { font-size: .75rem; color: #6b7280; margin-top: 6px; }
  form { display: flex; gap: 8px; margin-top: 14px; }
  input[type=text] { flex: 1; padding: 10px 14px; border: 1px solid #d1d5db;
                     border-radius: 8px; font-size: 1rem; }
  form button { padding: 10px 22px; border: none; border-radius: 8px;
                background: var(--mavi); color: white; font-size: 1rem; cursor: pointer; }
  form button:disabled { opacity: .5; }
  table { width: 100%; border-collapse: collapse; background: white;
          border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  th, td { padding: 10px 12px; text-align: center; }
  th { background: var(--mavi); color: white; font-weight: 600; }
  tr:nth-child(even) { background: #f9fafb; }
  td:first-child, th:first-child { text-align: left; }
  .bekliyor { color: #6b7280; font-style: italic; }
</style>
</head>
<body>
<h1>🧭 RAG Router TR <small>— tamamen çevrimdışı, Foundry Local</small></h1>
<div class="sekmeler">
  <button id="sek-sohbet" class="aktif" onclick="sekme('sohbet')">Sohbet</button>
  <button id="sek-lider" onclick="sekme('lider')">Leaderboard</button>
</div>

<div id="panel-sohbet" class="panel aktif">
  <div id="mesajlar"></div>
  <form onsubmit="return gonder(event)">
    <input type="text" id="soru" placeholder="Sorunuzu yazın... (kod, doküman ya da genel)" autocomplete="off">
    <button id="btn" type="submit">Sor</button>
  </form>
</div>

<div id="panel-lider" class="panel">
  <div id="lider-icerik" class="bekliyor">Yükleniyor...</div>
</div>

<script>
function sekme(ad) {
  for (const p of document.querySelectorAll('.panel')) p.classList.remove('aktif');
  for (const b of document.querySelectorAll('.sekmeler button')) b.classList.remove('aktif');
  document.getElementById('panel-' + ad).classList.add('aktif');
  document.getElementById('sek-' + ad).classList.add('aktif');
  if (ad === 'lider') liderYukle();
}

function ekle(sinif, metin) {
  const kutu = document.createElement('div');
  kutu.className = sinif;
  kutu.textContent = metin;
  document.getElementById('mesajlar').appendChild(kutu);
  kutu.scrollIntoView({behavior: 'smooth'});
  return kutu;
}

async function gonder(e) {
  e.preventDefault();
  const girdi = document.getElementById('soru');
  const soru = girdi.value.trim();
  if (!soru) return false;
  girdi.value = '';
  document.getElementById('btn').disabled = true;
  ekle('mesaj kullanici', soru);
  const bekleme = ekle('mesaj asistan', 'Düşünüyorum... (yerel modelde bu biraz sürebilir)');
  try {
    const y = await fetch('/api/sor', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({soru})
    });
    const v = await y.json();
    bekleme.textContent = v.cevap || '(boş cevap)';
    let rota = `🧭 ${v.model} · ${v.sure} sn — ${v.gerekce}`;
    const r = ekle('rota', rota);
    if (v.parcalar && v.parcalar.length) {
      const k = document.createElement('div');
      k.className = 'kaynaklar';
      k.textContent = 'Kaynaklar: ' + v.parcalar.map(p => `${p.kaynak}#${p.sira} (${p.skor})`).join(', ');
      r.appendChild(k);
    }
  } catch (hata) {
    bekleme.textContent = 'Hata: ' + hata;
  }
  document.getElementById('btn').disabled = false;
  return false;
}

async function liderYukle() {
  const hedef = document.getElementById('lider-icerik');
  const y = await fetch('/api/leaderboard');
  const v = await y.json();
  const modeller = Object.entries(v.modeller || {});
  if (!modeller.length) {
    hedef.textContent = 'Henüz leaderboard yok. Önce: python -m bench.run_bench';
    return;
  }
  modeller.sort((a, b) => b[1].genel_dogruluk - a[1].genel_dogruluk);
  let html = '<table><tr><th>Model</th><th>RAG</th><th>Kod</th><th>Genel</th><th>Toplam</th></tr>';
  for (const [ad, veri] of modeller) {
    const k = veri.kategoriler || {};
    const h = kat => kat ? `%${Math.round(kat.dogruluk * 100)}<br><small>${kat.ortalama_sure ?? '?'} sn</small>` : '-';
    html += `<tr><td>${ad}</td><td>${h(k.rag)}</td><td>${h(k.kod)}</td>` +
            `<td>${h(k.genel)}</td><td><b>%${Math.round(veri.genel_dogruluk * 100)}</b></td></tr>`;
  }
  html += '</table>';
  if (v.olusturulma) html += `<p class="kaynaklar">Ölçüm: ${v.olusturulma}</p>`;
  hedef.innerHTML = html;
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def anasayfa() -> str:
    return SAYFA
