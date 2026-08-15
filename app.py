import streamlit as st
import pandas as pd
import sqlite3
import json
from datetime import datetime
from PIL import Image
from google import genai

# --- CONFIG & INITIALIZATION ---
st.set_page_config(page_title="POS Kasir Kopi V2", layout="wide", page_icon="☕")

# Connect SQLite
conn = sqlite3.connect("kasir_kopi.db", check_same_thread=False)
c = conn.cursor()

# Setup Tables
c.execute('''CREATE TABLE IF NOT EXISTS stok (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama_bahan TEXT UNIQUE,
                jumlah REAL,
                satuan TEXT,
                harga_per_satuan REAL DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS resep (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama_menu TEXT,
                nama_bahan TEXT,
                jumlah_butuh REAL)''')

c.execute('''CREATE TABLE IF NOT EXISTS transaksi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                detail_order TEXT,
                total_harga REAL,
                metode_pembayaran TEXT,
                nama_pelanggan TEXT DEFAULT '',
                catatan TEXT DEFAULT '',
                status_pembayaran TEXT DEFAULT 'Lunas')''')

c.execute('''CREATE TABLE IF NOT EXISTS biaya_operasional (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                keterangan TEXT,
                total_biaya REAL)''')
conn.commit()

# Setup Gemini AI Client
gemini_key = st.secrets.get("GEMINI_API_KEY", None)
client = genai.Client(api_key=gemini_key) if gemini_key else None

st.title("☕ POS Kasir Kopi & Manajemen Stok (V2)")

# --- NAVIGATION TABS ---
tab_kasir, tab_kasbon, tab_stok, tab_laporan = st.tabs([
    "🛒 POS Kasir", 
    "📑 Buku Kasbon", 
    "📦 Restok & Gudang", 
    "📊 Laporan & Scan AI"
])

