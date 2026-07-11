import os
import logging
import asyncio
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import init_db, get_db, SessionLocal
from backend import database_crud
from backend.bot import create_bot_app, notify_user_payment_success
from backend.pakasir import simulate_pakasir_payment

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Secret for stateless authentication tokens
SECRET_KEY = "keyra_store_dashboard_secret_key"

# Global Telegram Bot State
bot_app = None

# FastAPI Lifespan Handler
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_app
    # Initialize DB
    logger.info("Initializing database...")
    init_db()

    # Load bot token and start bot
    db = SessionLocal()
    try:
        bot_token = database_crud.get_setting(db, "telegram_bot_token")
        bot_active = database_crud.get_setting(db, "bot_active") == "true"
        if bot_token and bot_active:
            logger.info("Starting Telegram Bot...")
            bot_app = create_bot_app(bot_token)
            await bot_app.initialize()
            await bot_app.start()
            await bot_app.updater.start_polling()
            logger.info("Telegram Bot started.")
        else:
            logger.warning("Telegram Bot token is empty or bot is inactive. Bot will not start on boot.")
    except Exception as e:
        logger.exception(f"Error starting Telegram Bot on boot: {e}")
    finally:
        db.close()

    yield

    # Clean up Telegram Bot
    if bot_app:
        logger.info("Stopping Telegram Bot...")
        try:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
            logger.info("Telegram Bot stopped.")
        except Exception as e:
            logger.error(f"Error stopping Telegram Bot: {e}")

