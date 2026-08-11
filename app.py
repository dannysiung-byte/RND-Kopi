import streamlit as st
import datetime
import pandas as pd
import sqlite3
import os

# Set judul halaman & layout
st.set_page_config(page_title="Kasir F&B POS", layout="wide", page_icon="☕")

# ---------------------------------------------------------
# DATABASE SETUP (SQLITE)
# ---------------------------------------------------------
DB_FILE = "pos_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS stok (
            id INTEGER PRIMARY KEY,
            susu INTEGER,
            kopi INTEGER,
            cup INTEGER
        )
    ''')
    c.execute('SELECT COUNT(*) FROM stok')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO stok (susu, kopi, cup) VALUES (1000, 500, 50)')
        
    c.execute('''
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            waktu TEXT,
            jam TEXT,
            metode TEXT,
            rincian TEXT,
            jumlah_item INTEGER,
            omzet INTEGER,
            hpp_biaya INTEGER,
            laba_bersih INTEGER
        )
    ''')
    
    conn.commit()
    conn.close()

def get_stok():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT susu, kopi, cup FROM stok WHERE id = 1')
    row = c.fetchone()
    conn.close()
    return {"susu": row[0], "kopi": row[1], "cup": row[2]}

def update_stok(susu, kopi, cup):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('UPDATE stok SET susu = ?, kopi = ?, cup = ? WHERE id = 1', (susu, kopi, cup))
    conn.commit()
    conn.close()

def simpan_transaksi(waktu, jam, metode, rincian, jumlah_item, omzet, hpp_biaya, laba_bersih):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transaksi (waktu, jam, metode, rincian, jumlah_item, omzet, hpp_biaya, laba_bersih)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (waktu, jam, metode, rincian, jumlah_item, omzet, hpp_biaya, laba_bersih))
    conn.commit()
    conn.close()

def load_transaksi():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query('SELECT * FROM transaksi ORDER BY id DESC', conn)
    conn.close()
    return df

init_db()

# ---------------------------------------------------------
# LOAD DATA MENU DARI FILE CSV
# ---------------------------------------------------------
@st.cache_data(ttl=60)
def load_menu_from_csv():
    if os.path.exists("menu_resep.csv"):
        df = pd.read_csv("menu_resep.csv")
        menu_dict = {}
        for _, row in df.iterrows():
            menu_dict[row['nama_menu']] = {
                "harga": int(row['harga_jual']),
                "susu": int(row['susu']),
                "kopi": int(row['kopi']),
                "cup": int(row['cup']),
                "foto": str(row['foto'])
            }
        return menu_dict
    else:
        return {
            "Kopi Susu": {"harga": 10000, "susu": 30, "kopi": 8, "cup": 1, "foto": "https://images.unsplash.com/photo-1517701604599-bb29b565090c?w=500&q=80"}
        }

DAFTAR_MENU = load_menu_from_csv()

# HPP ESTIMASI PER SATUAN
COST_SUSU_PER_GR = 25     # Rp 25 / gram (SKM)
COST_KOPI_PER_GRAM = 150  # Rp 150 / gram
COST_CUP_PER_PCS = 575    # Rp 575 / pcs

if 'keranjang' not in st.session_state:
    st.session_state.keranjang = []
if 'cart_counter' not in st.session_state:
    st.session_state.cart_counter = 0
if 'last_receipt' not in st.session_state:
    st.session_state.last_receipt = None

stok_db = get_stok()

TOPPING_LIST = {
    "Tanpa Tambahan": 0,
    "Extra Shot Espresso (+Rp 5.000)": 5000
}

# ---------------------------------------------------------
# HEADER APLIKASI
# ---------------------------------------------------------
df_tx_all = load_transaksi()
total_terjual_all = df_tx_all["jumlah_item"].sum() if not df_tx_all.empty else 0
total_omzet_all = df_tx_all["omzet"].sum() if not df_tx_all.empty else 0

st.title("☕ Aplikasi Kasir & Manajemen Stok F&B (CSV Resep Connected)")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("🥛 Stok Susu/SKM", f"{stok_db['susu']} gram")
col2.metric("🫘 Stok Biji Kopi", f"{stok_db['kopi']} gram")
col3.metric("🥤 Stok Cup Plastik", f"{stok_db['cup']} pcs")
col4.metric("🏆 Total Terjual", f"{total_terjual_all} Cangkir")
col5.metric("💰 Total Omzet", f"Rp {total_omzet_all:,}")

st.divider()

if stok_db['susu'] < 300:
    st.warning("⚠️ **ALERT:** Stok Susu kritis!")
if stok_db['kopi'] < 100:
    st.warning("⚠️ **ALERT:** Stok Biji Kopi kritis!")

# ---------------------------------------------------------
# TAB TAMPILAN
# ---------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🛒 Transaksi Penjualan", "📦 Restok Bahan Baku", "📊 Laporan & Analisa Owner"])

# === TAB 1: PENJUALAN ===
with tab1:
    col_kiri, col_kanan = st.columns([1.2, 1])
    
    with col_kiri:
        st.subheader("1. Pilih Minuman & Kustomisasi Varian")
        
        pilihan_menu = st.selectbox("Pilih Menu Base:", list(DAFTAR_MENU.keys()))
        data_base = DAFTAR_MENU[pilihan_menu]
        
        col_foto, col_opsi = st.columns([1, 1.2])
        
        with col_foto:
            st.image(data_base["foto"], use_container_width=True)
            st.info(f"💵 Harga Base: **Rp {data_base['harga']:,}**")
            
        with col_opsi:
            prefix_key = f"{pilihan_menu}_{st.session_state.cart_counter}"
            
            ukuran = st.radio(
                "Ukuran Cup:", 
                ["Medium (Normal)", "Large (+Rp 3.000)"], 
                horizontal=True,
                key=f"uk_{prefix_key}"
            )
            
            c_sug, c_ice = st.columns(2)
            sugar = c_sug.selectbox(
                "Sugar Level:", 
                ["Normal Sugar", "Less Sugar", "Extra Sugar", "No Sugar"],
                key=f"sug_{prefix_key}"
            )
            ice = c_ice.selectbox(
                "Ice Level:", 
                ["Normal Ice", "Less Ice", "Extra Ice", "No Ice"],
                key=f"ice_{prefix_key}"
            )
            
            topping = st.selectbox(
                "Opsi Kopi:", 
                list(TOPPING_LIST.keys()),
                key=f"top_{prefix_key}"
            )
            
            qty = st.number_input(
                "Jumlah Cangkir:", 
                min_value=1, 
                value=1,
                step=1,
                key=f"qty_{prefix_key}"
            )
            
            tambahan_ukuran = 3000 if "Large" in ukuran else 0
            tambahan_espresso = TOPPING_LIST[topping]
            
            kopi_extra_per_cup = 8 if tambahan_espresso > 0 else 0
            harga_final_satuan = data_base["harga"] + tambahan_ukuran + tambahan_espresso
            
            susu_req_unit = data_base["susu"]
            kopi_req_unit = data_base["kopi"] + kopi_extra_per_cup
            cup_req_unit = data_base["cup"]
            
            hpp_unit = (susu_req_unit * COST_SUSU_PER_GR) + (kopi_req_unit * COST_KOPI_PER_GRAM) + (cup_req_unit * COST_CUP_PER_PCS)
            
            if st.button("➕ Tambah Ke Keranjang", type="primary", use_container_width=True):
                label_espresso = " + Extra Shot" if tambahan_espresso > 0 else ""
                label_ukuran = " (Large)" if "Large" in ukuran else ""
                
                nama_item_lengkap = f"{pilihan_menu}{label_ukuran}{label_espresso}"
                detail_custom = f"{sugar}, {ice}"
                
                st.session_state.keranjang.append({
                    "nama_item": nama_item_lengkap,
                    "detail_custom": detail_custom,
                    "harga_satuan": harga_final_satuan,
                    "qty": qty,
                    "subtotal": harga_final_satuan * qty,
                    "hpp_total": hpp_unit * qty,
                    "susu_req": susu_req_unit * qty,
                    "kopi_req": kopi_req_unit * qty,
                    "cup_req": cup_req_unit * qty
                })
                
                st.session_state.cart_counter += 1
                st.toast(f"✅ {qty}x {nama_item_lengkap} ditambahkan!")
                st.rerun()

    with col_kanan:
        st.subheader("2. Keranjang & Pembayaran")
        if len(st.session_state.keranjang) == 0:
            st.info("Keranjang belanjaan kosong.")
            
            if st.session_state.last_receipt:
                st.divider()
                st.subheader("🧾 Struk Transaksi Terakhir")
                rc = st.session_state.last_receipt
                
                struk_text = "================================\n"
                struk_text += "         KOPI KITA POS          \n"
                struk_text += "     Jl. Niaga No. 123, Jakarta \n"
                struk_text += "================================\n"
                struk_text += f"Waktu : {rc['waktu']}\n"
                struk_text += "Kasir : Kasir 01\n"
                struk_text += "--------------------------------\n"
                
                for item in rc['items']:
                    struk_text += f"{item['nama_item']}\n"
                    struk_text += f"  {item['qty']} x Rp {item['harga_satuan']:,} = Rp {item['subtotal']:,}\n"
                
                struk_text += "--------------------------------\n"
                struk_text += f"TOTAL     : Rp {rc['total']:,}\n"
                struk_text += f"Metode    : {rc['metode']}\n"
                struk_text += f"Bayar     : Rp {rc['bayar']:,}\n"
                struk_text += f"Kembali   : Rp {rc['kembali']:,}\n"
                struk_text += "================================\n"
                struk_text += "   Terima Kasih Atas Kunjungannya! \n"
                struk_text += "================================\n"
                
                st.code(struk_text, language="text")
                st.download_button(
                    label="📥 Unduh Struk Digital (TXT)",
                    data=struk_text,
                    file_name=f"Struk_{rc['waktu'].replace(':', '-').replace(' ', '_')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
        else:
            total_bayar = 0
            total_susu = 0
            total_kopi = 0
            total_cup = 0
            
            for idx, item in enumerate(st.session_state.keranjang):
                total_bayar += item["subtotal"]
                total_susu += item["susu_req"]
                total_kopi += item["kopi_req"]
                total_cup += item["cup_req"]
                
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    st.write(f"**{item['nama_item']}**")
                    st.caption(f"⚙️ {item['detail_custom']} | Rp {item['harga_satuan']:,} x {item['qty']}")
                with c2:
                    st.write(f"**Rp {item['subtotal']:,}**")
                with c3:
                    if st.button("❌", key=f"del_{idx}"):
                        st.session_state.keranjang.pop(idx)
                        st.rerun()
                st.divider()
            
            st.markdown(f"### 💳 Total Tagihan: **Rp {total_bayar:,}**")
            
            st.markdown("---")
            st.subheader("💳 Metode Pembayaran")
            
            metode_bayar = st.radio(
                "Pilih Metode Pembayaran:",
                ["Tunai (Cash)", "QRIS / E-Wallet", "Kartu Debit/Kredit"],
                horizontal=True
            )
            
            uang_diterima = total_bayar
            kembalian = 0
            siap_bayar = True
            
            if metode_bayar == "Tunai (Cash)":
                uang_diterima = st.number_input(
                    "Jumlah Uang Diterima (Rp):", 
                    min_value=0, 
                    value=int(total_bayar), 
                    step=5000
                )
                kembalian = uang_diterima - total_bayar
                if kembalian < 0:
                    st.error(f"⚠️ Uang kurang Rp {abs(kembalian):,}")
                    siap_bayar = False
                else:
                    st.success(f"💵 Kembalian: **Rp {kembalian:,}**")
                    
            elif metode_bayar == "QRIS / E-Wallet":
                st.image("https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=https://kopi-pos.id", width=180)
                st.caption("📱 Silakan scan QRIS di atas untuk menyelesaikan pembayaran.")
                
            elif metode_bayar == "Kartu Debit/Kredit":
                st.info("💳 Silakan geser / tap kartu pada mesin EDC.")
            
            col_bt1, col_bt2 = st.columns(2)
            with col_bt1:
                if st.button("✅ Selesaikan & Cetak Struk", type="primary", use_container_width=True, disabled=not siap_bayar):
                    if total_susu > stok_db['susu']:
                        st.error("❌ Transaksi Gagal! Stok Susu kurang.")
                    elif total_kopi > stok_db['kopi']:
                        st.error("❌ Transaksi Gagal! Stok Kopi kurang.")
                    elif total_cup > stok_db['cup']:
                        st.error("❌ Transaksi Gagal! Stok Cup kurang.")
                    else:
                        susu_baru = stok_db['susu'] - total_susu
                        kopi_baru = stok_db['kopi'] - total_kopi
                        cup_baru = stok_db['cup'] - total_cup
                        update_stok(susu_baru, kopi_baru, cup_baru)
                        
                        total_cangkir = sum([it["qty"] for it in st.session_state.keranjang])
                        total_hpp_transaksi = sum([it["hpp_total"] for it in st.session_state.keranjang])
                        laba_bersih = total_bayar - total_hpp_transaksi
                        
                        dt_now = datetime.datetime.now()
                        waktu_sekarang = dt_now.strftime("%Y-%m-%d %H:%M:%S")
                        jam_sekarang = dt_now.strftime("%H:00")
                        rincian_teks = ", ".join([f"{it['qty']}x {it['nama_item']}" for it in st.session_state.keranjang])
                        
                        simpan_transaksi(
                            waktu_sekarang,
                            jam_sekarang,
                            metode_bayar,
                            rincian_teks,
                            total_cangkir,
                            total_bayar,
                            total_hpp_transaksi,
                            laba_bersih
                        )
                        
                        st.session_state.last_receipt = {
                            "waktu": waktu_sekarang,
                            "items": st.session_state.keranjang.copy(),
                            "total": total_bayar,
                            "metode": metode_bayar,
                            "bayar": uang_diterima,
                            "kembali": kembalian
                        }
                        
                        st.session_state.keranjang = []
                        st.balloons()
                        st.success("🎉 Transaksi Berhasil Diproses & Tersimpan di Database!")
                        st.rerun()
            
            with col_bt2:
                if st.button("🗑️ Batal / Kosongkan", use_container_width=True):
                    st.session_state.keranjang = []
                    st.rerun()

# === TAB 2: RESTOK ===
with tab2:
    st.subheader("Form Restok Gudang (Tersimpan Permanen)")
    ts = st.number_input("Tambah Susu (gram):", min_value=0, value=0, step=100)
    tk = st.number_input("Tambah Kopi (gram):", min_value=0, value=0, step=50)
    tcp = st.number_input("Tambah Cup (pcs):", min_value=0, value=0, step=10)
    
    if st.button("📥 Update Stok Gudang"):
        susu_update = stok_db['susu'] + ts
        kopi_update = stok_db['kopi'] + tk
        cup_update = stok_db['cup'] + tcp
        
        update_stok(susu_update, kopi_update, cup_update)
        st.success("Stok berhasil diperbarui di database!")
        st.rerun()

# === TAB 3: LAPORAN ANALISA OWNER ===
with tab3:
    st.subheader("📊 Executive Dashboard - Analisa Finansial Owner (SQLite Data)")
    
    df_transaksi = load_transaksi()
    
    if df_transaksi.empty:
        st.info("Belum ada data penjualan tersimpan di database.")
    else:
        total_omzet = df_transaksi["omzet"].sum()
        total_hpp = df_transaksi["hpp_biaya"].sum()
        total_laba = df_transaksi["laba_bersih"].sum()
        margin_laba = (total_laba / total_omzet * 100) if total_omzet > 0 else 0
        
        c_kpi1, c_kpi2, c_kpi3, c_kpi4 = st.columns(4)
        c_kpi1.metric("💵 Total Pendapatan (Omzet)", f"Rp {total_omzet:,}")
        c_kpi2.metric("📦 Total HPP (Cost Bahan)", f"Rp {total_hpp:,}")
        c_kpi3.metric("📈 Total Laba Bersih", f"Rp {total_laba:,}")
        c_kpi4.metric("📊 Profit Margin", f"{margin_laba:.1f}%")
        
        st.divider()
        
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.markdown("### 📈 Ringkasan Tren Omzet & Laba Bersih")
            df_ringkas = df_transaksi[["waktu", "jumlah_item", "omzet", "laba_bersih"]]
            st.dataframe(
                df_ringkas,
                column_config={
                    "waktu": "Waktu Transaksi",
                    "jumlah_item": "Cangkir",
                    "omzet": st.column_config.NumberColumn("Omzet", format="Rp %d"),
                    "laba_bersih": st.column_config.NumberColumn("Laba Bersih", format="Rp %d")
                },
                use_container_width=True,
                hide_index=True
            )
            
        with col_g2:
            st.markdown("### ⏰ Analisis Peak Hours (Jam Sibuk Penjualan)")
            df_peak = df_transaksi.groupby("jam")["jumlah_item"].sum().reset_index()
            st.dataframe(
                df_peak,
                column_config={
                    "jam": "Jam Operasional",
                    "jumlah_item": st.column_config.ProgressColumn(
                        "Total Cup Terjual",
                        format="%d Cup",
                        min_value=0,
                        max_value=int(df_peak["jumlah_item"].max() or 10)
                    ),
                },
                use_container_width=True,
                hide_index=True
            )
            
        st.divider()
        
        st.markdown("### 💳 Metode Pembayaran Populer")
        df_pay = df_transaksi.groupby("metode")["omzet"].sum().reset_index()
        st.dataframe(
            df_pay,
            column_config={
                "metode": "Metode Pembayaran",
                "omzet": st.column_config.NumberColumn("Total Omzet", format="Rp %d")
            },
            use_container_width=True,
            hide_index=True
        )
            
        st.divider()
        
        c_head1, c_head2 = st.columns([3, 1])
        with c_head1:
            st.markdown("### 📋 Jurnal / Buku Kas Penjualan Lengkap")
        with c_head2:
            csv_data = df_transaksi.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Excel/CSV",
                data=csv_data,
                file_name=f"Laporan_Penjualan_SQLite_{datetime.datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
        st.dataframe(df_transaksi, use_container_width=True, hide_index=True)
