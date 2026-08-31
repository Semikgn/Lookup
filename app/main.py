"""Lookup web uygulaması. Türkçe, tamamen çevrimdışı doküman asistanı.

Çalıştırma:
    uvicorn app.main:app --port 8000

Tek sayfa: karşılama ekranı ilk soruyla sohbete dönüşür. Ölçümler görünümü
hibrit retrieval before/after tablolarını gösterir. Sayfa hiçbir dış kaynağa
(font, CDN) bağlanmaz; WiFi kapalıyken de aynı görünür.
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

app = FastAPI(title="Lookup")

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
    gecmis: list[dict] = []  # [{soru, cevap}] — son turlar, tarayıcıdan gelir


@app.post("/api/sor")
def sor(istek: Soru) -> dict:
    endpoint = foundry.endpoint_bul()
    retriever = retriever_al()
    if retriever is None:
        return {"cevap": "İndeks bulunamadı. Önce `python -m ingest.ingest` çalıştırın.",
                "model": "-", "parcalar": [], "reddedildi": False, "sure": 0}

    baslangic = time.perf_counter()
    sonuc = rag.cevapla(
        istek.soru, retriever=retriever, endpoint=endpoint, gecmis=istek.gecmis
    )
    sure = time.perf_counter() - baslangic
    return {
        "cevap": sonuc.cevap,
        "model": sonuc.model,
        "reddedildi": sonuc.reddedildi,
        "parcalar": [
            {"kaynak": p.kaynak, "sira": p.sira, "skor": round(p.skor, 2)}
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
<title>Lookup</title>
<style>
  :root {
    --zemin: #0a0a0a;
    --yuzey: #151312;
    --cizgi: #2a2624;
    --metin: #f2efe9;
    --soluk: #9a948a;
    --bordo: #a02c3c;
    --bordo-koyu: #7b1e2b;
    --bordo-acik: #c44556;
  }
  * { box-sizing: border-box; margin: 0; }
  html, body { height: 100%; }
  body {
    background: var(--zemin);
    color: var(--metin);
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    line-height: 1.6;
    display: flex; flex-direction: column;
  }
  .serif { font-family: Georgia, "Times New Roman", serif; }
  .mono { font-family: Consolas, "Courier New", monospace; }
  a { color: var(--metin); text-decoration: none; }
  button { font-family: inherit; }
  :focus-visible { outline: 2px solid var(--bordo-acik); outline-offset: 2px; }

  /* Üst bar */
  nav {
    display: flex; align-items: center; justify-content: space-between;
    padding: 18px 28px; border-bottom: 1px solid var(--cizgi);
  }
  .marka { font-family: Georgia, serif; font-size: 1.35rem; letter-spacing: -0.01em; cursor: pointer; }
  .marka b { color: var(--bordo-acik); }
  .nav-sag { display: flex; gap: 22px; align-items: center; font-size: 0.9rem; }
  .nav-sag a, .nav-sag button {
    background: none; border: none; color: var(--soluk); cursor: pointer;
    font-size: 0.9rem; padding: 4px 2px;
  }
  .nav-sag a:hover, .nav-sag button:hover { color: var(--metin); }

  main { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 0 20px; }

  /* Karşılama */
  #hero { text-align: center; max-width: 760px; margin-top: 11vh; }
  #hero h1 {
    font-family: Georgia, serif; font-weight: 400;
    font-size: clamp(2.2rem, 6vw, 3.6rem); line-height: 1.15;
    letter-spacing: -0.01em; text-wrap: balance;
  }
  #hero h1 em { font-style: italic; color: var(--bordo-acik); }
  #hero p { color: var(--soluk); margin-top: 18px; font-size: 1.05rem; max-width: 56ch;
            margin-left: auto; margin-right: auto; }

  /* Soru kartı */
  .kart {
    width: 100%; max-width: 720px; margin-top: 38px;
    background: var(--yuzey); border: 1px solid var(--cizgi); border-radius: 16px;
    padding: 18px; display: flex; flex-direction: column; gap: 14px;
  }
  .kart-satir { display: flex; gap: 10px; }
  #soru {
    flex: 1; background: none; border: none; color: var(--metin);
    font-size: 1.05rem; font-family: inherit; padding: 6px 8px;
  }
  #soru::placeholder { color: var(--soluk); }
  #soru:focus { outline: none; }
  #btn {
    background: var(--bordo); color: #fff; border: none; border-radius: 10px;
    padding: 10px 26px; font-size: 1rem; cursor: pointer;
  }
  #btn:hover { background: var(--bordo-acik); }
  #btn:disabled { opacity: 0.45; cursor: wait; }

  .cipler { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; margin-top: 22px; }
  .cip {
    background: none; border: 1px solid var(--cizgi); border-radius: 999px;
    color: var(--soluk); padding: 7px 16px; font-size: 0.88rem; cursor: pointer;
  }
  .cip:hover { border-color: var(--bordo); color: var(--metin); }

  /* Sohbet */
  #sohbet { width: 100%; max-width: 720px; display: none; flex-direction: column;
            gap: 14px; padding: 26px 0 10px; flex: 1; overflow-y: auto; }
  .mesaj { padding: 12px 16px; border-radius: 14px; max-width: 88%;
           white-space: pre-wrap; line-height: 1.55; }
  .kullanici { background: var(--bordo-koyu); color: #fff; align-self: flex-end; }
  .asistan { background: var(--yuzey); border: 1px solid var(--cizgi); align-self: flex-start; }
  .asistan.red { border-color: var(--bordo); }
  .kunye { font-size: 0.76rem; color: var(--soluk); align-self: flex-start;
           max-width: 88%; font-family: Consolas, monospace; }
  .kunye .b { color: var(--bordo-acik); }

  /* Ölçümler */
  #olcumler { width: 100%; max-width: 760px; display: none; padding: 30px 0; }
  #olcumler h2 { font-family: Georgia, serif; font-weight: 400; font-size: 1.4rem; margin: 22px 0 10px; }
  .tablo-kap { overflow-x: auto; border: 1px solid var(--cizgi); border-radius: 12px; }
  table { border-collapse: collapse; width: 100%; font-size: 0.9rem; min-width: 480px; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--cizgi); }
  tbody tr:last-child td { border-bottom: none; }
  th { color: var(--soluk); font-weight: 600; font-size: 0.74rem;
       text-transform: uppercase; letter-spacing: 0.08em; }
  .vurgu { color: var(--bordo-acik); font-weight: 600; }
  .kilit-kutu { border: 1px solid var(--bordo-koyu); border-radius: 12px;
                padding: 12px 16px; margin-bottom: 8px; font-size: 0.92rem; }
  .not { color: var(--soluk); font-size: 0.8rem; margin-top: 10px; }

  footer {
    text-align: center; color: var(--soluk); font-size: 0.78rem;
    padding: 18px; font-family: Consolas, monospace;
  }
  footer .b { color: var(--bordo-acik); }

  @media (prefers-reduced-motion: no-preference) {
    #hero { transition: opacity .35s ease, transform .35s ease; }
    #hero.kapan { opacity: 0; transform: translateY(-12px); }
  }
</style>
</head>
<body>

<nav>
  <div class="marka" onclick="gorunum('sohbet-yuzeyi')">lookup<b>.</b></div>
  <div class="nav-sag">
    <button id="nav-olcum" onclick="gorunum('olcumler')">Ölçümler</button>
    <a href="https://github.com/Semikgn/Lookup/blob/main/data/SOURCES.md" target="_blank" rel="noopener">Kaynaklar</a>
    <a href="https://github.com/Semikgn/Lookup" target="_blank" rel="noopener">GitHub</a>
  </div>
</nav>

<main>
  <section id="hero">
    <h1 class="serif">İnternete değil,<br><em>belgelere</em> sor.</h1>
    <p>Lookup, ağ ve sistem sorularını kendi makinendeki açık lisanslı Türkçe
       kaynaklardan cevaplar. Ne bulut hesabına ihtiyacı var ne internete.
       Cevabı belgelerde bulamazsa uydurmak yerine bunu açıkça söyler.</p>
  </section>

  <div class="kart" id="soru-karti">
    <div class="kart-satir">
      <input type="text" id="soru" placeholder="Merak ettiğini yaz" autocomplete="off">
      <button id="btn" onclick="gonder()">Sor</button>
    </div>
  </div>

  <div class="cipler" id="cipler">
    <button class="cip" onclick="cipSor(this)">DNS nedir?</button>
    <button class="cip" onclick="cipSor(this)">RAID 1 verileri nasıl korur?</button>
    <button class="cip" onclick="cipSor(this)">SSH hangi portu kullanır?</button>
    <button class="cip" onclick="cipSor(this)">OSI modeli kaç katmandır?</button>
  </div>

  <section id="sohbet"></section>

  <section id="olcumler"><div id="olcum-icerik">Yükleniyor...</div></section>
</main>

<footer>her cevap <span class="b">127.0.0.1</span>'den döner · foundry local · qwen2.5-coder-1.5b</footer>

<script>
const gecmis = [];
let sohbetBasladi = false;

function gorunum(ad) {
  document.getElementById('olcumler').style.display = ad === 'olcumler' ? 'block' : 'none';
  const sohbetGorunur = ad !== 'olcumler';
  document.getElementById('sohbet').style.display = (sohbetGorunur && sohbetBasladi) ? 'flex' : 'none';
  document.getElementById('soru-karti').style.display = sohbetGorunur ? 'flex' : 'none';
  document.getElementById('cipler').style.display = (sohbetGorunur && !sohbetBasladi) ? 'flex' : 'none';
  document.getElementById('hero').style.display = (sohbetGorunur && !sohbetBasladi) ? 'block' : 'none';
  if (ad === 'olcumler') olcumYukle();
}

function sohbeteGec() {
  if (sohbetBasladi) return;
  sohbetBasladi = true;
  const hero = document.getElementById('hero');
  hero.classList.add('kapan');
  setTimeout(() => { hero.style.display = 'none'; }, 300);
  document.getElementById('cipler').style.display = 'none';
  document.getElementById('sohbet').style.display = 'flex';
  const kart = document.getElementById('soru-karti');
  kart.style.marginTop = '10px';
  document.querySelector('main').appendChild(kart);
}

function ekle(sinif, metin) {
  const kutu = document.createElement('div');
  kutu.className = sinif;
  kutu.textContent = metin;
  document.getElementById('sohbet').appendChild(kutu);
  kutu.scrollIntoView({behavior: 'smooth'});
  return kutu;
}

function cipSor(dugme) {
  document.getElementById('soru').value = dugme.textContent;
  gonder();
}

async function gonder() {
  const girdi = document.getElementById('soru');
  const soru = girdi.value.trim();
  if (!soru) return;
  girdi.value = '';
  sohbeteGec();
  document.getElementById('btn').disabled = true;
  ekle('mesaj kullanici', soru);
  const bekleme = ekle('mesaj asistan', 'Belgelere bakıyorum...');
  try {
    const y = await fetch('/api/sor', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({soru, gecmis: gecmis.slice(-3)})
    });
    const v = await y.json();
    bekleme.textContent = v.cevap || '(boş cevap)';
    if (v.reddedildi) bekleme.classList.add('red');
    gecmis.push({soru, cevap: (v.cevap || '').slice(0, 300)});
    let satir;
    if (v.reddedildi) {
      satir = `belgelerde yok, model çağrılmadı · ${v.sure} sn`;
    } else if (v.parcalar && v.parcalar.length) {
      satir = `${v.sure} sn · ` + v.parcalar.map(p => `${p.kaynak}#${p.sira}`).join(' · ');
    } else {
      satir = `${v.sure} sn · sohbet geçmişinden`;
    }
    ekle('kunye', satir);
  } catch (hata) {
    bekleme.textContent = 'Bir şeyler ters gitti: ' + hata;
  }
  document.getElementById('btn').disabled = false;
  girdi.focus();
}

document.getElementById('soru').addEventListener('keydown', e => {
  if (e.key === 'Enter') gonder();
});

async function olcumYukle() {
  const hedef = document.getElementById('olcum-icerik');
  const y = await fetch('/api/olcumler');
  const v = await y.json();
  if (!v.retrieval) { hedef.textContent = 'Henüz ölçüm yok. Çalıştır: python -m bench.run_bench'; return; }
  let html = '';
  if (v.kilitli_model) {
    html += `<div class="kilit-kutu">Aktif model: <span class="vurgu">${v.kilitli_model}</span>. ` +
            `Seçim elle değil, aşağıdaki ölçümlerle yapıldı.</div>`;
  }
  html += '<h2 class="serif">Arama: düz kosinüs ile hibrit karşılaştırması</h2><div class="tablo-kap">';
  html += '<table><tr><th>Mod</th><th>hit@1</th><th>hit@3</th><th>Konu dışı reddi</th></tr>';
  for (const [mod, r] of Object.entries(v.retrieval)) {
    const vurgula = mod === 'hibrit';
    html += `<tr><td>${vurgula ? '<span class="vurgu">hibrit</span>' : mod}</td>` +
            `<td>%${Math.round(r.hit1 * 100)}</td><td>%${Math.round(r.hit3 * 100)} (${r.isabet})</td>` +
            `<td>${r.red_dogru}</td></tr>`;
  }
  html += '</table></div>';
  if (v.modeller && Object.keys(v.modeller).length) {
    html += '<h2 class="serif">Model yarışı</h2><div class="tablo-kap">';
    html += '<table><tr><th>Model</th><th>Doğruluk</th><th>Medyan süre</th></tr>';
    for (const [ad, m] of Object.entries(v.modeller)) {
      html += `<tr><td class="mono">${ad}</td><td>%${Math.round(m.rag_dogruluk * 100)}</td>` +
              `<td>${m.medyan_sure} sn</td></tr>`;
    }
    html += '</table></div>';
  }
  if (v.elenenler) {
    html += '<h2 class="serif">Elenenler</h2><div class="tablo-kap">';
    html += '<table><tr><th>Model</th><th>Neden</th></tr>';
    for (const [ad, e] of Object.entries(v.elenenler)) {
      html += `<tr><td class="mono">${ad}</td><td>${e.gerekce}</td></tr>`;
    }
    html += '</table></div>';
  }
  html += `<p class="not">36 soruluk Türkçe test seti üzerinde ölçüldü. Ayrıntılar repoda: bench/</p>`;
  hedef.innerHTML = html;
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def anasayfa() -> str:
    return SAYFA
