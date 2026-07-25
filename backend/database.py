import datetime
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# Determine Database URL
# Default to SQLite for local development, support PostgreSQL via environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./store_keyra.db")

# If using PostgreSQL, verify driver
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Connect options (check_same_thread is only needed for SQLite)
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=True)

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, unique=True, index=True)
    slug = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    # Auto-inject ke Markastools: "weavy" | "framia" | "roboneo".
    # Kosong / NULL berarti produk dikirim manual (hanya file .txt seperti biasa).
    inject_provider = Column(String, nullable=True)
    inject_recipe_id = Column(String, nullable=True)  # opsional, hanya dipakai Weavy
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    category = relationship("Category", back_populates="products")
    items = relationship("ProductItem", back_populates="product", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="product")

class ProductItem(Base):
    __tablename__ = "product_items"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    content = Column(String, nullable=False) # Store the actual token / account data
    is_sold = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    sold_at = Column(DateTime, nullable=True)

    product = relationship("Product", back_populates="items")
    transaction = relationship("Transaction", back_populates="product_item")

class Transaction(Base):
    __tablename__ = "transactions"
    order_id = Column(String, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, index=True)
    telegram_username = Column(String, nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    product_item_id = Column(Integer, ForeignKey("product_items.id"), nullable=True)
    amount = Column(Float, nullable=False)
    fee = Column(Float, default=0.0)
    total_payment = Column(Float, nullable=False)
    payment_method = Column(String, nullable=True)
    status = Column(String, default="pending", index=True) # pending, completed, cancelled, expired
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    invoice_msg_id = Column(Integer, nullable=True)
    # Email akun Markastools milik pembeli (diisi saat checkout produk auto-inject)
    buyer_email = Column(String, nullable=True)
    # Status auto-inject: pending, success, partial, failed
    inject_status = Column(String, nullable=True)
    inject_detail = Column(String, nullable=True)
    # Isi stok yang dikirim ke pembeli (satu item per baris), dipakai untuk retry inject
    delivered_content = Column(String, nullable=True)

    product = relationship("Product", back_populates="transactions")
    product_item = relationship("ProductItem", back_populates="transaction")

class TelegramUser(Base):
    __tablename__ = "telegram_users"
    id = Column(BigInteger, primary_key=True, index=True) # Telegram User ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Kolom yang wajib ada setelah migrasi berjalan. Dipakai untuk memverifikasi
# hasil migrasi saat boot (lihat verify_schema) supaya kegagalan ALTER TABLE
# terlihat jelas di log deploy, bukan muncul sebagai error 500 saat dipakai.
REQUIRED_COLUMNS = {
    "products": ["inject_provider", "inject_recipe_id"],
    "transactions": ["invoice_msg_id", "buyer_email", "inject_status", "inject_detail", "delivered_content"],
}


def verify_schema() -> list:
    """Pastikan kolom hasil migrasi benar-benar ada. Mengembalikan daftar kolom
    yang masih hilang (kosong berarti skema sudah lengkap)."""
    from sqlalchemy import inspect

    missing = []
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table, columns in REQUIRED_COLUMNS.items():
            if table not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table)}
            missing.extend(f"{table}.{col}" for col in columns if col not in existing)
    except Exception as e:
        print(f"Schema check gagal dijalankan: {e}")
        return []

    if missing:
        print(
            "!!! SCHEMA WARNING: kolom berikut belum ada di database -> "
            + ", ".join(missing)
            + ". Fitur auto-inject Markastools akan error sampai kolom ini dibuat."
        )
    else:
        print("Schema check OK: semua kolom yang dibutuhkan tersedia.")
    return missing


def run_migrations():
    """
    Run manual SQL migrations for schema changes that SQLAlchemy's create_all
    won't apply automatically (e.g., changing column types on existing tables).
    """
    is_postgres = DATABASE_URL.startswith("postgresql")

    # PostgreSQL mendukung ADD COLUMN IF NOT EXISTS sehingga deploy berulang tidak
    # memicu error sama sekali. SQLite belum mendukungnya, jadi errornya ditangkap
    # dan dianggap "sudah pernah dijalankan".
    add_column = "ADD COLUMN IF NOT EXISTS" if is_postgres else "ADD COLUMN"

    migrations = []
    if is_postgres:
        migrations.extend([
            # Fix: Telegram User IDs are 64-bit, must be BIGINT not INT
            "ALTER TABLE telegram_users ALTER COLUMN id TYPE BIGINT",
            "ALTER TABLE transactions ALTER COLUMN telegram_user_id TYPE BIGINT",
        ])

    migrations.extend([
        f"ALTER TABLE transactions {add_column} invoice_msg_id INTEGER",
        # Integrasi auto-inject Markastools
        f"ALTER TABLE products {add_column} inject_provider VARCHAR",
        f"ALTER TABLE products {add_column} inject_recipe_id VARCHAR",
        f"ALTER TABLE transactions {add_column} buyer_email VARCHAR",
        f"ALTER TABLE transactions {add_column} inject_status VARCHAR",
        f"ALTER TABLE transactions {add_column} inject_detail VARCHAR",
        f"ALTER TABLE transactions {add_column} delivered_content VARCHAR",
    ])

    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
                conn.commit()
                print(f"Migration applied: {sql}")
            except Exception as e:
                # Column may already exist — safe to ignore
                conn.rollback()
                print(f"Migration skipped (already done or not needed): {e}")

    # Laporkan hasilnya supaya ketahuan di log Railway bila ada yang gagal
    verify_schema()


def init_db():
    Base.metadata.create_all(bind=engine)
    run_migrations()

    # Initialize default settings if not exists
    db = SessionLocal()
    try:
        defaults = {
            "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "pakasir_slug": os.getenv("PAKASIR_SLUG", ""),
            "pakasir_api_key": os.getenv("PAKASIR_API_KEY", ""),
            "admin_username": os.getenv("ADMIN_USERNAME", "admin"),
            "admin_password": os.getenv("ADMIN_PASSWORD", "admin123"), # Simple login password
            "bot_welcome_msg": "Selamat datang di StoreKeyra Bot! 🛍️\nSilakan pilih menu di bawah ini untuk memulai belanja produk digital premium, token, dan lainnya.",
            "bot_contact_admin": "@KeyraAdmin",
            "bot_active": "true",
            "bot_product_note": "⚠️ *PENTING SEBELUM BELI!* ⚠️\nSemua akun dipastikan aktif saat dibeli. Garansi klaim hanya berlaku 10 menit sejak transaksi (hubungi admin jika ada kendala). Lewat 10 menit, komplain tidak diterima. TIDAK ADA GARANSI PEMAKAIAN — harap beli seperlunya dan langsung digunakan. Membeli berarti setuju & paham konsekuensinya."
        }
        for key, value in defaults.items():
            setting = db.query(Setting).filter(Setting.key == key).first()
            if not setting:
                db.add(Setting(key=key, value=value))
        db.commit()
    except Exception as e:
        print(f"Error initializing DB settings: {e}")
        db.rollback()
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