# ==========================================
# 1. TAB POS KASIR (WITH LIVE STOK DISPLAY)
# ==========================================
with tab_kasir:
    st.header("Point of Sale (Kasir)")
    
    # Ambil Menu dari Resep
    c.execute("SELECT DISTINCT nama_menu FROM resep")
    menu_list = [row[0] for row in c.fetchall()]
    
    col1, col2, col3 = st.columns([1.5, 1.2, 1.3])
    
    if "cart" not in st.session_state:
        st.session_state.cart = {}

    with col1:
        st.subheader("1. Pilih Menu")
        if not menu_list:
            st.info("Belum ada menu resep. Silakan masukkan resep di Tab Restok & Gudang!")
        else:
            pilih_menu = st.selectbox("Menu", menu_list)
            qty = st.number_input("Jumlah Porsi", min_value=1, value=1)
            
            # Hitung Estimasi HPP Real
            c.execute("""
                SELECT r.nama_bahan, r.jumlah_butuh, s.harga_per_satuan 
                FROM resep r 
                JOIN stok s ON r.nama_bahan = s.nama_bahan 
                WHERE r.nama_menu = ?
            """, (pilih_menu,))
            resep_items = c.fetchall()
            
            hpp_real = sum([item[1] * item[2] for item in resep_items])
            harga_jual_default = float(hpp_real * 2.5) if hpp_real > 0 else 15000.0
            
            harga_jual = st.number_input("Harga Jual / Porsi (Rp)", value=harga_jual_default, step=1000.0)
            
            if st.button("➕ Tambah ke Keranjang", use_container_width=True):
                if pilih_menu in st.session_state.cart:
                    st.session_state.cart[pilih_menu]['qty'] += qty
                else:
                    st.session_state.cart[pilih_menu] = {
                        'qty': qty,
                        'harga': harga_jual,
                        'hpp': hpp_real
                    }
                st.success(f"{pilih_menu} ditambahkan!")

    with col2:
        st.subheader("2. 🛒 Keranjang Belanja")
        total_bayar = 0
        detail_summary = []
        
        for item, val in list(st.session_state.cart.items()):
            subtotal = val['harga'] * val['qty']
            total_bayar += subtotal
            detail_summary.append(f"{item} x{val['qty']} ({subtotal:,.0f})")
            st.write(f"**{item}** x{val['qty']} = Rp {subtotal:,.0f}")
        
        st.markdown(f"### **Total: Rp {total_bayar:,.0f}**")
        
        metode = st.selectbox("Metode Pembayaran", ["Tunai", "QRIS / Transfer", "Hutang / Kasbon"])
        
        nama_pelanggan = ""
        catatan_kasbon = ""
        if metode == "Hutang / Kasbon":
            nama_pelanggan = st.text_input("Nama Pelanggan (Wajib)", placeholder="Misal: Mas Budi")
            catatan_kasbon = st.text_input("Catatan / No. HP", placeholder="Misal: Langganan")

        if st.button("✅ Selesaikan Transaksi", use_container_width=True):
            if metode == "Hutang / Kasbon" and not nama_pelanggan.strip():
                st.error("Nama pelanggan wajib diisi untuk transaksi Kasbon!")
            elif total_bayar > 0:
                status_pembayaran = "Belum Lunas" if metode == "Hutang / Kasbon" else "Lunas"
                tgl_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                detail_str = ", ".join(detail_summary)
                
                # Potong Stok Bahan
                for item, val in st.session_state.cart.items():
                    c.execute("SELECT nama_bahan, jumlah_butuh FROM resep WHERE nama_menu=?", (item,))
                    resep_bahan = c.fetchall()
                    for b_nama, b_butuh in resep_bahan:
                        total_butuh = b_butuh * val['qty']
                        c.execute("UPDATE stok SET jumlah = jumlah - ? WHERE nama_bahan=?", (total_butuh, b_nama))
                
                # Simpan Transaksi
                c.execute("""
                    INSERT INTO transaksi (tanggal, detail_order, total_harga, metode_pembayaran, nama_pelanggan, catatan, status_pembayaran)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (tgl_now, detail_str, total_bayar, metode, nama_pelanggan, catatan_kasbon, status_pembayaran))
                
                conn.commit()
                st.session_state.cart = {}
                st.balloons()
                st.success("Transaksi Berhasil!")
                st.rerun()

    # --- INFORMASI STOK BAHAN LANGSUNG ---
    with col3:
        st.subheader("3. 📦 Sisa Stok Bahan")
        df_stok_live = pd.read_sql_query("SELECT nama_bahan as 'Bahan', jumlah as 'Sisa Stok', satuan as 'Satuan' FROM stok", conn)
        if df_stok_live.empty:
            st.caption("Belum ada data bahan di gudang.")
        else:
            st.dataframe(df_stok_live, hide_index=True, use_container_width=True)

# ==========================================
# 2. TAB BUKU KASBON
# ==========================================
with tab_kasbon:
    st.header("📑 Buku Catatan Kasbon / Hutang Pelanggan")
    
    query_kasbon = """
        SELECT nama_pelanggan, SUM(total_harga) as total_hutang, COUNT(id) as jumlah_transaksi
        FROM transaksi
        WHERE status_pembayaran = 'Belum Lunas'
        GROUP BY nama_pelanggan
    """
    df_kasbon = pd.read_sql_query(query_kasbon, conn)
    
    if df_kasbon.empty:
        st.success("🎉 Tidak ada tunggakan kasbon saat ini!")
    else:
        st.warning(f"Total Piutang Belum Tertagih: **Rp {df_kasbon['total_hutang'].sum():,.0f}**")
        
        col_k1, col_k2 = st.columns([2, 1])
        
        with col_k1:
            st.subheader("Daftar Penagihan Per Pelanggan")
            st.dataframe(df_kasbon, use_container_width=True)
            
        with col_k2:
            st.subheader("Pelunasan Kasbon")
            pelanggan_pilih = st.selectbox("Pilih Pelanggan", df_kasbon['nama_pelanggan'].tolist())
            
            c.execute("SELECT SUM(total_harga) FROM transaksi WHERE nama_pelanggan=? AND status_pembayaran='Belum Lunas'", (pelanggan_pilih,))
            hutang_pilihan = c.fetchone()[0] or 0
            
            st.write(f"Total Hutang **{pelanggan_pilih}**: **Rp {hutang_pilihan:,.0f}**")
            
            metode_pelunasan = st.radio("Metode Bayar Pelunasan", ["Tunai", "QRIS / Transfer"])
            
            if st.button(f"🟢 Lunasi Semua Hutang {pelanggan_pilih}"):
                tgl_pelunasan = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""
                    UPDATE transaksi 
                    SET status_pembayaran = 'Lunas', catatan = catatan || ' (Dilunasi: ' || ? || ' via ' || ? || ')'
                    WHERE nama_pelanggan = ? AND status_pembayaran = 'Belum Lunas'
                """, (tgl_pelunasan, metode_pelunasan, pelanggan_pilih))
                conn.commit()
                st.success(f"Hutang atas nama {pelanggan_pilih} telah LUNAS!")
                st.rerun()

