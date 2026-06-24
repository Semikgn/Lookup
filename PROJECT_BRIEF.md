# RAG Router TR — Proje Brief'i

## Bağlam
Bu bir Microsoft Azure Foundry Local yaz okulu projesi. Hedef: tamamen offline
çalışan, Türkçe odaklı bir RAG asistanı. Üç katman var:

1. **Offline RAG** — lokal dokümanlardan soru-cevap (internet yok).
2. **Akıllı model router** — gelen sorunun türüne göre farklı yerel modeller
   arasında otomatik seçim.
3. **Türkçe benchmark/leaderboard** — router'ın seçimi elle yazılmış kuralla değil,
   modelleri Türkçe görevlerde ölçen bir skor tablosuyla yönetiliyor.

Tüm inference Foundry Local üzerinde (OpenAI-uyumlu lokal endpoint).

## Çalışma şeklin (önemli)
1. HEMEN kod yazma. Önce ortamı incele, sonra detaylı bir PLAN + görev listesi
   (TodoWrite) çıkar. Fazlara böl, her faza "definition of done" yaz.
2. Planı bana göster, onay bekle. Onaylayınca fazları SIRAYLA uygula.
3. Her görev bitince: test et → çalıştığını göster → commit at → todo'yu işaretle.
4. Her faz sonunda çalışan (demo edilebilir) bir çıktı olsun. Büyük tek seferde
   değil, artımlı ilerle.
5. Bir şeyden emin değilsen varsayım yapıp ilerleme; sor.

## Hard kurallar
- **TAMAMEN OFFLINE:** ilk model indirme dışında hiçbir bulut/internet çağrısı yok.
  OpenAI/Azure/HF API'ye gidme.
- **Vektör DB EKLEME.** SQLite'ta embedding'leri sakla, Python'da brute-force cosine
  similarity yap. Qdrant/FAISS/Chroma yok. (Resmi plana sadık kal, basit tut.)
- Foundry Local preview'da; CLI/SDK komutlarını varsaymadan `foundry --help` ile
  doğrula. Endpoint'i SABİT PORT olarak hardcode ETME — `foundry service status`
  ya da SDK'dan dinamik al.
- Model alias'larını hardcode etmeden önce `foundry model list` ile mevcut olanları
  kontrol et. Bir model bu donanımda yoksa daha küçüğüne düş (fallback).
- Sırlar/anahtarlar koda gömülmesin. Türkçe: prompt'lar, testset, UI hepsi Türkçe.
- Benchmark'ı şişirme: ~30-50 soru yeter (RAG + kod + genel reasoning). Akademik
  leaderboard'a kaçma.

## Stack (sabit)
- Python 3.11+, FastAPI (API) + basit bir arayüz (Streamlit ya da minimal HTML).
- Inference: Foundry Local, `openai` client'ı lokal endpoint'e yönlendirilerek.
- Router modelleri (mevcutsa): `phi-4-mini` (genel/reasoning), `qwen2.5-coder` (kod),
  `qwen2.5-0.5b` (hızlı/ucuz). `foundry model list` ile doğrula.
- Embedding: `qwen3-embedding-0.6b` (yoksa eşdeğer küçük lokal embedding modeli).
- Store: SQLite.

## Repo iskeleti (hedef)
```
rag-router-tr/
├── data/              # domain dokümanları (.txt/.md/.pdf)
├── ingest/ingest.py   # doküman → chunk → embedding → sqlite
├── core/
│   ├── foundry.py     # foundry local endpoint client (dinamik endpoint)
│   ├── retriever.py   # cosine similarity arama
│   ├── router.py      # intent → model seçimi (leaderboard.json'dan)
│   └── rag.py         # retrieve + prompt + generate
├── bench/
│   ├── testset.tr.json   # Türkçe soru seti
│   ├── run_bench.py      # modelleri skorla → leaderboard.json
│   └── leaderboard.json
├── app/main.py        # FastAPI / arayüz
├── cli.py             # hızlı test
├── requirements.txt
├── .env.example
└── README.md
```

## Fazlar (4 hafta — her biri ayrı milestone)
- **Faz 1 — Zemin:** ortam doğrulama, foundry client (`core/foundry.py`), tek modelle
  Python'dan cevap.
  *DoD:* `cli.py`'den tek modele soru sorup cevap alınıyor.
- **Faz 2 — Offline RAG:** ingest (chunk + embedding + sqlite) + retriever + rag.
  *DoD:* WiFi kapalı, `data/` içindeki dokümanlardan tek-model RAG cevabı geliyor.
- **Faz 3 — Benchmark:** `testset.tr.json` + `run_bench.py`, modelleri skorla +
  latency ölç → `leaderboard.json`.
  *DoD:* `leaderboard.json` üretiliyor, tablo okunabilir.
- **Faz 4 — Router + arayüz:** intent sınıflandırma → leaderboard'a göre model seçimi
  + fallback; FastAPI/arayüzde chat + leaderboard sekmesi + "bu soru şu modele gitti
  çünkü..." göstergesi.
  *DoD:* uçtan uca offline demo + README + kısa sunum taslağı.

## İlk adımın
1. `foundry --version`, `foundry service status`, `foundry model list` çalıştır.
   Foundry Local kurulu değilse kurulum komutunu yaz ve DUR.
2. Kuruluysa: yukarıdaki fazları görevlere böl, TodoWrite ile listele, planı bana
   sun ve onay bekle.
