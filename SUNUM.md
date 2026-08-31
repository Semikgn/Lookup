# RAG Router TR v2 — Sunum Taslağı (5-7 dk)

## 1. Problem (1 slayt)
- Bulut LLM'leri: internet şart, veri dışarıda, maliyetli.
- Hedef: 7.7 GB RAM'li sıradan bir laptopta, tamamen çevrimdışı, Türkçe RAG asistanı.
- İddia: kaliteyi büyük modelden değil, **daha iyi retrieval'dan** çıkarmak.

## 2. v1 → v2 hikâyesi (1 slayt)
- v1: 3 model + runtime router + leaderboard. Çalıştı; ama router'ın gerekçesi
  zayıftı (coder neredeyse her kategoride kazanıyordu).
- v2 kararı: router'ı KALDIR. Tek iyi model + Türkçe'ye optimize hibrit retrieval.
- "Hangi model" sorusu çalışan bir katman değil, ölçümle verilen belgeli bir karar.

## 3. Türkçe hibrit retrieval (1 slayt — teknik omurga)
- 3 sinyal: anlamsal kosinüs (0.70) + BM25 (0.22) + terim kapsama (0.08);
  sorgu başına min-max normalizasyon (yoksa BM25 her şeyi ezer).
- Türkçe farkı: İ/ı-duyarlı küçültme + stopword + hafif stemming
  ("yönlendiricinin" ↔ "yönlendirici" — sondan eklemeli dilde BM25 recall'u).
- Domain-dışı reddi: ham kosinüs < 0.45 VE kapsama < 0.40 → modele gitmeden
  "dokümanlarda bulunamadı" (eşikler ölçümle kalibre: domain-içi taban 0.51,
  domain-dışı tavan 0.39).

## 4. Before/after — ASIL KOZ (1 slayt, tabloyu göster)
| | hit@1 | hit@3 | red |
|---|---|---|---|
| düz kosinüs | %83.3 | %96.7 | 5/5 |
| hibrit | **%90.0** | **%100** | 5/5 |
- Kurtarılan vaka: Türkçe soru → İngilizce dokümandaki `ip link` komutu.
  Embedding diller arası köprüyü kuramadı, tam-terim eşleşmesi kurdu.
- Korpus: 24 açık lisanslı doküman / 354 parça (SOURCES.md ile lisans dökümü).

## 5. Model seçimi: ölçümle kilit (1 slayt)
- Yarış: coder-1.5b %76.7 @ 42 sn 🔒 | qwen3-1.7b %73.3 @ 111 sn | phi-4-mini
  5/5 doğru ama 135 sn medyan + süreç ölümleri → ELENDİ.
- Ders: "en iyi model" donanım bağlamında tanımlanır. phi-4-mini kaliteliydi;
  bu makinede kullanılamazdı. Ölçüm olmasa yanlış model kilitlenirdi.

## 6. Canlı demo (2 dk)
1. WiFi'ı KAPAT. `uvicorn app.main:app --port 8000`
2. "RAID 1 verileri nasıl korur?" → kaynaklar + skorlarla cevap.
3. "Mona Lisa'yı kim yaptı?" → ⛔ 6 saniyede modelsiz red.
4. Ölçümler sekmesi: before/after + model yarışı + elenenler.

## 7. Mühendislik dersleri (1 slayt)
- Foundry Local preview: komutlar sürümle değişiyor; `--help` ile doğrula.
  Modeller API'de otomatik yüklenmiyor; qwen3'te `/no_think` şart.
- 7.7 GB RAM'de uzun benchmark koşuları kesiliyor → soru bazlı checkpoint +
  dilimli koşu (`--limit`), kesinti maliyeti sıfıra indi.
- Ölçmeden karar verme: probe (5 soruluk sonda) ucuz, yanlış model kilidi pahalı.

## 8. Gelecek (kapanış)
- LLM-hakem puanlaması (anahtar-kelime eşleşmesinin ötesi).
- Streaming cevap; korpus genişletme (fetch_corpus.py hazır).
- NPU/GPU donanımda phi-4-mini'yi kadroya geri almak — mimari hazır.
