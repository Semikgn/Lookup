"""RAG Router TR v2 web uygulaması — tek model, Türkçe hibrit RAG.

Çalıştırma:
    uvicorn app.main:app --port 8000

Sekmeler: Sohbet (RAG + kaynak/skor + domain-dışı reddi) ve Ölçümler
(düz→hibrit before/after + model seçim yarışı). Tamamen çevrimdışı.
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
from core import foundry, rag
from core.retriever import Retriever

app = FastAPI(title="RAG Router TR")

LEADERBOARD_YOLU = Path(__file__).resolve().parent.parent / "bench" / "leaderboard.json"

_retriever: Retriever | None = None


def retriever_al() -> Retriever | None:
    global _retriever
    if _retriever is None:
        try:
            _retriever = Retriever(mod="hibrit")
        except (FileNotFoundError, ValueError):
            return None
    return _retriever


class Soru(BaseModel):
    soru: str


@app.post("/api/sor")
def sor(istek: Soru) -> dict:
    endpoint = foundry.endpoint_bul()
    retriever = retriever_al()
    if retriever is None:
        return {"cevap": "İndeks bulunamadı. Önce `python -m ingest.ingest` çalıştırın.",
                "model": "-", "parcalar": [], "reddedildi": False, "sure": 0}

    baslangic = time.perf_counter()
    sonuc = rag.cevapla(istek.soru, retriever=retriever, endpoint=endpoint)
    sure = time.perf_counter() - baslangic
    return {
        "cevap": sonuc.cevap,
        "model": sonuc.model,
        "reddedildi": sonuc.reddedildi,
        "parcalar": [
            {"kaynak": p.kaynak, "sira": p.sira, "skor": round(p.skor, 2),
             "kosinus": round(p.kosinus, 2), "kapsama": round(p.kapsama, 2)}
            for p in sonuc.parcalar
        ],
        "sure": round(sure, 1),
    }


@app.get("/api/olcumler")
def olcumler() -> dict:
    if not LEADERBOARD_YOLU.exists():
        return {}
    return json.loads(LEADERBOARD_YOLU.read_text(encoding="utf-8"))


SAYFA = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAG Router TR</title>
<style>
  :root { --mavi: #0e7d8a; --gri: #f3f4f6; --koyu: #111827; }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "Segoe UI", system-ui, sans-serif; background: var(--gri);
         color: var(--koyu); max-width: 880px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.3rem; margin: 8px 0 4px; }
  h1 small { color: #6b7280; font-weight: normal; font-size: .8rem; }
  .altbaslik { color: #6b7280; font-size: .85rem; margin-bottom: 16px; }
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
  .red { background: #fef3c7; }
  .kaynak-kutu { font-size: .78rem; color: #6b7280; background: #e8f4f5; border-radius: 8px;
                 padding: 6px 10px; align-self: flex-start; max-width: 85%; }
  form { display: flex; gap: 8px; margin-top: 14px; }
  input[type=text] { flex: 1; padding: 10px 14px; border: 1px solid #d1d5db;
                     border-radius: 8px; font-size: 1rem; }
  form button { padding: 10px 22px; border: none; border-radius: 8px;
                background: var(--mavi); color: white; font-size: 1rem; cursor: pointer; }
  form button:disabled { opacity: .5; }
  table { width: 100%; border-collapse: collapse; background: white; margin-bottom: 16px;
          border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  th, td { padding: 10px 12px; text-align: center; font-size: .9rem; }
  th { background: var(--mavi); color: white; font-weight: 600; }
  tr:nth-child(even) { background: #f9fafb; }
  td:first-child, th:first-child { text-align: left; }
  h2 { font-size: 1rem; margin: 18px 0 8px; }
  .not { font-size: .8rem; color: #6b7280; margin-top: 4px; }
  .kilit { background: #dcfce7; border-radius: 8px; padding: 10px 14px; font-size: .9rem;
           margin-bottom: 14px; }
</style>
</head>
<body>
<h1>🧭 RAG Router TR <small>— v2</small></h1>
<div class="altbaslik">Tek model + Türkçe hibrit retrieval, tamamen çevrimdışı (Foundry Local)</div>
<div class="sekmeler">
  <button id="sek-sohbet" class="aktif" onclick="sekme('sohbet')">Sohbet</button>
  <button id="sek-olcum" onclick="sekme('olcum')">Ölçümler</button>
</div>

<div id="panel-sohbet" class="panel aktif">
  <div id="mesajlar"></div>
  <form onsubmit="return gonder(event)">
    <input type="text" id="soru" placeholder="Dokümanlara sor: DNS, DHCP, SSH, RAID, systemd..." autocomplete="off">
    <button id="btn" type="submit">Sor</button>
  </form>
</div>

<div id="panel-olcum" class="panel">
  <div id="olcum-icerik">Yükleniyor...</div>
</div>

<script>
function sekme(ad) {
  for (const p of document.querySelectorAll('.panel')) p.classList.remove('aktif');
  for (const b of document.querySelectorAll('.sekmeler button')) b.classList.remove('aktif');
  document.getElementById('panel-' + ad).classList.add('aktif');
  document.getElementById('sek-' + ad).classList.add('aktif');
  if (ad === 'olcum') olcumYukle();
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
  const bekleme = ekle('mesaj asistan', 'Aranıyor ve cevap üretiliyor...');
  try {
    const y = await fetch('/api/sor', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({soru})
    });
    const v = await y.json();
    bekleme.textContent = v.cevap || '(boş cevap)';
    if (v.reddedildi) bekleme.classList.add('red');
    let bilgi = v.reddedildi
      ? `⛔ Domain dışı: model hiç çağrılmadı (${v.sure} sn)`
      : `📄 ${v.model} · ${v.sure} sn · Kaynaklar: ` +
        v.parcalar.map(p => `${p.kaynak}#${p.sira} (${p.skor})`).join(', ');
    ekle('kaynak-kutu', bilgi);
  } catch (hata) {
    bekleme.textContent = 'Hata: ' + hata;
  }
  document.getElementById('btn').disabled = false;
  return false;
}

async function olcumYukle() {
  const hedef = document.getElementById('olcum-icerik');
  const y = await fetch('/api/olcumler');
  const v = await y.json();
  if (!v.retrieval) { hedef.textContent = 'Henüz ölçüm yok: python -m bench.run_bench'; return; }
  let html = '';
  if (v.kilitli_model) {
    html += `<div class="kilit">🔒 Kilitli model: <b>${v.kilitli_model}</b> — ${v.kilit_gerekcesi || ''}</div>`;
  }
  html += '<h2>Retrieval: düz kosinüs → hibrit (before/after)</h2>';
  html += '<table><tr><th>Mod</th><th>hit@1</th><th>hit@3</th><th>Domain-dışı red</th></tr>';
  for (const [mod, r] of Object.entries(v.retrieval)) {
    html += `<tr><td>${mod}</td><td>%${Math.round(r.hit1 * 100)}</td>` +
            `<td>%${Math.round(r.hit3 * 100)} (${r.isabet})</td><td>${r.red_dogru}</td></tr>`;
  }
  html += '</table>';
  if (v.modeller && Object.keys(v.modeller).length) {
    html += '<h2>Model seçim yarışı (uçtan uca, hibrit RAG)</h2>';
    html += '<table><tr><th>Model</th><th>RAG doğruluk</th><th>Medyan süre</th><th>Red</th></tr>';
    for (const [ad, m] of Object.entries(v.modeller)) {
      html += `<tr><td>${ad}${ad === v.kilitli_model ? ' 🔒' : ''}</td>` +
              `<td>%${Math.round(m.rag_dogruluk * 100)}</td><td>${m.medyan_sure} sn</td><td>${m.red_dogru}</td></tr>`;
    }
    html += '</table>';
  }
  if (v.elenenler) {
    html += '<h2>Elenenler</h2><table><tr><th>Model</th><th>Durum</th><th>Gerekçe</th></tr>';
    for (const [ad, e] of Object.entries(v.elenenler)) {
      html += `<tr><td>${ad}</td><td>${e.durum}</td><td style="text-align:left">${e.gerekce}</td></tr>`;
    }
    html += '</table>';
  }
  html += `<p class="not">Test seti: 30 RAG + 5 domain-dışı Türkçe soru · Ölçüm: ${v.olusturulma || '?'}</p>`;
  hedef.innerHTML = html;
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def anasayfa() -> str:
    return SAYFA
