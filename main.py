from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import asyncio
import os
import sqlite3
import json
import urllib.request

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VERİTABANI KURULUMU ---
def veritabani_ayarla():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS kullanicilar (nick TEXT PRIMARY KEY, puan INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tahminler (nick TEXT, mac_id TEXT, ev_skor INTEGER, dep_skor INTEGER, kazanilan_puan INTEGER DEFAULT -1)''')
    conn.commit()
    conn.close()

veritabani_ayarla()

# --- PUANLAMA MOTORU ---
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

# --- SAYFA VE API YÖNLENDİRMELERİ ---

@app.get("/")
async def ana_sayfa():
    return FileResponse("index.html")

@app.get("/api/liderlik")
async def liderlik_tablosu():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT nick, puan FROM kullanicilar ORDER BY puan DESC")
    sonuclar = c.fetchall()
    conn.close()
    
    if not sonuclar:
        return []
    return [{"nick": satir[0], "puan": satir[1]} for satir in sonuclar]

@app.post("/api/tahmin-yap")
async def tahmin_kaydet(nick: str, mac_id: str, ev_skor: int, dep_skor: int):
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO kullanicilar (nick, puan) VALUES (?, ?)", (nick, 0))
    c.execute("DELETE FROM tahminler WHERE nick = ? AND mac_id = ?", (nick, mac_id))
    c.execute("INSERT INTO tahminler (nick, mac_id, ev_skor, dep_skor, kazanilan_puan) VALUES (?, ?, ?, ?, -1)", (nick, mac_id, ev_skor, dep_skor))
    conn.commit()
    conn.close()
    return {"mesaj": "Başarılı"}

# --- TAM OTOMATİK API HAKEM MOTORU ---
@app.post("/api/otomatik-skor-guncelle")
async def otomatik_skor_guncelle(admin_sifre: str):
    if admin_sifre != "samsun55":
        return {"hata": "Yetkisiz İşlem! Hatalı Şifre."}
        
    api_key = os.environ.get("FOOTBALL_API_KEY")
    if not api_key:
        return {"hata": "Render panelinde FOOTBALL_API_KEY bulunamadı!"}

    # API-Football: Süper Lig (Lig ID: 203), Güncel 2026 Sezonu, Son 15 Maç
    url = "https://v3.football.api-sports.io/fixtures?league=203&season=2026&last=15"
    
    try:
        req = urllib.request.Request(url)
        req.add_header("x-apisports-key", api_key)
        
        with urllib.request.urlopen(req) as response:
            veri = json.loads(response.read())
            
        biten_maclar = {}
        for mac in veri.get("response", []):
            # Maç durumu "Match Finished" (FT) ise sonuçları al
            if mac["fixture"]["status"]["short"] == "FT":
                mac_id = str(mac["fixture"]["id"])
                ev_skor = mac["goals"]["home"]
                dep_skor = mac["goals"]["away"]
                
                if ev_skor is not None and dep_skor is not None:
                    biten_maclar[mac_id] = {"ev": ev_skor, "dep": dep_skor}
                    
        conn = sqlite3.connect("superlig.db")
        c = conn.cursor()
        
        hesaplanan_tahmin_sayisi = 0
        
        # Puanı henüz hesaplanmamış (-1) tüm tahminleri bul
        c.execute("SELECT nick, mac_id, ev_skor, dep_skor FROM tahminler WHERE kazanilan_puan = -1")
        bekleyenler = c.fetchall()
        
        for satir in bekleyenler:
            nick, t_mac_id, t_ev, t_dep = satir
            
            # Kullanıcının tahminde bulunduğu maç, biten maçlar listesinde varsa
            if t_mac_id in biten_maclar:
                gercek_ev = biten_maclar[t_mac_id]["ev"]
                gercek_dep = biten_maclar[t_mac_id]["dep"]
                
                puan = puan_hesapla(t_ev, t_dep, gercek_ev, gercek_dep)
                
                # Kullanıcının toplam puanına ekle
                c.execute("UPDATE kullanicilar SET puan = puan + ? WHERE nick = ?", (puan, nick))
                # Tahmini "Hesaplandı" olarak işaretle ve aldığı puanı yaz
                c.execute("UPDATE tahminler SET kazanilan_puan = ? WHERE nick = ? AND mac_id = ?", (puan, nick, t_mac_id))
                
                hesaplanan_tahmin_sayisi += 1
                
        conn.commit()
        conn.close()
        
        return {"mesaj": f"API'ye başarıyla bağlanıldı. {hesaplanan_tahmin_sayisi} adet tahminin puanı otomatik hesaplanarak liderlik tablosuna aktarıldı."}
        
    except Exception as e:
        return {"hata": f"API bağlantı sorunu: {str(e)}"}