# ==========================================
# 3. TAB RESTOK & STOK GUDANG (MANUAL WITH DROPDOWN LIST)
# ==========================================
with tab_stok:
    st.header("📦 Kelola Stok Gudang & Restok Manual")
    
    col_st1, col_st2 = st.columns([1, 1])
    
    with col_st1:
        st.subheader("➕ Tambah / Restok Bahan Manual")
        
        # Ambil daftar bahan baku yang sudah ada di database + opsi standar kopi
        c.execute("SELECT nama_bahan FROM stok")
        existing_bahan = [row[0] for row in c.fetchall()]
        
        # Preset bahan umum toko kopi jika database masih kosong
        default_preset = ["biji kopi espresso", "susu uht 1l", "susu skm", "sirup vanila", "gula aren", "cup 16oz", "sedotan"]
        all_bahan_options = list(set(existing_bahan + default_preset))
        all_bahan_options.sort()
        all_bahan_options.append("➕ [Tambah Bahan Baru...]")
        
        pilihan_bahan = st.selectbox("Pilih Nama Bahan Baku", all_bahan_options)
        
        # Jika memilih tambah bahan baru
        if pilihan_bahan == "➕ [Tambah Bahan Baru...]":
            input_bahan = st.text_input("Ketik Nama Bahan Baru", placeholder="misal: Matcha Powder").lower().strip()
            input_satuan = st.text_input("Satuan", placeholder="misal: gram, ml, pcs, kaleng").lower().strip()
        else:
            input_bahan = pilihan_bahan
            # Auto-fill satuan jika bahan sudah ada di database
            c.execute("SELECT satuan FROM stok WHERE nama_bahan=?", (input_bahan,))
            satuan_res = c.fetchone()
            satuan_default = satuan_res[0] if satuan_res else "pcs"
            input_satuan = st.text_input("Satuan", value=satuan_default).lower().strip()
            
        input_jumlah = st.number_input("Jumlah Restok", min_value=0.0, value=1.0)
        input_harga = st.number_input("Harga Beli Total (Rp)", min_value=0.0, step=1000.0)
        
        if st.button("📥 Simpan Restok Manual", use_container_width=True):
            if input_bahan and input_satuan:
                harga_satuan = input_harga / input_jumlah if input_jumlah > 0 else 0
                tgl_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                c.execute("SELECT id FROM stok WHERE nama_bahan=?", (input_bahan,))
                existing = c.fetchone()
                
                if existing:
                    c.execute("UPDATE stok SET jumlah = jumlah + ?, harga_per_satuan = ? WHERE nama_bahan=?", 
                              (input_jumlah, harga_satuan, input_bahan))
                else:
                    c.execute("INSERT INTO stok (nama_bahan, jumlah, satuan, harga_per_satuan) VALUES (?, ?, ?, ?)", 
                              (input_bahan, input_jumlah, input_satuan, harga_satuan))
                
                if input_harga > 0:
                    c.execute("INSERT INTO biaya_operasional (tanggal, keterangan, total_biaya) VALUES (?, ?, ?)",
                              (tgl_now, f"Restok Manual: {input_bahan} ({input_jumlah} {input_satuan})", input_harga))
                
                conn.commit()
                st.success(f"Berhasil menambahkan {input_bahan} ke gudang!")
                st.rerun()
            else:
                st.error("Nama bahan dan satuan wajib diisi!")

    with col_st2:
        st.subheader("📋 Status Stok & Real Cost HPP Saat Ini")
        df_stok = pd.read_sql_query("SELECT nama_bahan as 'Bahan Baku', jumlah as 'Jumlah Stok', satuan as 'Satuan', harga_per_satuan as 'HPP / Satuan (Rp)' FROM stok", conn)
        st.dataframe(df_stok, use_container_width=True)

