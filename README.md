# Lookup

**İnternete değil, belgelere sor.** Tamamen çevrimdışı, Türkçe'ye optimize
edilmiş doküman asistanı. Microsoft Azure Foundry Local yaz okulu projesi.
İsim, `nslookup`'a ve sözlükteki "lookup"a aynı anda göz kırpar; her cevap
`127.0.0.1`'den döner.

> Projenin eski adı **RAG Router TR** idi. v2'de runtime model router'ı
> kaldırıldı ve proje yeniden markalandı. Omurga artık **tek iyi model +
> Türkçe-özel hibrit retrieval + bunu sayıyla kanıtlayan değerlendirme**.
> Model seçimi çalışan bir katman değil, bir kereye mahsus ölçümle verilmiş
> ve belgelenmiş bir karar (aşağıda).

## Sonuçlar (asıl koz)

### Retrieval: düz kosinüs → Türkçe hibrit (before/after)

| Mod | hit@1 | hit@3 | Domain-dışı red |
|---|---|---|---|
| düz kosinüs (v1) | %83.3 | %96.7 (29/30) | 5/5 |
| **hibrit (v2)** | **%90.0** | **%100 (30/30)** | **5/5** |

Hibrit = anlamsal kosinüs (0.70) + BM25 (0.22) + terim kapsama (0.08), sinyaller
sorgu başına min-max normalize. Türkçe tarafı: İ/ı-duyarlı küçültme, stopword
ayıklama ve hafif stemming (snowballstemmer) — sondan eklemeli dilde
"yönlendiricinin" ↔ "yönlendirici" eşleşmesini BM25'e kazandırıyor. Hibritin
kurtardığı tipik vaka: Türkçe soruyla İngilizce dokümandaki `ip link` komutu —
embedding diller arası köprüyü kuramadı, tam-terim eşleşmesi kurdu.

### Model seçimi (bir kez, ölçümle — 30 RAG + 5 red Türkçe soru)

| Model | RAG doğruluk | Medyan süre | Sonuç |
|---|---|---|---|
| **qwen2.5-coder-1.5b** | **%76.7** | **42 sn** | 🔒 **kilitli model** |
| qwen3-1.7b (/no_think) | %73.3 | 111 sn | yedek (kilitli model diskte yoksa) |
| phi-4-mini | 5/5 (kısmi) | 135 sn | elendi: 7.7 GB RAM'de swap + süreç ölümleri |
| qwen3-4b | 6/6 (kısmi, v1) | ~100 sn | elendi: aynı donanım sorunu |
| qwen2.5-0.5b | %25 (v1) | 21 sn | elendi: kalite (genel Türkçe %8) |

phi-4-mini kalitede umut vericiydi (ölçülebilen her soruda doğru) ama bu
donanımda (7.7 GB RAM, GPU yok) cevap başına 68-179 sn sürdü ve koşular
tekrar tekrar süreç ölümüyle kesildi. Karar gereçleriyle birlikte
`bench/leaderboard.json` içinde.

### Domain-dışı reddi

En iyi parçanın ham kosinüsü < 0.45 VE terim kapsaması < 0.40 ise soru modele
hiç gitmez; "Bu bilgi mevcut dokümanlarda bulunamadı." dönülür. Eşikler ölçümle
kalibre edildi: domain-içi soruların kosinüs tabanı 0.51, domain-dışıların
tavanı 0.39. 5/5 red doğruluğu.

## Korpus

%100 açık lisanslı, ağırlıkla Türkçe: 18 Türkçe Wikipedia maddesi (CC BY-SA,
ağ/sistem kavramları: DNS, DHCP, TCP/IP, RAID, SSH, OSI...) + 3 ArchWiki how-to
(GFDL 1.3, İngilizce) + 3 proje dokümanı. Toplam 24 doküman, 354 parça.
Kaynak ve lisans dökümü: [`data/SOURCES.md`](data/SOURCES.md). Korpus
`python -m ingest.fetch_corpus` ile yeniden üretilebilir.

