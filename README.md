# 🧭 RAG Router TR

Tamamen **çevrimdışı** çalışan, Türkçe odaklı bir RAG asistanı. Microsoft Azure
Foundry Local yaz okulu projesi. Üç katmandan oluşur:

1. **Offline RAG** — `data/` içindeki dokümanlardan soru-cevap (internet yok).
2. **Akıllı model router** — soru türüne göre (kod / doküman / genel) yerel
   modeller arasında otomatik seçim.
3. **Türkçe benchmark & leaderboard** — router'ın seçimi elle yazılmış kurallarla
   değil, modelleri Türkçe görevlerde ölçen bir skor tablosuyla yönetilir.

Tüm inference [Foundry Local](https://github.com/microsoft/Foundry-Local)
üzerinde, OpenAI-uyumlu **yerel** endpoint ile yapılır. İlk model indirme
dışında hiçbir bulut/internet çağrısı yoktur.

## Kurulum

```powershell
winget install Microsoft.FoundryLocal
pip install -r requirements.txt

# Modelleri indir (tek seferlik, internet gerektirir)
foundry model download qwen2.5-0.5b
foundry model download qwen2.5-coder-1.5b
foundry model download qwen3-4b
foundry model download qwen3-embedding-0.6b
```

> Endpoint portu sabit değildir; kod, `foundry server status` çıktısından
> dinamik olarak okur. Elle sabitlemek istersen `.env.example`'a bak.

## Kullanım

```powershell
# 1) Dokümanları indeksle (data/ -> chunk -> embedding -> SQLite)
python -m ingest.ingest

# 2) Hızlı test (CLI)
python cli.py "Türkiye'nin başkenti neresi?"
python cli.py --rag "Bu projede neden vektör veritabanı yok?"
python cli.py --rol kod "Faktöriyel hesaplayan fonksiyon yaz"

# 3) Benchmark koş -> leaderboard.json üret
python -m bench.run_bench

# 4) Web arayüzü (Sohbet + Leaderboard sekmeleri)
uvicorn app.main:app --port 8000
```

Arayüzde her cevabın altında **"bu soru şu modele gitti çünkü..."** rotası
gösterilir: sınıflandırılan kategori, seçilen model ve leaderboard gerekçesi.

## Mimari

```
Soru ─► router.kategori_bul ──► kod?  ─► leaderboard[kod]  en iyi model
              │                 rag?  ─► retriever (SQLite + NumPy cosine)
              │                          └─► bağlam + prompt ─► model
              └── benzerlik < eşik ───► genel ─► leaderboard[genel]
```

- **Vektör deposu:** SQLite (BLOB) + NumPy kaba kuvvet kosinüs benzerliği.
  Bilinçli sadelik: bu ölçekte harici vektör DB gereksiz.
- **Embedding:** `qwen3-embedding-0.6b` (1024 boyut).
- **Benchmark:** `bench/testset.tr.json` — 36 Türkçe soru (12 RAG + 12 kod +
  12 genel muhakeme). Doğruluk anahtar-ifade eşleşmesiyle, hız latency ile ölçülür.
- **RAM dostu:** modeller kullanılırken yüklenir, model değişiminde öncekiler
  bellekten çıkarılır (`foundry model unload`). Bir model inmemişse otomatik
  olarak daha küçüğüne düşülür.

## Proje yapısı

```
├── data/              # dokümanlar (.txt/.md/.pdf) + indeks.db
├── ingest/ingest.py   # doküman -> chunk -> embedding -> SQLite
├── core/
│   ├── foundry.py     # dinamik endpoint, model çözme/yükleme, chat
│   ├── retriever.py   # kosinüs benzerliği araması
│   ├── router.py      # intent -> leaderboard'dan model seçimi
│   └── rag.py         # retrieve + prompt + generate
├── bench/             # testset.tr.json, run_bench.py, leaderboard.json
├── app/main.py        # FastAPI + tek sayfa arayüz
└── cli.py             # hızlı test
```
