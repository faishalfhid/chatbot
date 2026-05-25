"""
Step 2: Text-to-SQL agent untuk tabel vtiger_service.

Konteks: Bisnis pelatihan IT, 121 program pelatihan di vtiger_service.

Alur:
  User: "Berapa harga training CCNA?"
  → LLM bikin SQL
  → Eksekusi ke MySQL
  → LLM format hasil jadi jawaban natural

Jalankan: python text_to_sql.py
"""
import os
import re
import sys
from urllib.parse import quote_plus

from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy import create_engine



# ============================================================
# Setup
# ============================================================
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not all([DB_HOST, DB_USER, DB_PASS, DB_NAME, GROQ_API_KEY]):
    print("[ERROR] Konfigurasi belum lengkap di .env")
    print("        Pastikan DB_* dan GROQ_API_KEY sudah diisi.")
    sys.exit(1)

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASS)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ============================================================
# 1. Koneksi ke DB, batasi tabel yang dilihat LLM
# ============================================================
# include_tables PENTING: tanpa ini, LLM melihat 200+ tabel Vtiger
# dan jadi bingung / generate SQL aneh. Ini juga lebih hemat token.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # auto-reconnect kalau koneksi mati
    pool_recycle=1800,    # recycle koneksi tiap 30 menit
)

db = SQLDatabase(
    engine,
    include_tables=["vtiger_service", "vtiger_crmentity"],
    sample_rows_in_table_info=3,
)

print("[OK] Connected.")
print(f"     Tabel yang dilihat agent: {db.get_usable_table_names()}")
print()


# ============================================================
# 2. LLM (gpt-oss-20b via Groq)
# ============================================================
llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,                     # deterministik untuk SQL generation
    api_key=GROQ_API_KEY,
    reasoning_effort="low",   # cepat & murah
)


