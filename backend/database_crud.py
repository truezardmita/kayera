from sqlalchemy.orm import Session
from datetime import datetime
from .database import Category, Product, ProductItem, Transaction, Setting
import string
import random

# Setting helpers
def get_setting(db: Session, key: str) -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else ""

def get_all_settings(db: Session):
    return {s.key: s.value for s in db.query(Setting).all()}

def set_setting(db: Session, key: str, value: str):
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
    db.commit()
    return setting

# Category helpers
def get_categories(db: Session):
    return db.query(Category).all()

def get_category_by_id(db: Session, cat_id: int):
    return db.query(Category).filter(Category.id == cat_id).first()

def get_category_by_slug(db: Session, slug: str):
    return db.query(Category).filter(Category.slug == slug).first()

def create_category(db: Session, name: str, slug: str):
    category = Category(name=name, slug=slug)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category

def delete_category(db: Session, cat_id: int):
    category = get_category_by_id(db, cat_id)
    if category:
        db.delete(category)
        db.commit()
        return True
    return False

# Product helpers
def get_products(db: Session, category_id: int = None, active_only: bool = False):
    query = db.query(Product)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if active_only:
        query = query.filter(Product.is_active == True)
    return query.all()

def get_product_by_id(db: Session, prod_id: int):
    return db.query(Product).filter(Product.id == prod_id).first()

def create_product(db: Session, category_id: int, name: str, description: str, price: float, is_active: bool = True):
    product = Product(category_id=category_id, name=name, description=description, price=price, is_active=is_active)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product

def update_product(db: Session, prod_id: int, name: str, description: str, price: float, is_active: bool):
    product = get_product_by_id(db, prod_id)
    if product:
        product.name = name
        product.description = description
        product.price = price
        product.is_active = is_active
        db.commit()
        db.refresh(product)
    return product

def delete_product(db: Session, prod_id: int):
    product = get_product_by_id(db, prod_id)
    if product:
        db.delete(product)
        db.commit()
        return True
    return False

# ProductItem (Stock) helpers
def add_stock(db: Session, product_id: int, items: list[str]):
    added_items = []
    for item_content in items:
        cleaned_content = item_content.strip()
        if cleaned_content:
            pi = ProductItem(product_id=product_id, content=cleaned_content, is_sold=False)
            db.add(pi)
            added_items.append(pi)
    db.commit()
    return added_items

def get_available_stock_count(db: Session, product_id: int) -> int:
    return db.query(ProductItem).filter(ProductItem.product_id == product_id, ProductItem.is_sold == False).count()

def get_stock_items(db: Session, product_id: int):
    return db.query(ProductItem).filter(ProductItem.product_id == product_id).all()

def get_unsold_items(db: Session, product_id: int):
    return db.query(ProductItem).filter(ProductItem.product_id == product_id, ProductItem.is_sold == False).all()

def delete_stock_item(db: Session, item_id: int):
    item = db.query(ProductItem).filter(ProductItem.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
        return True
    return False

# Transaction helpers
def create_transaction(db: Session, telegram_user_id: int, telegram_username: str, product_id: int, amount: float, fee: float, total_payment: float, payment_method: str, order_id: str = None) -> Transaction:
    if not order_id:
        # Generate random unique ID
        timestamp = datetime.now().strftime("%y%m%d%H%M")
        random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        order_id = f"INV{timestamp}{random_str}"
        
    tx = Transaction(
        order_id=order_id,
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        product_id=product_id,
        amount=amount,
        fee=fee,
        total_payment=total_payment,
        payment_method=payment_method,
        status="pending"
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx

def get_transaction_by_id(db: Session, order_id: str) -> Transaction:
    return db.query(Transaction).filter(Transaction.order_id == order_id).first()

def get_transactions(db: Session):
    return db.query(Transaction).order_by(Transaction.created_at.desc()).all()

def complete_transaction(db: Session, order_id: str) -> Transaction:
    tx = get_transaction_by_id(db, order_id)
    if tx and tx.status == "pending":
        # Find one unsold item for the product
        unsold_item = db.query(ProductItem).filter(ProductItem.product_id == tx.product_id, ProductItem.is_sold == False).first()
        if unsold_item:
            unsold_item.is_sold = True
            unsold_item.sold_at = datetime.utcnow()
            tx.product_item_id = unsold_item.id
            tx.status = "completed"
            tx.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(tx)
            return tx, unsold_item.content
        else:
            # Paid but stock runs out! Mark completed but with empty product_item (requires admin intervention)
            tx.status = "completed"
            tx.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(tx)
            return tx, None
    return tx, None

def cancel_transaction(db: Session, order_id: str) -> Transaction:
    tx = get_transaction_by_id(db, order_id)
    if tx and tx.status == "pending":
        tx.status = "cancelled"
        db.commit()
        db.refresh(tx)
    return tx
