import datetime
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey
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
    telegram_user_id = Column(Integer, index=True)
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

    product = relationship("Product", back_populates="transactions")
    product_item = relationship("ProductItem", back_populates="transaction")

def init_db():
    Base.metadata.create_all(bind=engine)
    
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
            "bot_active": "true"
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
