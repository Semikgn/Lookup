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

## Sonuçlar

### Retrieval: düz kosinüs ile Türkçe hibrit karşılaştırması

| Mod | hit@1 | hit@3 | Domain-dışı red |
|---|---|---|---|
| düz kosinüs (v1) | %83.3 | %96.7 (29/30) | 5/5 |
| **hibrit (v2)** | **%90.0** | **%100 (30/30)** | **5/5** |

Hibrit skor üç sinyalin karışımıdır: anlamsal kosinüs (0.70), BM25 (0.22) ve
terim kapsama (0.08). Sinyaller sorgu başına min-max normalize edilir. Türkçe
tarafında İ/ı-duyarlı küçültme, stopword ayıklama ve hafif stemming
(snowballstemmer) var; sondan eklemeli dilde "yönlendiricinin" ile
"yönlendirici" ancak bu sayede eşleşiyor. Hibritin kurtardığı tipik vaka,
Türkçe soruyla İngilizce dokümandaki `ip link` komutunu bulmak oldu: embedding
diller arası köprüyü kuramadı, tam-terim eşleşmesi kurdu.

### Model seçimi (bir kez, ölçümle: 30 RAG + 5 konu dışı Türkçe soru)

| Model | RAG doğruluk | Medyan süre | Sonuç |
|---|---|---|---|
| **qwen2.5-coder-1.5b** | **%76.7** | **42 sn** | **seçilen model** |
| qwen3-1.7b (/no_think) | %73.3 | 111 sn | yedek (kilitli model diskte yoksa) |
| phi-4-mini | 5/5 (kısmi) | 135 sn | elendi: 7.7 GB RAM'de swap + süreç ölümleri |
| qwen3-4b | 6/6 (kısmi, v1) | ~100 sn | elendi: aynı donanım sorunu |
| qwen2.5-0.5b | %25 (v1) | 21 sn | elendi: kalite (genel Türkçe %8) |

phi-4-mini kalitede umut vericiydi (ölçülebilen her soruda doğru) ama bu
donanımda (7.7 GB RAM, GPU yok) cevap başına 68-179 sn sürdü ve koşular
tekrar tekrar süreç ölümüyle kesildi. Karar gereçleriyle birlikte
`bench/leaderboard.json` içinde.

### Konu dışı soruların reddi

Arama sinyalleri yeterince güçlü değilse soru modele hiç gitmez; kullanıcıya
"Bu bilgi mevcut dokümanlarda bulunamadı." dönülür. Karar ham kosinüs ve terim
kapsaması üzerinden verilir (`core/retriever.py`): iki kademeli eşik sınırına
ek olarak, anlamsal ve sözcüksel sinyalin aynı parçada buluşması şartı aranır.
Bu son şart, embedding'in "X kimdir" tarzı soruları ansiklopedi girişlerine
benzetmesinden doğan yanlış pozitifleri keser. Eşikler test setindeki 5 konu
dışı soru ve gerçek kullanım vakalarıyla kalibre edildi; konu dışı reddi 5/5,
konu içi 30 sorunun hiçbiri yanlışlıkla reddedilmiyor.

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
Soru ─► hibrit retrieval ──► skor >= eşik ─► en iyi parçalar + Türkçe prompt ─► qwen2.5-coder-1.5b
        (kosinüs+BM25+kapsama,│
         Türkçe stemming)     └► skor < eşik ─► "Bu bilgi mevcut dokümanlarda bulunamadı."
```

- **Depo:** SQLite (BLOB vektörler) + NumPy; BM25 bellekte. Harici vektör
  veritabanı bilinçli olarak kullanılmadı: bu ölçekte kaba kuvvet arama
  milisaniyeler sürüyor.
- **Değerlendirme:** `bench/testset.tr.json` içinde altın doküman etiketli
  30 RAG sorusu ve 5 konu dışı soru var. `bench/run_bench.py` soru bazlı
  checkpoint tutar ve `--limit` ile dilim dilim koşulabilir, kesinti emek
  kaybettirmez.
- **Foundry Local notları:** modeller API isteğiyle kendiliğinden yüklenmez;
  kod "not loaded" hatasını yakalayıp `foundry model load` çalıştırır ve isteği
  bir kez yineler. qwen3 ailesinde `/no_think` gerekir, yoksa düşünme tokenları
  CPU'da soru başına 40-90 saniye yer.
- **Üretim kalitesi:** küçük modellerin cümle tekrarı döngüsü çıktı katmanında
  kırılır (Jaccard benzerliğiyle tekrar ayıklama, `core/foundry.py`).
  `frequency_penalty` denendi ve geri alındı; bu sunucu/model ikilisinde
  döngüyü çözmek yerine kötüleştirdi. max_tokens 256, temperature 0.2.
- **Hız (CPU'da cevap başına ~10-20 saniye):** sürenin ana kalemi prompt'un
  okunması (prefill). Bu yüzden bağlam parçaları prompt'a girerken soru
  kökleriyle örtüşen cümleler seçilerek ~600 karaktere indirilir ve varsayılan
  k=2'dir. Örnek ölçüm: DNS sorusu 31.8 saniyeden 17.1 saniyeye indi.

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
