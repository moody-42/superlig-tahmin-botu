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

def veritabani_ayarla():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS kullanicilar (nick TEXT PRIMARY KEY, puan INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tahminler (nick TEXT, mac_id TEXT, ev_skor INTEGER, dep_skor INTEGER, kazanilan_puan INTEGER DEFAULT -1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS fikstur (mac_id TEXT PRIMARY KEY, ev_sahibi TEXT, deplasman TEXT, tarih TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS gercek_lig (sira INTEGER PRIMARY KEY, takim TEXT, o INTEGER, g INTEGER, b INTEGER, m INTEGER, av INTEGER, p INTEGER)''')
    conn.commit()
    conn.close()

veritabani_ayarla()

def puan_hesapla(tahmin_ev, tahmin_deplasman, gercek_ev, gercek_deplasman):
    if (tahmin_ev == gercek_ev and tahmin_deplasman == gercek_deplasman) or (tahmin_ev == tahmin_deplasman and gercek_ev == gercek_deplasman):
        return 4
    tahmin_fark = tahmin_ev - tahmin_deplasman
    gercek_fark = gercek_ev - gercek_deplasman
    if (tahmin_fark > 0 and gercek_fark > 0) or (tahmin_fark < 0 and gercek_fark < 0):
        if tahmin_fark == gercek_fark: return 3
        return 2
    return 0

@app.get("/")
async def ana_sayfa():
    return FileResponse("index.html")

@app.get("/api/fikstur")
async def fikstur_getir():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT mac_id, ev_sahibi, deplasman, tarih FROM fikstur ORDER BY tarih ASC")
    sonuclar = c.fetchall()
    conn.close()
    return [{"mac_id": s[0], "ev": s[1], "dep": s[2], "tarih": s[3]} for s in sonuclar]

@app.get("/api/liderlik")
async def liderlik_tablosu():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT nick, puan FROM kullanicilar ORDER BY puan DESC")
    sonuclar = c.fetchall()
    conn.close()
    return [{"nick": satir[0], "puan": satir[1]} for satir in sonuclar]

@app.get("/api/gercek-puan-durumu")
async def gercek_puan_durumu():
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT sira, takim, o, g, b, m, av, p FROM gercek_lig ORDER BY sira ASC")
    sonuclar = c.fetchall()
    conn.close()
    return [{"sira": s[0], "takim": s[1], "o": s[2], "g": s[3], "b": s[4], "m": s[5], "av": s[6], "p": s[7]} for s in sonuclar]

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

# CRON JOB 1: SALI GÜNLERİ ÇALIŞACAK YENİ HAFTA BOTU (HATA AYIKLAMA MODU EKLENDİ)
@app.get("/api/otomatik-fikstur-cek")
async def otomatik_fikstur_cek(admin_sifre: str):
    if admin_sifre != "samsun55": return {"hata": "Yetkisiz İşlem!"}
    api_key = os.environ.get("FOOTBALL_API_KEY")
    
    url = "https://v3.football.api-sports.io/fixtures?league=203&season=2026&next=9"
    try:
        req = urllib.request.Request(url)
        req.add_header("x-apisports-key", api_key)
        with urllib.request.urlopen(req) as response:
            veri = json.loads(response.read())
            
        conn = sqlite3.connect("superlig.db")
        c = conn.cursor()
        
        eklenen = 0
        if "response" in veri:
            for mac in veri["response"]:
                m_id = str(mac["fixture"]["id"])
                tarih = mac["fixture"]["date"]
                ev = mac["teams"]["home"]["name"]
                dep = mac["teams"]["away"]["name"]
                c.execute("INSERT OR IGNORE INTO fikstur (mac_id, ev_sahibi, deplasman, tarih) VALUES (?, ?, ?, ?)", (m_id, ev, dep, tarih))
                eklenen += 1
            
        conn.commit()
        conn.close()
        
        # BÜTÜN CEVABI EKRANA BAS
        return {
            "mesaj": f"{eklenen} yeni maç sisteme eklendi.",
            "api_ham_cevap": veri
        }
    except Exception as e:
        return {"hata": f"Bağlantı sorunu: {str(e)}"}

# CRON JOB 2: GÜNLÜK ÇALIŞAN SKOR VE TABLO GÜNCELLEYİCİ
@app.get("/api/otomatik-skor-guncelle")
async def otomatik_skor_guncelle(admin_sifre: str):
    if admin_sifre != "samsun55": return {"hata": "Yetkisiz İşlem!"}
    api_key = os.environ.get("FOOTBALL_API_KEY")
    
    url_fikstur = "https://v3.football.api-sports.io/fixtures?league=203&season=2026&last=20"
    url_lig = "https://v3.football.api-sports.io/standings?league=203&season=2026"
    
    try:
        conn = sqlite3.connect("superlig.db")
        c = conn.cursor()

        req_f = urllib.request.Request(url_fikstur)
        req_f.add_header("x-apisports-key", api_key)
        with urllib.request.urlopen(req_f) as response:
            veri_f = json.loads(response.read())
            
        biten_maclar = {}
        for mac in veri_f.get("response", []):
            if mac["fixture"]["status"]["short"] in ["FT", "AET", "PEN"]:
                mac_id = str(mac["fixture"]["id"])
                biten_maclar[mac_id] = {"ev": mac["goals"]["home"], "dep": mac["goals"]["away"]}
                    
        c.execute("SELECT nick, mac_id, ev_skor, dep_skor FROM tahminler WHERE kazanilan_puan = -1")
        bekleyenler = c.fetchall()
        hesaplanan = 0
        
        for satir in bekleyenler:
            nick, t_mac_id, t_ev, t_dep = satir
            if t_mac_id in biten_maclar:
                gercek_ev = biten_maclar[t_mac_id]["ev"]
                gercek_dep = biten_maclar[t_mac_id]["dep"]
                puan = puan_hesapla(t_ev, t_dep, gercek_ev, gercek_dep)
                c.execute("UPDATE kullanicilar SET puan = puan + ? WHERE nick = ?", (puan, nick))
                c.execute("UPDATE tahminler SET kazanilan_puan = ? WHERE nick = ? AND mac_id = ?", (puan, nick, t_mac_id))
                hesaplanan += 1

        req_l = urllib.request.Request(url_lig)
        req_l.add_header("x-apisports-key", api_key)
        with urllib.request.urlopen(req_l) as response:
            veri_l = json.loads(response.read())
        
        if veri_l.get("response"):
            c.execute("DELETE FROM gercek_lig") 
            takimlar = veri_l["response"][0]["league"]["standings"][0]
            for t in takimlar:
                c.execute("INSERT INTO gercek_lig (sira, takim, o, g, b, m, av, p) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                          (t["rank"], t["team"]["name"], t["all"]["played"], t["all"]["win"], t["all"]["draw"], t["all"]["lose"], t["goalsDiff"], t["points"]))

        conn.commit()
        conn.close()
        return {"mesaj": f"{hesaplanan} tahmin hesaplandı ve gerçek lig tablosu güncellendi."}
    except Exception as e:
        return {"hata": f"API sorunu: {str(e)}"}
