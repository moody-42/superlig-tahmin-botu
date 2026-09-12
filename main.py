from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import sqlite3

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
    conn.commit()
    conn.close()

veritabani_ayarla()

def puan_hesapla(t_ev, t_dep, g_ev, g_dep):
    if (t_ev == g_ev and t_dep == g_dep) or (t_ev == t_dep and g_ev == g_dep):
        return 4
    t_fark = t_ev - t_dep
    g_fark = g_ev - g_dep
    if (t_fark > 0 and g_fark > 0) or (t_fark < 0 and g_fark < 0):
        if t_fark == g_fark: return 3
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

# --- GİZLİ ADMİN KONTROL MERKEZİ ---

@app.post("/api/admin/mac-ekle")
async def admin_mac_ekle(sifre: str, ev: str, dep: str, tarih: str):
    if sifre != "samsun55": return {"hata": "Yanlış Şifre!"}
    
    # Takım isimlerinin ilk 3 harfinden ID oluştur (Örn: GAL-FEN)
    m_id = f"{ev[:3].upper()}-{dep[:3].upper()}"
    
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO fikstur (mac_id, ev_sahibi, deplasman, tarih) VALUES (?, ?, ?, ?)", (m_id, ev, dep, tarih))
    conn.commit()
    conn.close()
    return {"mesaj": f"{ev} - {dep} sisteme eklendi."}

@app.post("/api/admin/skor-gir")
async def admin_skor_gir(sifre: str, mac_id: str, gercek_ev: int, gercek_dep: int):
    if sifre != "samsun55": return {"hata": "Yanlış Şifre!"}
    
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("SELECT nick, ev_skor, dep_skor FROM tahminler WHERE mac_id = ? AND kazanilan_puan = -1", (mac_id,))
    bekleyenler = c.fetchall()
    
    hesaplanan = 0
    for satir in bekleyenler:
        nick, t_ev, t_dep = satir
        p = puan_hesapla(t_ev, t_dep, gercek_ev, gercek_dep)
        c.execute("UPDATE kullanicilar SET puan = puan + ? WHERE nick = ?", (p, nick))
        c.execute("UPDATE tahminler SET kazanilan_puan = ? WHERE nick = ? AND mac_id = ?", (p, nick, mac_id))
        hesaplanan += 1
        
    conn.commit()
    conn.close()
    return {"mesaj": f"Skor onaylandı! {hesaplanan} kişinin puanı hesaplandı."}

@app.post("/api/admin/fikstur-temizle")
async def admin_temizle(sifre: str):
    if sifre != "samsun55": return {"hata": "Yanlış Şifre!"}
    conn = sqlite3.connect("superlig.db")
    c = conn.cursor()
    c.execute("DELETE FROM fikstur")
    conn.commit()
    conn.close()
    return {"mesaj": "Geçmiş tüm fikstür çöpe atıldı, sistem tertemiz!"}
