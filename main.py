from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
import sqlite3
from fastapi.responses 
import FileResponse
app = FastAPI()

# Frontend (HTML) sayfasının sunucuya veri gönderebilmesi için güvenlik izni (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Her yerden erişime açık
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI KURULUMU (SQLite) ---
def veritabani_ayarla():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    # Kullanıcılar tablosu: Nick ve Toplam Puan
    c.execute('''CREATE TABLE IF NOT EXISTS kullanicilar (nick TEXT PRIMARY KEY, puan INTEGER)''')
    # Tahminler tablosu: Hangi nick, hangi maça ne dedi
    c.execute('''CREATE TABLE IF NOT EXISTS tahminler (nick TEXT, mac_id TEXT, ev_skor INTEGER, dep_skor INTEGER)''')
    conn.commit()
    conn.close()

# Sunucu her başladığında tabloları kontrol eder/oluşturur
veritabani_ayarla()

# --- 1. PUANLAMA MOTORU ---
def puan_hesapla(tahmin_ev, tahmin_deplasman, gercek_ev, gercek_deplasman):
    if (tahmin_ev == gercek_ev and tahmin_deplasman == gercek_deplasman) or \
       (tahmin_ev == tahmin_deplasman and gercek_ev == gercek_deplasman):
        return 4
    tahmin_fark = tahmin_ev - tahmin_deplasman
    gercek_fark = gercek_ev - gercek_deplasman
    if (tahmin_fark > 0 and gercek_fark > 0) or (tahmin_fark < 0 and gercek_fark < 0):
        if tahmin_fark == gercek_fark:
            return 3
        return 2
    return 0

# --- API YÖNLENDİRMELERİ (SAYFALAR) ---

# 1. Liderlik Tablosunu Veritabanından Çekme
@app.get("/api/liderlik")
async def liderlik_tablosu():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT nick, puan FROM kullanicilar ORDER BY puan DESC")
    sonuclar = c.fetchall()
    conn.close()
    
    # Eğer veritabanı henüz boşsa varsayılan liste döndür
    if not sonuclar:
        return [{"nick": "emirhan", "puan": 42}, {"nick": "kullanici_2", "puan": 31}]
        
    return [{"nick": satir[0], "puan": satir[1]} for satir in sonuclar]

# 2. Tahminleri Veritabanına Kaydetme
@app.post("/api/tahmin-yap")
async def tahmin_kaydet(nick: str, mac_id: str, ev_skor: int, dep_skor: int):
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    
    # Kullanıcı ilk defa tahmin yapıyorsa, onu 0 puanla sisteme kaydet
    c.execute("INSERT OR IGNORE INTO kullanicilar (nick, puan) VALUES (?, ?)", (nick, 0))
    
    # Aynı maça daha önce tahmin yapmışsa (fikrini değiştirmişse) eskisini sil
    c.execute("DELETE FROM tahminler WHERE nick = ? AND mac_id = ?", (nick, mac_id))
    
    # Yeni tahmini kaydet
    c.execute("INSERT INTO tahminler (nick, mac_id, ev_skor, dep_skor) VALUES (?, ?, ?, ?)", (nick, mac_id, ev_skor, dep_skor))
    
    conn.commit()
    conn.close()
    return {"mesaj": f"{nick}, {mac_id} maçı için tahminin ({ev_skor}-{dep_skor}) kaydedildi."}

# 3. Canlı Maç Merkezi (WebSocket)
@app.websocket("/ws/canli-skor")
async def canli_mac_merkezi(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Simüle edilmiş anlık skor verisi
            anlik_veri = {
                "dakika": "45+2",
                "ev_sahibi": "Galatasaray",
                "deplasman": "Fenerbahçe",
                "gercek_skor": {"ev": 1, "dep": 1},
                "tahminler": [
                    {"nick": "emirhan", "tahmin_ev": 2, "tahmin_dep": 1, "anlik_puan": 0}
                ]
            }
            await websocket.send_json(anlik_veri)
            await asyncio.sleep(60)
    except Exception as e:
        print(f"Bağlantı koptu: {e}")
        @app.get("/")

        async def ana_sayfa():
    return FileResponse("index.html")