## Kurulum ve kullanım

```powershell
winget install Microsoft.FoundryLocal
pip install -r requirements.txt
foundry model download qwen2.5-coder-1.5b
foundry model download qwen3-embedding-0.6b

python -m ingest.fetch_corpus     # korpusu çek (tek seferlik, internet)
python -m ingest.ingest           # chunk -> embedding -> SQLite

# Soru sor (CLI)
python cli.py "DHCP kiralama süresi ne anlama gelir?"
python cli.py --mod duz "..."     # v1 düz kosinüsle karşılaştır
python cli.py --k 3 "..."         # kalite düğmesi: daha geniş bağlam
                                  # (varsayılan k=2: hit@2 %96.7; k=3: hit@3 %100)

# Benchmark (before/after + model yarışı)
python -m bench.run_bench --sadece-retrieval
python -m bench.run_bench

# Web arayüzü -> http://127.0.0.1:8000  (Sohbet + Ölçümler sekmeleri)
uvicorn app.main:app --port 8000
```

Bundan sonrası tamamen çevrimdışıdır: WiFi kapalıyken tüm istekler
`127.0.0.1`'e gider. Endpoint portu sabit değildir; kod `foundry server status`
çıktısından dinamik okur.

## Mimari

```
Soru ─► hibrit retrieval ──► skor >= eşik ─► top-3 parça + Türkçe prompt ─► qwen2.5-coder-1.5b
        (kosinüs+BM25+kapsama,│
         Türkçe stemming)     └► skor < eşik ─► "Bu bilgi mevcut dokümanlarda bulunamadı."
```

- **Depo:** SQLite (BLOB vektörler) + NumPy; BM25 bellekte. Vektör DB bilinçli yok.
- **Değerlendirme:** `bench/testset.tr.json` — 30 RAG (altın doküman etiketli,
  hit@k) + 5 domain-dışı; `bench/run_bench.py` soru bazlı checkpoint + `--limit`
  ile kesintiye dayanıklı.
- **Foundry Local notları:** modeller API'de otomatik yüklenmez ("not loaded"
  yakala → `foundry model load` → tekrar dene); qwen3 ailesinde `/no_think`
  şart (yoksa düşünme tokenları CPU'da 40-90 sn yer).
- **Üretim kalitesi/hızı:** küçük modellerin cümle-tekrar döngüsü çıktı
  katmanında kırılır (Jaccard ≥ 0.7 tekrar ayıklama, `core/foundry.py`);
  `frequency_penalty` denendi ve geri alındı — bu sunucu/model ikilisinde
  döngüyü paraphrase'e çevirip kötüleştirdi. max_tokens 256, temperature 0.2.
- **Latency (CPU'da ~10-20 sn/cevap):** prefill ana kalem olduğundan bağlam
  parçaları prompt'a girerken soru kökleriyle örtüşen cümleler seçilerek
  ~600 karaktere kırpılır (kör baş-kırpma değil; saf lexical seçim),
  varsayılan k=2. Ölçüm: 31.8 sn → 17.1 sn (DNS), 38.9 → 16.7 (RAID).

## Proje yapısı

```
├── data/                  # korpus (.txt/.md) + SOURCES.md + indeks.db
├── ingest/
│   ├── fetch_corpus.py    # açık lisanslı korpusu çek (tekrar üretilebilir)
│   └── ingest.py          # chunk -> embedding -> SQLite
├── core/
│   ├── foundry.py         # dinamik endpoint, model çözme/yükleme
│   ├── metin.py           # Türkçe tokenizasyon + stemming
│   ├── retriever.py       # hibrit arama + domain-dışı reddi
│   └── rag.py             # retrieve -> prompt -> generate
├── bench/                 # testset, run_bench, leaderboard(.v1).json, sonda.py
├── app/main.py            # FastAPI + arayüz
└── cli.py                 # hızlı test
```

<!-- WiFi kapalı demo ekran görüntüsü buraya: docs/demo.png -->