# ============================================================
# 3. Prompt: ubah pertanyaan → SQL
# ============================================================
SQL_GENERATION_PROMPT = ChatPromptTemplate.from_template("""\
Anda adalah ahli SQL untuk database MySQL milik Inixindo (penyedia pelatihan IT).

KONTEKS BISNIS PENTING:
- Database ini adalah katalog pelatihan internal Inixindo.
- SEMUA data di tabel vtiger_service adalah milik / diselenggarakan oleh Inixindo.
- Karena itu, kata "Inixindo", "di Inixindo", "Inixindo punya", "training Inixindo"
  yang muncul di pertanyaan user adalah KONTEKS, BUKAN kriteria pencarian.
  JANGAN PERNAH menambahkan filter LIKE '%inixindo%' pada kolom apapun.

Schema database yang tersedia:
{schema}

Catatan kolom:
- vtiger_service.servicename : nama pelatihan/program (gunakan ini untuk pencarian topik/judul).
- vtiger_service.unit_price  : harga pelatihan.
- vtiger_crmentity.label     : label entitas (biasanya mirror dari servicename),
                               BUKAN nama vendor/penyedia. Jangan dipakai untuk filter nama perusahaan.
- vtiger_crmentity.deleted   : flag soft-delete (0 = aktif, 1 = dihapus).

ATURAN:
1. Tulis HANYA query SELECT. DILARANG INSERT/UPDATE/DELETE/DROP/ALTER.
2. Gunakan hanya tabel & kolom dari schema di atas.
3. Untuk pencarian nama pelatihan, gunakan vtiger_service.servicename LIKE '%kata%'.
4. WAJIB selalu JOIN vtiger_crmentity ON vtiger_crmentity.crmid = vtiger_service.serviceid
   dan tambahkan WHERE vtiger_crmentity.deleted = 0.
5. Batasi LIMIT 20 kecuali user minta lebih banyak.
6. Output HANYA query SQL mentah, tanpa ```sql```, tanpa penjelasan apapun.
                                                         
PENTING - GAP BAHASA INDONESIA vs ENGLISH TEKNIS:
Nama pelatihan di kolom servicename SELALU dalam Bahasa Inggris dengan istilah teknis
(contoh nyata: "Implementing and Administering Cisco Solutions (CCNA)",
"Certified Information Systems Security Professional (CISSP)").

Pertanyaan user biasanya pakai kata umum Bahasa Indonesia. Anda HARUS menerjemahkan
kata umum tersebut ke beberapa istilah teknis Inggris yang relevan, lalu gabungkan
dengan OR di WHERE. Pemetaan acuan (gunakan istilah ini dan istilah serupa lainnya):

- "jaringan" / "networking"     → CCNA, CCNP, network, networking, Cisco, routing, switching
- "keamanan" / "cyber security" → security, CISSP, CEH, ethical hacking, pentest, firewall, SOC
- "basis data" / "database"     → database, SQL, MySQL, Oracle, PostgreSQL, MongoDB
- "cloud" / "komputasi awan"    → cloud, AWS, Azure, GCP, kubernetes, OpenStack
- "data" / "analitik"           → data, analytics, big data, Power BI, Tableau, machine learning, AI
- "pemrograman" / "coding"      → programming, Python, Java, JavaScript, .NET, web development
- "tata kelola" / "governance"  → governance, COBIT, ITIL, audit, compliance, ISO
- "DevOps" / "operasional"      → DevOps, Docker, Kubernetes, CI/CD, Jenkins, Ansible

Kalau topiknya tidak ada di daftar di atas, gunakan pengetahuan Anda sendiri untuk
mendaftar 3-6 istilah teknis Inggris yang relevan dan pakai OR.

Contoh:

User: "Apakah ada pelatihan CCNA di Inixindo?"
SQL: SELECT s.serviceid, s.servicename, s.unit_price
     FROM vtiger_service s
     JOIN vtiger_crmentity c ON c.crmid = s.serviceid
     WHERE c.deleted = 0 AND s.servicename LIKE '%CCNA%'
     LIMIT 20

User: "Training Inixindo soal cloud apa saja?"
SQL: SELECT s.serviceid, s.servicename, s.unit_price
     FROM vtiger_service s
     JOIN vtiger_crmentity c ON c.crmid = s.serviceid
     WHERE c.deleted = 0 AND s.servicename LIKE '%cloud%'
     LIMIT 20

User: "Berapa harga kelas CCNA?"
SQL: SELECT s.serviceid, s.servicename, s.unit_price
     FROM vtiger_service s
     JOIN vtiger_crmentity c ON c.crmid = s.serviceid
     WHERE c.deleted = 0 AND s.servicename LIKE '%CCNA%'
     LIMIT 20

User: "Apakah ada pelatihan jaringan di Inixindo?"
SQL: SELECT s.serviceid, s.servicename, s.unit_price
     FROM vtiger_service s
     JOIN vtiger_crmentity c ON c.crmid = s.serviceid
     WHERE c.deleted = 0
       AND (s.servicename LIKE '%CCNA%'
            OR s.servicename LIKE '%CCNP%'
            OR s.servicename LIKE '%network%'
            OR s.servicename LIKE '%Cisco%'
            OR s.servicename LIKE '%routing%'
            OR s.servicename LIKE '%switching%')
     LIMIT 20

User: "Pelatihan tentang keamanan informasi apa saja?"
SQL: SELECT s.serviceid, s.servicename, s.unit_price
     FROM vtiger_service s
     JOIN vtiger_crmentity c ON c.crmid = s.serviceid
     WHERE c.deleted = 0
       AND (s.servicename LIKE '%security%'
            OR s.servicename LIKE '%CISSP%'
            OR s.servicename LIKE '%CEH%'
            OR s.servicename LIKE '%firewall%'
            OR s.servicename LIKE '%ethical%')
     LIMIT 20

Pertanyaan user: {question}

SQL:""")


# ============================================================
# 4. Prompt: ubah hasil SQL → jawaban natural
# ============================================================
ANSWER_PROMPT = ChatPromptTemplate.from_template("""\
Anda adalah asisten customer service penyedia pelatihan IT yang ramah.

Pertanyaan user: {question}
Query yang dijalankan: {query}
Hasil query: {result}

Berikan jawaban dalam Bahasa Indonesia. Aturan:
- Format harga sebagai Rupiah (contoh: Rp 7.500.000).
- Jika hasil kosong, katakan dengan sopan bahwa data tidak ditemukan.
- Singkat dan to-the-point, maksimal 3-4 kalimat.
- JANGAN tampilkan ID internal atau detail teknis ke user.
- JANGAN mengarang informasi yang tidak ada di hasil query.

Jawaban:""")


