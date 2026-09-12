from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import sqlite3
import requests
from bs4 import BeautifulSoup

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

# TFF BOTU - YENİ HAFTA FİKSTÜRÜ ÇEKİCİ (AKILLI FİLTRELİ VE KARAKTER ÇÖZÜCÜLÜ)
@app.get("/api/otomatik-fikstur-cek")
async def otomatik_fikstur_cek(admin_sifre: str):
    if admin_sifre != "samsun55": return {"hata": "Yetkisiz İşlem!"}

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = "https://www.tff.org/default.aspx?pageID=198"

    try:
        res = requests.get(url, headers=headers, timeout=15)
        # TFF'nin garip karakter kodlamasını zorla çöz:
        res.encoding = 'utf-8' 
        soup = BeautifulSoup(res.content, "html.parser", from_encoding="utf-8")

        conn = sqlite3.connect("superlig.db")
        c = conn.cursor()
        
        # SİSTEMDEKİ ESKİ BOZUK YAZILARI TEMİZLE
        c.execute("DELETE FROM fikstur")
        
        eklenen = 0
        satirlar = soup.find_all("tr")
        for satir in satirlar:
            # İç içe geçmiş bozuk tabloları almaması için sadece doğrudan alt sütunlara bak
            sutunlar = satir.find_all("td", recursive=False) 
            if len(sutunlar) >= 4:
                ev = sutunlar[0].text.strip()
                skor = sutunlar[1].text.strip()
                dep = sutunlar[2].text.strip()
                tarih = sutunlar[3].text.strip()

                # AKILLI FİLTRE: Takım isimleri çok uzun olamaz ve başlık içeremez
                if 2 < len(ev) < 40 and 2 < len(dep) < 40 and "Takım" not in ev and "Hafta" not in ev:
                    m_id = f"{ev[:3].upper()}-{dep[:3].upper()}"
                    c.execute("INSERT OR IGNORE INTO fikstur (mac_id, ev_sahibi, deplasman, tarih) VALUES (?, ?, ?, ?)", (m_id, ev, dep, tarih))
                    eklenen += 1

        conn.commit()
        conn.close()
        return {"mesaj": f"Temizlik yapıldı. TFF Kazıma Botu çalıştı! {eklenen} maç sisteme pürüzsüz aktarıldı."}

    except Exception as e:
        return {"hata": f"Bot Hatası: {str(e)}"}

# TFF BOTU - SKOR OKUYUCU VE PUANLAYICI
@app.get("/api/otomatik-skor-guncelle")
async def otomatik_skor_guncelle(admin_sifre: str):
    if admin_sifre != "samsun55": return {"hata": "Yetkisiz İşlem!"}

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    url = "https://www.tff.org/default.aspx?pageID=198"

    try:
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.content, "html.parser", from_encoding="utf-8")

        biten_maclar = {}
        satirlar = soup.find_all("tr")

        for satir in satirlar:
            sutunlar = satir.find_all("td", recursive=False)
            if len(sutunlar) >= 4:
                ev = sutunlar[0].text.strip()
                skor_metin = sutunlar[1].text.strip()
                dep = sutunlar[2].text.strip()

                if 2 < len(ev) < 40 and "-" in skor_metin:
                    temiz_skor = skor_metin.replace(" ", "")
                    parcalar = temiz_skor.split("-")
                    
                    if len(parcalar) == 2 and parcalar[0].isdigit() and parcalar[1].isdigit():
                        ev_skor = int(parcalar[0])
                        dep_skor = int(parcalar[1])
                        m_id = f"{ev[:3].upper()}-{dep[:3].upper()}"
                        biten_maclar[m_id] = {"ev": ev_skor, "dep": dep_skor}

        conn = sqlite3.connect("superlig.db")
        c = conn.cursor()
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

        conn.commit()
        conn.close()
        
        return {"mesaj": f"Biten maçlar bulundu ve {hesaplanan} tahmin hesaplandı."}

    except Exception as e:
        return {"hata": f"Bot Hatası: {str(e)}"}