# ==========================================
# 4. TAB LAPORAN & SCAN AI NOTA
# ==========================================
with tab_laporan:
    st.header("📊 Laporan Keuangan Owner & Scan AI Nota")
    
    # --- METRICS KEUANGAN ---
    df_trans = pd.read_sql_query("SELECT * FROM transaksi", conn)
    df_biaya = pd.read_sql_query("SELECT * FROM biaya_operasional", conn)
    
    total_omzet = df_trans[df_trans['status_pembayaran'] == 'Lunas']['total_harga'].sum() if not df_trans.empty else 0
    total_biaya_restok = df_biaya['total_biaya'].sum() if not df_biaya.empty else 0
    laba_bersih = total_omzet - total_biaya_restok
    
    col_l1, col_l2, col_l3 = st.columns(3)
    col_l1.metric("Total Omzet (Lunas)", f"Rp {total_omzet:,.0f}")
    col_l2.metric("Total Pengeluaran Restok", f"Rp {total_biaya_restok:,.0f}")
    col_l3.metric("Estimasi Laba Bersih", f"Rp {laba_bersih:,.0f}")
    
    st.divider()
    
    # --- SCAN AI NOTA SECTION ---
    st.subheader("📸 AI Scan Nota Pengeluaran / Belanja")
    st.caption("Upload foto nota belanja dari pasar/supermarket. AI akan otomatis mencatat pengeluaran & meng-update stok gudang.")
    
    col_scan1, col_scan2 = st.columns([1, 1])
    
    with col_scan1:
        uploaded_file = st.file_uploader("Upload / Foto Nota Belanja", type=["jpg", "jpeg", "png"])
        
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Preview Nota Belanja", use_container_width=True)
            
            if st.button("🤖 Analisis Nota dengan AI", use_container_width=True):
                if not client:
                    st.error("API Key Gemini belum dipasang di Streamlit Secrets!")
                else:
                    with st.spinner("AI sedang membaca nota belanjaanmu..."):
                        prompt = """
                        Kamu adalah asisten kasir toko kopi. Analisis foto nota belanja ini dan ekstrak daftar bahan baku.
                        Keluarkan hasil HANYA berupa JSON valid dengan format seperti ini tanpa markdown code block:
                        [
                          {"nama_bahan": "Susu SKM", "jumlah": 5, "satuan": "kaleng", "total_harga": 60000},
                          {"nama_bahan": "Kopi Biji", "jumlah": 1, "satuan": "kg", "total_harga": 120000}
                        ]
                        """
                        try:
                            response = client.models.generate_content(
                                model='gemini-1.5-flash',
                                contents=[image, prompt]
                            )
                            cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
                            items_nota = json.loads(cleaned_text)
                            st.session_state['ai_nota_result'] = items_nota
                            st.success("Nota berhasil dibaca!")
                        except Exception as e:
                            st.error(f"Gagal membaca nota: {e}")

    with col_scan2:
        if 'ai_nota_result' in st.session_state:
            st.write("### Hasil Ekstraksi AI:")
            df_ai = pd.DataFrame(st.session_state['ai_nota_result'])
            st.dataframe(df_ai, use_container_width=True)
            
            if st.button("📥 Konfirmasi & Update ke Stok & Laporan", use_container_width=True):
                tgl_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for item in st.session_state['ai_nota_result']:
                    nama = item['nama_bahan'].lower().strip()
                    qty = float(item['jumlah'])
                    satuan = item['satuan'].lower().strip()
                    total_biaya = float(item['total_harga'])
                    harga_satuan = total_biaya / qty if qty > 0 else 0
                    
                    # Update/Insert ke Stok
                    c.execute("SELECT id FROM stok WHERE nama_bahan=?", (nama,))
                    existing = c.fetchone()
                    if existing:
                        c.execute("UPDATE stok SET jumlah = jumlah + ?, harga_per_satuan = ? WHERE nama_bahan=?", 
                                  (qty, harga_satuan, nama))
                    else:
                        c.execute("INSERT INTO stok (nama_bahan, jumlah, satuan, harga_per_satuan) VALUES (?, ?, ?, ?)",
                                  (nama, qty, satuan, harga_satuan))
                        
                    # Catat ke Pengeluaran Operasional Laporan
                    c.execute("INSERT INTO biaya_operasional (tanggal, keterangan, total_biaya) VALUES (?, ?, ?)",
                              (tgl_sekarang, f"Restok AI: {nama} ({qty} {satuan})", total_biaya))
                
                conn.commit()
                del st.session_state['ai_nota_result']
                st.success("Pengeluaran & Stok berhasil diperbarui!")
                st.rerun()

    st.divider()
    st.subheader("Riwayat Transaksi Penjualan")
    st.dataframe(df_trans, use_container_width=True)
