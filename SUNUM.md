# RAG Router TR — Sunum Taslağı (5-7 dk)

## 1. Problem (1 slayt)
- Bulut LLM'leri her yerde ama: internet şart, veri dışarı çıkıyor, maliyetli.
- Hedef: **tamamen çevrimdışı**, Türkçe çalışan, kendi dokümanlarını bilen asistan.
- Bonus: tek model her işte iyi değil → soruya göre **doğru modeli** seçmek.

## 2. Çözüm mimarisi (1 slayt)
- Foundry Local: OpenAI-uyumlu yerel endpoint, ONNX Runtime, CPU'da çalışıyor.
- Üç katman: Offline RAG → Akıllı Router → Türkçe Benchmark/Leaderboard.
- Demo makinesi: 7.7 GB RAM'li sıradan bir laptop — her şey küçük modellerle.

## 3. Offline RAG (1 slayt)
- data/ → paragraf bazlı chunk (~800 karakter) → qwen3-embedding-0.6b (1024d)
  → SQLite BLOB.
- Arama: NumPy kaba kuvvet kosinüs benzerliği. Vektör DB YOK — bu ölçekte
  gereksiz karmaşıklık (bilinçli mühendislik kararı).

## 4. Benchmark ve Leaderboard (1 slayt — leaderboard tablosunu göster)
- 36 Türkçe soru: 12 RAG + 12 kod + 12 genel muhakeme.
- Ölçüm: anahtar-ifade doğruluğu + latency. Çıktı: leaderboard.json.
- Kilit fikir: **router kuralla değil, ölçümle karar veriyor.**
  (0.5B model Türkçe'de saçmalıyor — tabloda görülüyor; 4B model doğru ama yavaş.)

## 5. Router (1 slayt)
- Intent sınıflandırma: kod desenleri + retrieval benzerlik eşiği.
- Model seçimi: leaderboard'da o kategorinin en iyisi (eşitlikte en hızlısı).
- Model inmemişse/yüklenemezse fallback zinciri.
- Arayüzde şeffaflık: "bu soru şu modele gitti çünkü..."

## 6. Canlı demo (2-3 dk)
1. WiFi'ı KAPAT.
2. `uvicorn app.main:app --port 8000`
3. Doküman sorusu: "Bu projede neden vektör veritabanı yok?" → RAG rotası + kaynaklar.
4. Kod sorusu: "Fibonacci fonksiyonu yaz" → coder modeline rota.
5. Genel soru: "Yarısı 8 olan sayı?" → genel model.
6. Leaderboard sekmesi: skorların nereden geldiğini göster.

## 7. Öğrenilenler / zorluklar (1 slayt)
- Foundry Local preview: CLI komutları sürümle değişiyor (`service` → `server`),
  varsaymak yerine `--help` ile doğrulamak şart.
- Modeller API'de otomatik yüklenmiyor → "not loaded" yakala, yükle, tekrar dene.
- 7.7 GB RAM'de model rotasyonu: kullanmadan yükle, bitince boşalt.
- Küçük modellerde tekrar döngüsü → max_tokens + düşük temperature.
- Windows konsolunda Türkçe karakter: UTF-8'i her katmanda zorlamak gerekti.

## 8. Gelecek işler (kapanış)
- Daha büyük Türkçe test seti + LLM-hakem puanlaması.
- Streaming cevaplar, çoklu doküman koleksiyonları.
- NPU/GPU'lu donanımda aynı mimariyle daha büyük modeller.
