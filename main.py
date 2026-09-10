from fastapi import FastAPI, WebSocket
import google.generativeai as genai
import json
import asyncio

app = FastAPI()

# --- 1. PUANLAMA MOTORU ---
def puan_hesapla(tahmin_ev, tahmin_deplasman, gercek_ev, gercek_deplasman):
    # Skoru birebir bilme veya beraberliği bilme durumu (Örn: 1-1, 2-2)
    if (tahmin_ev == gercek_ev and tahmin_deplasman == gercek_deplasman) or \
       (tahmin_ev == tahmin_deplasman and gercek_ev == gercek_deplasman):
        return 4
        
    tahmin_fark = tahmin_ev - tahmin_deplasman
    gercek_fark = gercek_ev - gercek_deplasman
    
    # Tarafı doğru bilme durumu (İkisi de ev sahibi veya ikisi de deplasman kazanmışsa)
    if (tahmin_fark > 0 and gercek_fark > 0) or (tahmin_fark < 0 and gercek_fark < 0):
        # Aradaki gol farkını da doğru bildiyse
        if tahmin_fark == gercek_fark:
            return 3
        # Sadece kazananı bildiyse
        return 2
        
    # Yanlış tahmin veya boş bırakma
    return 0

# --- 2. GEMINI YAPAY ZEKA BOTU ---
# API anahtarını şimdilik buraya ekliyoruz, daha sonra güvenli hale getireceğiz
genai.configure(api_key="SENIN_GEMINI_API_ANAHTARIN_BURAYA_GELECEK")

def bot_tahminlerini_al(haftanin_maclari):
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Sen bir futbol analistisin. Aşağıdaki Süper Lig maçları için gerçekçi skor tahminleri yap. 
    Lütfen sadece aşağıdaki JSON formatında yanıt ver, ekstra metin ekleme.
    
    Maçlar: {haftanin_maclari}
    
    Format:
    [
      {{"ev_sahibi": "Takım A", "deplasman": "Takım B", "tahmin_ev": 2, "tahmin_deplasman": 1}}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        tahminler = json.loads(response.text.strip('```json').strip('```'))
        return tahminler
    except Exception as e:
        return [] # Hata durumunda boş liste döner

# --- 3. API YÖNLENDİRMELERİ (SAYFALAR) ---

# 1. Sayfa: Liderlik Tablosu
@app.get("/api/liderlik")
async def liderlik_tablosu():
    # Veritabanı bağlandığında burası gerçek verileri çekecek
    siralama = [
        {"nick": "emirhan", "puan": 42},
        {"nick": "Bot_Gemini", "puan": 38},
        {"nick": "kullanici_2", "puan": 31}
    ]
    return siralama

# 2. Sayfa: Tahmin Penceresi
@app.post("/api/tahmin-yap")
async def tahmin_kaydet(kullanici_id: str, mac_id: str, ev_skor: int, dep_skor: int):
    # Maç başlama saati kontrolü ve veritabanı kaydı burada yapılacak
    return {"mesaj": "Tahmin başarıyla kilitlendi."}

# 3. Sayfa: Canlı Maç Merkezi
@app.websocket("/ws/canli-skor")
async def canli_mac_merkezi(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Anlık skor API'sinden gelen veriler burada simüle ediliyor
            anlik_veri = {
                "dakika": "45+2",
                "ev_sahibi": "Galatasaray",
                "deplasman": "Fenerbahçe",
                "gercek_skor": {"ev": 1, "dep": 1},
                "tahminler": [
                    {"nick": "emirhan", "tahmin_ev": 2, "tahmin_dep": 1, "anlik_puan": 0},
                    {"nick": "Bot_Gemini", "tahmin_ev": 1, "tahmin_dep": 1, "anlik_puan": 4}
                ]
            }
            await websocket.send_json(anlik_veri)
            await asyncio.sleep(60) # Her 60 saniyede bir güncelle
    except Exception as e:
        print(f"Bağlantı koptu: {e}")