# ============================================================
# 5. Utility: bersihkan & validasi SQL
# ============================================================
def clean_sql(text: str) -> str:
    """Hapus markdown fence dan prefix yang kadang dihasilkan LLM."""
    text = text.strip()
    # Hapus ```sql ... ``` fence kalau ada
    fence = re.search(r"```(?:sql)?\s*(.+?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    # Hapus prefix "SQL:" yang kadang muncul
    text = re.sub(r"^sql\s*:\s*", "", text.strip(), flags=re.IGNORECASE)
    return text.strip().rstrip(";")


def is_safe_sql(sql: str) -> bool:
    """Pastikan query hanya SELECT, tanpa keyword berbahaya."""
    cleaned = sql.strip().lower()
    if not cleaned.startswith("select"):
        return False
    danger = ["insert ", "update ", "delete ", "drop ", "alter ",
              "truncate ", "grant ", "revoke ", "create "]
    return not any(kw in cleaned for kw in danger)


# ============================================================
# 6. Chain
# ============================================================
schema_info = db.get_table_info()
sql_chain = SQL_GENERATION_PROMPT | llm | StrOutputParser()
answer_chain = ANSWER_PROMPT | llm | StrOutputParser()


def ask(question: str) -> None:
    raw = sql_chain.invoke({"schema": schema_info, "question": question})
    sql = clean_sql(raw)
    print(f"  [SQL]    {sql}")

    if not is_safe_sql(sql):
        print("  [BLOCK]  Query ditolak: bukan SELECT atau ada keyword berbahaya.")
        return

    try:
        result = db.run(sql)
    except Exception as e:
        print(f"  [DB ERR] {e}")
        return

    # --- FALLBACK: kalau kosong, minta LLM longgarkan filter ---
    if not result or result.strip() in ("", "[]"):
        print("  [RETRY]  Hasil kosong, mencoba dengan kata kunci lebih luas...")
        retry_question = (
            f"{question}\n\n"
            f"Query sebelumnya ({sql}) menghasilkan 0 baris. "
            f"Tolong tulis ulang dengan kata kunci yang lebih luas atau "
            f"sinonim teknis tambahan (multiple LIKE digabung OR)."
        )
        raw = sql_chain.invoke({"schema": schema_info, "question": retry_question})
        sql = clean_sql(raw)
        print(f"  [SQL2]   {sql}")
        if is_safe_sql(sql):
            try:
                result = db.run(sql)
            except Exception as e:
                print(f"  [DB ERR] {e}")
                return

    display_result = result if len(result) <= 200 else result[:200] + "..."
    print(f"  [HASIL]  {display_result}")

    answer = answer_chain.invoke({
        "question": question,
        "query": sql,
        "result": result,
    })
    print(f"\nBot: {answer}")

def ask_return(question: str) -> str:
    """Versi ask() yang return jawaban sebagai string (untuk API/bot)."""

    raw = sql_chain.invoke({"schema": schema_info, "question": question})
    sql = clean_sql(raw)

    if not is_safe_sql(sql):
        return "⚠️ Query tidak aman, permintaan ditolak."

    try:
        result = db.run(sql)
    except Exception as e:
        return f"❌ Gagal mengambil data: {e}"

    answer = answer_chain.invoke({
        "question": question,
        "query": sql,
        "result": result,
    })
    return answer


# ============================================================
# 7. Loop interaktif
# ============================================================
def main():
    print("=" * 60)
    print("Text-to-SQL Agent | Pelatihan IT")
    print("-" * 60)
    print("Contoh pertanyaan:")
    print("  - Berapa harga training CCNA?")
    print("  - Pelatihan apa saja di kategori Authorized Inixindo?")
    print("  - Ada training tentang IT governance?")
    print("  - Total pelatihan yang tersedia berapa?")
    print("  - Training dengan harga di bawah 10 juta apa saja?")
    print()
    print("Ketik 'keluar' untuk berhenti.")
    print("=" * 60)

    while True:
        try:
            q = input("\nAnda: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break

        if not q:
            continue
        if q.lower() in {"keluar", "exit", "quit"}:
            print("Bye.")
            break

        try:
            ask(q)
        except Exception as e:
            print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