app = FastAPI(title="StoreKeyra API", lifespan=lifespan)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication Helpers
def generate_token(username: str) -> str:
    timestamp = str(int(datetime.utcnow().timestamp()))
    payload = f"{username}:{timestamp}"
    signature = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_admin_token(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format")
    
    token = authorization.split(" ")[1]
    try:
        parts = token.split(":")
        if len(parts) != 3:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
        
        username, timestamp, signature = parts
        
        # Verify age (e.g., 7 days)
        if int(datetime.utcnow().timestamp()) - int(timestamp) > 7 * 24 * 3600:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
            
        # Verify signature
        payload = f"{username}:{timestamp}"
        expected_sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")
            
        # Verify user still active / valid
        db_admin = database_crud.get_setting(db, "admin_username")
        if username != db_admin:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User mismatch")
            
        return username
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token verification failed: {str(e)}")

# Dynamic Bot Control Helper
async def restart_bot_application(token: str, active: bool = True):
    global bot_app
    if bot_app:
        logger.info("Restarting: Stopping current Telegram Bot...")
        try:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
        except Exception as e:
            logger.error(f"Error stopping bot for restart: {e}")
        bot_app = None

    if token and active:
        logger.info("Restarting: Initializing new Telegram Bot instance...")
        try:
            bot_app = create_bot_app(token)
            await bot_app.initialize()
            await bot_app.start()
            await bot_app.updater.start_polling()
            logger.info("Restarting: Bot started successfully.")
            return True
        except Exception as e:
            logger.exception(f"Restarting: Failed to start bot: {e}")
            return False
    return False

# Pydantic Schemas
class LoginReq(BaseModel):
    username: str
    password: str

class CategoryReq(BaseModel):
    name: str
    slug: str

class ProductReq(BaseModel):
    category_id: int
    name: str
    description: Optional[str] = None
    price: float
    is_active: Optional[bool] = True

class StockReq(BaseModel):
    content: str # Bulk contents split by lines

class SettingsReq(BaseModel):
    telegram_bot_token: str
    pakasir_slug: str
    pakasir_api_key: str
    admin_username: str
    admin_password: str
    bot_welcome_msg: str
    bot_contact_admin: str
    bot_active: str

class BroadcastReq(BaseModel):
    message: str

# ----------------- ADMIN API ENDPOINTS -----------------

@app.post("/api/admin/login")
def admin_login(req: LoginReq, db: Session = Depends(get_db)):
    db_username = database_crud.get_setting(db, "admin_username")
    db_password = database_crud.get_setting(db, "admin_password")
    
    if req.username == db_username and req.password == db_password:
        token = generate_token(req.username)
        return {"success": True, "token": token}
    raise HTTPException(status_code=400, detail="Username atau Password salah")

@app.get("/api/admin/stats")
def admin_stats(db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    txs = database_crud.get_transactions(db)
    products = database_crud.get_products(db)
    categories = database_crud.get_categories(db)
    
    # Aggregates
    completed_txs = [t for t in txs if t.status == "completed"]
    total_revenue = sum(t.amount for t in completed_txs)
    total_tx_count = len(txs)
    total_completed_count = len(completed_txs)
    
    # Active products
    active_prods = [p for p in products if p.is_active]
    
    # Group revenue and tx count by date (past 7 days)
    sales_by_date = {}
    for i in range(7):
        date_str = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        sales_by_date[date_str] = {"revenue": 0.0, "count": 0}
        
    for t in completed_txs:
        date_str = t.completed_at.strftime("%Y-%m-%d")
        if date_str in sales_by_date:
            sales_by_date[date_str]["revenue"] += t.amount
            sales_by_date[date_str]["count"] += 1
            
    sales_chart = [
        {"date": k, "revenue": v["revenue"], "count": v["count"]}
        for k, v in sorted(sales_by_date.items())
    ]
    
    # Group sales by Category
    cat_sales = {c.name: 0.0 for c in categories}
    for t in completed_txs:
        if t.product and t.product.category:
            cat_name = t.product.category.name
            if cat_name in cat_sales:
                cat_sales[cat_name] += t.amount
                
    category_chart = [
        {"category": k, "revenue": v}
        for k, v in cat_sales.items()
    ]

    # Recent transactions
    recent = []
    for t in txs[:10]:
        recent.append({
            "order_id": t.order_id,
            "telegram_user_id": t.telegram_user_id,
            "telegram_username": t.telegram_username,
            "product_name": t.product.name if t.product else "N/A",
            "amount": t.amount,
            "total_payment": t.total_payment,
            "payment_method": t.payment_method,
            "status": t.status,
            "created_at": t.created_at.isoformat()
        })
        
    return {
        "summary": {
            "total_revenue": total_revenue,
            "total_transactions": total_tx_count,
            "completed_transactions": total_completed_count,
            "total_products": len(products),
            "active_products": len(active_prods),
            "total_categories": len(categories)
        },
        "sales_chart": sales_chart,
        "category_chart": category_chart,
        "recent_transactions": recent
    }

# Categories CRUD
@app.get("/api/admin/categories")
def get_categories(db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    categories = database_crud.get_categories(db)
    return [{
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "created_at": c.created_at.isoformat()
    } for c in categories]

@app.post("/api/admin/categories")
def create_category(req: CategoryReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    try:
        cat = database_crud.create_category(db, req.name, req.slug)
        return {"success": True, "category": {"id": cat.id, "name": cat.name, "slug": cat.slug}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membuat kategori. Kemungkinan nama/slug sudah digunakan: {str(e)}")

@app.delete("/api/admin/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    success = database_crud.delete_category(db, cat_id)
    if success:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Kategori tidak ditemukan")

# Products CRUD
@app.get("/api/admin/products")
def get_products(db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    products = database_crud.get_products(db)
    res = []
    for p in products:
        stock_count = database_crud.get_available_stock_count(db, p.id)
        res.append({
            "id": p.id,
            "category_id": p.category_id,
            "category_name": p.category.name if p.category else "N/A",
            "name": p.name,
            "description": p.description,
            "price": p.price,
            "is_active": p.is_active,
            "stock_count": stock_count,
            "created_at": p.created_at.isoformat()
        })
    return res

@app.post("/api/admin/products")
def create_product(req: ProductReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    p = database_crud.create_product(
        db, req.category_id, req.name, req.description, req.price, req.is_active
    )
    return {"success": True, "product": {"id": p.id, "name": p.name}}

@app.put("/api/admin/products/{prod_id}")
def update_product(prod_id: int, req: ProductReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    p = database_crud.update_product(
        db, prod_id, req.name, req.description, req.price, req.is_active
    )
    if p:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

@app.delete("/api/admin/products/{prod_id}")
def delete_product(prod_id: int, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    success = database_crud.delete_product(db, prod_id)
    if success:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Produk tidak ditemukan")

# Stock Management
@app.get("/api/admin/products/{prod_id}/stock")
def get_product_stock(prod_id: int, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    items = database_crud.get_stock_items(db, prod_id)
    return [{
        "id": i.id,
        "content": i.content,
        "is_sold": i.is_sold,
        "created_at": i.created_at.isoformat(),
        "sold_at": i.sold_at.isoformat() if i.sold_at else None
    } for i in items]

@app.post("/api/admin/products/{prod_id}/stock")
def add_product_stock(prod_id: int, req: StockReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    lines = [line.strip() for line in req.content.split("\n") if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="Tidak ada data input stok")
    
    added = database_crud.add_stock(db, prod_id, lines)
    return {"success": True, "count": len(added)}

@app.delete("/api/admin/products/stock/{item_id}")
def delete_stock_item(item_id: int, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    success = database_crud.delete_stock_item(db, item_id)
    if success:
        return {"success": True}
    raise HTTPException(status_code=404, detail="Item stok tidak ditemukan")

# Settings Management
@app.get("/api/admin/settings")
def get_settings(db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    return database_crud.get_all_settings(db)

@app.put("/api/admin/settings")
async def update_settings(req: SettingsReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    # Load previous settings to check for changes in Telegram Bot configuration
    prev_token = database_crud.get_setting(db, "telegram_bot_token")
    prev_active = database_crud.get_setting(db, "bot_active")
    
    data = req.dict()
    for key, value in data.items():
        database_crud.set_setting(db, key, str(value))
        
    # Trigger Telegram bot restart if config changed
    token_changed = prev_token != req.telegram_bot_token
    active_changed = prev_active != req.bot_active
    
    if token_changed or active_changed:
        is_active = req.bot_active == "true"
        # Run bot restart in background to not block response
        asyncio.create_task(restart_bot_application(req.telegram_bot_token, is_active))
        
    return {"success": True, "message": "Settings updated, Bot restart scheduled if token changed."}

# Broadcast Management
async def run_broadcast(users, message: str):
    global bot_app
    if not bot_app:
        logger.error("Cannot run broadcast: Bot is not initialized or active.")
        return

    logger.info(f"Starting broadcast to {len(users)} users.")
    success_count = 0
    fail_count = 0

    for user in users:
        try:
            await bot_app.bot.send_message(
                chat_id=user.id,
                text=message,
                parse_mode="Markdown"
            )
            success_count += 1
            # Add delay to avoid hitting Telegram API limit (30 messages per second)
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user.id}: {e}")
            fail_count += 1

    logger.info(f"Broadcast completed. Success: {success_count}, Failed: {fail_count}")

@app.post("/api/admin/broadcast")
def send_broadcast(req: BroadcastReq, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    if not bot_app:
        raise HTTPException(status_code=400, detail="Bot Telegram saat ini tidak aktif atau belum dikonfigurasi.")
    
    users = database_crud.get_telegram_users(db)
    if not users:
        return {"success": True, "message": "Tidak ada pengguna bot terdaftar untuk dikirimi broadcast."}
    
    # Run the broadcast process in background to prevent API gateway timeouts
    asyncio.create_task(run_broadcast(users, req.message))
    
    return {
        "success": True, 
        "message": f"Broadcast dijadwalkan untuk dikirim ke {len(users)} pengguna di background."
    }

# Transactions Management
@app.get("/api/admin/transactions")
def get_admin_transactions(db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    txs = database_crud.get_transactions(db)
    return [{
        "order_id": t.order_id,
        "telegram_user_id": t.telegram_user_id,
        "telegram_username": t.telegram_username,
        "product_id": t.product_id,
        "product_name": t.product.name if t.product else "N/A",
        "amount": t.amount,
        "fee": t.fee,
        "total_payment": t.total_payment,
        "payment_method": t.payment_method,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None
    } for t in txs]

# Simulates Pakasir Payment directly (helps admin simulate transactions manually)
@app.post("/api/admin/transactions/{order_id}/simulate")
def simulate_payment(order_id: str, db: Session = Depends(get_db), current_user: str = Depends(verify_admin_token)):
    tx = database_crud.get_transaction_by_id(db, order_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan")
    if tx.status != "pending":
        raise HTTPException(status_code=400, detail="Transaksi sudah selesai / dibatalkan")
        
    pakasir_slug = database_crud.get_setting(db, "pakasir_slug")
    pakasir_api_key = database_crud.get_setting(db, "pakasir_api_key")
    
    if not pakasir_slug or not pakasir_api_key:
        raise HTTPException(status_code=400, detail="Pakasir slug atau API key belum dikonfigurasi")
        
    res = simulate_pakasir_payment(
        project=pakasir_slug,
        order_id=tx.order_id,
        amount=int(tx.amount),
        api_key=pakasir_api_key
    )
    
    if "error" in res:
        raise HTTPException(status_code=400, detail=f"Gagal melakukan simulasi: {res['error']}")
        
    return {"success": True, "response": res}

# ----------------- WEBHOOKS -----------------

class WebhookReq(BaseModel):
    amount: float
    order_id: str
    project: str
    status: str
    payment_method: str
    completed_at: str

@app.post("/api/webhook/pakasir")
async def pakasir_webhook(req: WebhookReq, db: Session = Depends(get_db)):
    logger.info(f"Received Pakasir Webhook: order_id={req.order_id}, status={req.status}, amount={req.amount}")
    
    # 1. Verify project matching
    db_slug = database_crud.get_setting(db, "pakasir_slug")
    if req.project != db_slug:
        logger.warning(f"Webhook mismatch: project is '{req.project}' but DB configured for '{db_slug}'")
        raise HTTPException(status_code=400, detail="Project mismatch")
        
    # 2. Check if transaction exists
    tx = database_crud.get_transaction_by_id(db, req.order_id)
    if not tx:
        logger.warning(f"Webhook transaction not found: order_id={req.order_id}")
        raise HTTPException(status_code=404, detail="Transaction not found")

    # 3. Double check completed status
    if req.status == "completed" and tx.status == "pending":
        # complete the transaction and assign a digital item
        completed_tx, item_content = database_crud.complete_transaction(db, tx.order_id)
        if completed_tx.status == "completed" and bot_app:
            # Send digital item contents to user on Telegram asynchronously
            val_content = item_content if item_content else "Data premium sedang disiapkan. Hubungi admin."
            asyncio.create_task(notify_user_payment_success(bot_app, tx.order_id, val_content))
            logger.info(f"Webhook completed successfully for order {tx.order_id}")
            return {"success": True, "message": "Transaction completed and user notified."}
            
    return {"success": True, "message": "No action required / already handled."}


# ----------------- STATIC FRONTEND SERVING -----------------

# Serve index.html or build assets
# Make sure frontend is built into backend/static/ directory
frontend_static_dir = os.path.join(os.path.dirname(__file__), "static")

if os.path.exists(frontend_static_dir):
    app.mount("/_next", StaticFiles(directory=os.path.join(frontend_static_dir, "_next")), name="next_static")
    
    # Fallback to index.html for SPA router
    @app.get("/{rest_of_path:path}")
    async def serve_frontend(rest_of_path: str):
        # Prevent API routes from being falling back to index.html
        if rest_of_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        # Check if file exists in static path
        file_path = os.path.join(frontend_static_dir, rest_of_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_static_dir, "index.html"))
else:
    @app.get("/")
    def index():
        return {"message": "StoreKeyra API running. Frontend static directory not built yet."}
