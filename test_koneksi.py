"""
Step 1: Test koneksi ke MySQL database cPanel.

Tujuan:
  1. Pastikan Python bisa terhubung ke database
  2. Validasi credential di .env benar
  3. Tampilkan daftar tabel & strukturnya (untuk persiapan step berikutnya)

Jalankan: python test_koneksi.py
"""
import os
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError, SQLAlchemyError


def main():
    # ---- 1. Load credentials dari .env ----
    load_dotenv()

    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER")
    DB_PASS = os.getenv("DB_PASS")
    DB_NAME = os.getenv("DB_NAME")

    # Validasi: pastikan semua variabel ada
    missing = [
        name for name, val in {
            "DB_HOST": DB_HOST,
            "DB_USER": DB_USER,
            "DB_PASS": DB_PASS,
            "DB_NAME": DB_NAME,
        }.items() if not val
    ]
    if missing:
        print(f"[ERROR] Konfigurasi belum lengkap di .env: {', '.join(missing)}")
        print("        Salin .env.example ke .env, lalu isi credential-nya.")
        sys.exit(1)

    # ---- 2. Bangun connection URL ----
    # quote_plus penting kalau password mengandung karakter spesial (@ # / dll)
    password_encoded = quote_plus(DB_PASS)
    DATABASE_URL = (
        f"mysql+pymysql://{DB_USER}:{password_encoded}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    print(f"Mencoba koneksi ke {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
    print()

    # ---- 3. Coba terhubung ----
    try:
        # pool_pre_ping mengecek koneksi sebelum dipakai (anti idle disconnect)
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)

        with engine.connect() as conn:
            # Test query paling dasar
            version = conn.execute(text("SELECT VERSION()")).scalar()
            print(f"[OK] Berhasil terhubung. Versi MySQL: {version}")
            print()

            # ---- 4. Inspect struktur database ----
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            if not tables:
                print("[INFO] Database ini belum ada tabelnya.")
                return

            print(f"Ditemukan {len(tables)} tabel di database '{DB_NAME}':")
            print("-" * 60)

            for table_name in tables:
                # Hitung jumlah baris
                try:
                    row_count = conn.execute(
                        text(f"SELECT COUNT(*) FROM `{table_name}`")
                    ).scalar()
                except Exception:
                    row_count = "?"

                # Ambil daftar kolom
                columns = inspector.get_columns(table_name)
                col_summary = ", ".join(
                    f"{c['name']} ({c['type']})" for c in columns
                )

                print(f"\nTabel: {table_name}  ({row_count} baris)")
                print(f"  Kolom: {col_summary}")

            print()
            print("-" * 60)
            print("[OK] Test selesai. Database siap dipakai untuk step berikutnya.")

    except OperationalError as e:
        err_str = str(e)
        print("[ERROR] Gagal terhubung ke database.")
        print()

        if "1045" in err_str or "Access denied" in err_str:
            print("  Penyebab: username atau password salah.")
            print("  Cek di cPanel → MySQL Databases:")
            print("  - Username biasanya berformat: cpaneluser_namauser")
            print("  - Pastikan password tidak ada typo")

        elif "2003" in err_str or "Can't connect" in err_str:
            print("  Penyebab: tidak bisa mencapai server MySQL.")
            print("  Kemungkinan besar IP Anda belum di-whitelist.")
            print("  Solusi:")
            print("  1. Cek IP publik Anda di https://whatismyip.com")
            print("  2. Login cPanel → menu 'Remote MySQL'")
            print("  3. Tambahkan IP tersebut ke daftar 'Allowed Hosts'")

        elif "Unknown database" in err_str:
            print(f"  Penyebab: database '{DB_NAME}' tidak ditemukan.")
            print("  Cek nama lengkap di cPanel → MySQL Databases.")
            print("  Formatnya biasanya: cpaneluser_namadb")

        elif "Unknown MySQL server host" in err_str:
            print(f"  Penyebab: host '{DB_HOST}' tidak ditemukan.")
            print("  Coba ganti DB_HOST ke:")
            print("  - Nama domain Anda (tanpa http://)")
            print("  - Atau hostname server hosting (cek di email aktivasi)")

        else:
            print(f"  Detail: {err_str[:400]}")

        sys.exit(1)

    except SQLAlchemyError as e:
        print(f"[ERROR] SQLAlchemy error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
