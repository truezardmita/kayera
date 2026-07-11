import logging
import io
import asyncio
import qrcode
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

from backend.database import SessionLocal, Setting
from backend import database_crud
from backend.pakasir import create_pakasir_transaction, get_pakasir_transaction_detail, cancel_pakasir_transaction

logger = logging.getLogger(__name__)

# Main Keyboard
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("🛍️ Beli Produk"), KeyboardButton("🧾 Riwayat Transaksi")],
        [KeyboardButton("ℹ️ Informasi Bot"), KeyboardButton("📞 Hubungi Admin")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Helper to clean dynamic strings for Markdown V1
def clean_md(val) -> str:
    if val is None:
        return ""
    val_str = str(val)
    # Escape characters that trigger Markdown syntax errors
    return val_str.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[")

# Helper to get settings
def get_db_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        val = database_crud.get_setting(db, key)
        return val if val else default
    finally:
        db.close()

# Register Telegram User
def register_user_interaction(user):
    if not user:
        return
    db = SessionLocal()
    try:
        database_crud.save_telegram_user(
            db=db,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
    except Exception as e:
        logger.error(f"Error registering user: {e}")
    finally:
        db.close()

# Command: /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    welcome_msg = get_db_setting("bot_welcome_msg", "Selamat datang di StoreKeyra Bot! 🛍️")
    await update.message.reply_text(
        welcome_msg,
        reply_markup=get_main_keyboard()
    )

# Handler: Beli Produk (Browse Categories)
async def handle_beli_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    db = SessionLocal()
    try:
        categories = database_crud.get_categories(db)
        if not categories:
            await update.message.reply_text("Maaf, belum ada kategori produk saat ini.")
            return

        keyboard = []
        for cat in categories:
            # Check if this category has active products
            products = database_crud.get_products(db, category_id=cat.id, active_only=True)
            if products:
                keyboard.append([InlineKeyboardButton(f"📁 {cat.name}", callback_data=f"cat_{cat.id}")])

        if not keyboard:
            await update.message.reply_text("Maaf, belum ada produk aktif saat ini.")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Silakan pilih Kategori Produk:", reply_markup=reply_markup)
    finally:
        db.close()

# Handler: Riwayat Transaksi
async def handle_riwayat_transaksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    user_id = update.effective_user.id
    db = SessionLocal()
    try:
        # Find transactions for this user
        txs = db.query(database_crud.Transaction).filter(
            database_crud.Transaction.telegram_user_id == user_id
        ).order_by(database_crud.Transaction.created_at.desc()).limit(5).all()

        if not txs:
            await update.message.reply_text("Kamu belum memiliki riwayat transaksi.")
            return

        text = "=== 5 TRANSAKSI TERAKHIR ===\n\n"
        for tx in txs:
            prod = database_crud.get_product_by_id(db, tx.product_id)
            prod_name = prod.name if prod else "Produk Tidak Dikenal"
            status_emoji = "✅" if tx.status == "completed" else "❌" if tx.status == "cancelled" else "⏳"
            text += f"ID: `{tx.order_id}`\n"
            text += f"Produk: {prod_name}\n"
            text += f"Total: Rp {tx.total_payment:,.0f}\n"
            text += f"Status: {status_emoji} {tx.status.upper()}\n"
            
            if tx.status == "completed":
                # Show digital item if sold and assigned
                if tx.product_item:
                    text += f"Data: `{tx.product_item.content}`\n"
                else:
                    text += "Data: Hubungi admin untuk pengiriman manual.\n"
            text += "-" * 25 + "\n"

        await update.message.reply_text(text, parse_mode="Markdown")
    finally:
        db.close()

# Handler: Informasi Bot
async def handle_informasi_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    info_text = (
        "🤖 *StoreKeyra Bot*\n\n"
        "Bot ini menyediakan berbagai macam Akun Premium, Token Akses, dan produk digital lainnya secara otomatis.\n\n"
        "⚡ Pembayaran instan menggunakan QRIS dan Virtual Account didukung oleh *Pakasir.com*.\n"
        "⚡ Produk akan langsung dikirim oleh bot setelah pembayaran terverifikasi!\n\n"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

# Handler: Hubungi Admin
async def handle_hubungi_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    admin_contact = get_db_setting("bot_contact_admin", "@KeyraAdmin")
    safe_contact = clean_md(admin_contact)
    safe_contact = clean_md(admin_contact)
    text = (
        "📞 *Hubungi Admin*\n\n"
        f"Jika Anda memiliki kendala transaksi atau pertanyaan lainnya, silakan hubungi admin kami di: {safe_contact}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# Helper to format the category's product list message
def format_category_products_message(db, cat, products) -> tuple[str, InlineKeyboardMarkup]:
    note = get_db_setting(
        "bot_product_note",
        "⚠️ *PENTING SEBELUM BELI!* ⚠️\nSemua akun dipastikan aktif saat dibeli. Garansi klaim hanya berlaku 10 menit sejak transaksi (hubungi admin jika ada kendala). Lewat 10 menit, komplain tidak diterima. TIDAK ADA GARANSI PEMAKAIAN — harap beli seperlunya dan langsung digunakan. Membeli berarti setuju & paham konsekuensinya."
    )
    
    text = "🛍️ *Daftar Produk*\n\n"
    keyboard = []
    
    for p in products:
        stock_count = database_crud.get_available_stock_count(db, p.id)
        
        # Formatting price Indonesian style (e.g. Rp 700 or Rp 1.500)
        price_val = f"{p.price:,.0f}".replace(",", ".")
        price_str = f"Rp{price_val}"
        
        # Parse description for list suffix and extra info
        desc_suffix = ""
        extra_info = ""
        if p.description:
            # Check if there is a pipe separator to divide suffix and extra info
            parts = [d.strip() for d in p.description.split("|")]
            if len(parts) >= 2:
                desc_suffix = " " + parts[0]
                extra_info = f" · {parts[1]}"
            elif "\n" not in p.description:
                # If it's a short single line description
                desc_suffix = " " + p.description
        
        text += f"• *{clean_md(p.name)}* — {price_str}{clean_md(desc_suffix)} ({stock_count} tersedia{clean_md(extra_info)})\n"
        
        keyboard.append([InlineKeyboardButton(f"🛒 {p.name} — {price_str}", callback_data=f"prod_{p.id}")])
        
    text += f"\n{note}\n\nTekan tombol di bawah untuk membeli."
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="menu_cats")])
    
    return text, InlineKeyboardMarkup(keyboard)

# Handle Callback Queries (Inline Keyboards)
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user_interaction(update.effective_user)
    query = update.callback_query
    await query.answer()

    data = query.data
    db = SessionLocal()
    try:
        # Category selected: list products
        if data.startswith("cat_"):
            cat_id = int(data.split("_")[1])
            cat = database_crud.get_category_by_id(db, cat_id)
            products = database_crud.get_products(db, category_id=cat_id, active_only=True)
            
            if not products:
                await query.edit_message_text(
                    f"Kategori *{clean_md(cat.name)}* tidak memiliki produk aktif.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="menu_cats")]])
                )
                return

            text, reply_markup = format_category_products_message(db, cat, products)
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

        # Back to categories list
        elif data == "menu_cats":
            categories = database_crud.get_categories(db)
            keyboard = []
            for cat in categories:
                products = database_crud.get_products(db, category_id=cat.id, active_only=True)
                if products:
                    keyboard.append([InlineKeyboardButton(f"📁 {cat.name}", callback_data=f"cat_{cat.id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Silakan pilih Kategori Produk:", reply_markup=reply_markup)

        # Product selected: show details
        elif data.startswith("prod_"):
            prod_id = int(data.split("_")[1])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)

            text = (
                f"📦 *{clean_md(p.name)}*\n\n"
                f"📝 *Deskripsi:*\n{clean_md(p.description) or '-'}\n\n"
                f"💵 *Harga:* Rp {p.price:,.0f}\n"
                f"📊 *Stok Tersedia:* {stock_count}\n"
            )

            keyboard = []
            if stock_count > 0:
                keyboard.append([InlineKeyboardButton("💳 Beli Sekarang", callback_data=f"pay_{p.id}_qris")])
            else:
                keyboard.append([InlineKeyboardButton("🚫 Stok Habis", callback_data="stock_empty")])
            
            keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_prods_{p.category_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Alert if stock empty
        elif data == "stock_empty":
            await query.answer("Maaf, stok untuk produk ini sedang kosong. Silakan hubungi admin.", show_alert=True)

        # Back to products list in category
        elif data.startswith("menu_prods_"):
            cat_id = int(data.split("_")[2])
            cat = database_crud.get_category_by_id(db, cat_id)
            products = database_crud.get_products(db, category_id=cat_id, active_only=True)
            
            text, reply_markup = format_category_products_message(db, cat, products)
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )

        # Buy clicked: show payment methods
        elif data.startswith("buy_"):
            prod_id = int(data.split("_")[1])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)
            
            if stock_count <= 0:
                await query.answer("Stok habis!", show_alert=True)
                return

            text = (
                f"🛒 *Metode Pembayaran*\n\n"
                f"Produk: *{clean_md(p.name)}*\n"
                f"Harga: Rp {p.price:,.0f}\n\n"
                "Silakan pilih metode pembayaran yang ingin digunakan:"
            )

            # Standard payment methods supported by Pakasir
            keyboard = [
                [InlineKeyboardButton("📱 QRIS (All E-Wallet / Bank)", callback_data=f"pay_{p.id}_qris")],
                [InlineKeyboardButton("🏦 BNI VA", callback_data=f"pay_{p.id}_bni_va"), InlineKeyboardButton("🏦 BRI VA", callback_data=f"pay_{p.id}_bri_va")],
                [InlineKeyboardButton("🏦 CIMB VA", callback_data=f"pay_{p.id}_cimb_niaga_va"), InlineKeyboardButton("🏦 Permata VA", callback_data=f"pay_{p.id}_permata_va")],
                [InlineKeyboardButton("🔙 Batal", callback_data=f"prod_{p.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Create payment & order
        elif data.startswith("pay_"):
            parts = data.split("_")
            prod_id = int(parts[1])
            method = "_".join(parts[2:]) # Handles method with multiple underscores like cimb_niaga_va

            # Fetch credentials
            pakasir_slug = database_crud.get_setting(db, "pakasir_slug")
            pakasir_api_key = database_crud.get_setting(db, "pakasir_api_key")

            if not pakasir_slug or not pakasir_api_key:
                await query.edit_message_text(
                    "❌ Sistem pembayaran belum dikonfigurasi oleh Admin. Silakan hubungi admin.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_cats")]])
                )
                return

            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)
            if stock_count <= 0:
                await query.answer("Stok habis!", show_alert=True)
                return

            # Initial message to show loading state
            await query.edit_message_text("⏳ Sedang memproses invoice pembayaran, mohon tunggu...")

            # Generate unique transaction order_id and record it
            # To simulate exact fee, we create transaction in database first
            tx = database_crud.create_transaction(
                db=db,
                telegram_user_id=query.from_user.id,
                telegram_username=query.from_user.username,
                product_id=p.id,
                amount=p.price,
                fee=0,
                total_payment=p.price,
                payment_method=method
            )

            # Call Pakasir API to generate invoice
            res = create_pakasir_transaction(
                method=method,
                project=pakasir_slug,
                order_id=tx.order_id,
                amount=int(p.price),
                api_key=pakasir_api_key
            )

            if "error" in res or not res.get("payment"):
                # Cancel the transaction in our database since API call failed
                database_crud.cancel_transaction(db, tx.order_id)
                error_detail = res.get("error") or res.get("message") or "Response format invalid from Payment Gateway"
                await query.edit_message_text(
                    f"❌ Gagal memproses transaksi ke Payment Gateway:\n{error_detail}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data=f"prod_{p.id}")]])
                )
                return

            # Extract payment details
            pay_data = res.get("payment") or {}
            fee = pay_data.get("fee", 0)
            total_payment = pay_data.get("total_payment", p.price + fee)
            payment_number = pay_data.get("payment_number", "")
            expired_str = pay_data.get("expired_at", "")

            # Update transaction in DB with correct fee and total payment
            tx.fee = fee
            tx.total_payment = total_payment
            db.commit()

            # Parse expired_at to reader-friendly format
            # expired_at is usually RFC3339 string like "2025-09-19T01:18:49.678622564Z"
            try:
                dt = datetime.fromisoformat(expired_str.replace("Z", "+00:00"))
                expired_formatted = dt.strftime("%d %b %Y, %H:%M:%S UTC")
            except:
                expired_formatted = expired_str

            detail_text = (
                f"🧾 *INVOICE PEMBAYARAN*\n\n"
                f"ID Order: `{tx.order_id}`\n"
                f"Produk: *{clean_md(p.name)}*\n"
                f"Metode: *{method.upper()}*\n\n"
                f"Harga: Rp {p.price:,.0f}\n"
                f"Biaya Admin: Rp {fee:,.0f}\n"
                f"🏦 *Total Pembayaran:* `Rp {total_payment:,.0f}`\n"
                f"⏳ *Batas Waktu:* {expired_formatted}\n\n"
            )

            # Keyboard for status check/cancel
            tx_keyboard = [
                [InlineKeyboardButton("🔄 Cek Pembayaran", callback_data=f"chk_{tx.order_id}")],
                [InlineKeyboardButton("❌ Batalkan Pesanan", callback_data=f"cnl_{tx.order_id}")]
            ]
            tx_markup = InlineKeyboardMarkup(tx_keyboard)

            if method == "qris":
                detail_text += "👉 Silakan SCAN kode QR di bawah menggunakan aplikasi E-Wallet atau M-Banking Anda untuk membayar."
                # Generate QR code image
                qr_bio = generate_qr_code(payment_number)
                # Send QR Image along with detail text
                await query.message.reply_photo(
                    photo=qr_bio,
                    caption=detail_text,
                    parse_mode="Markdown",
                    reply_markup=tx_markup
                )
                # Delete the loading message
                await query.message.delete()
            else:
                detail_text += (
                    "👉 Silakan lakukan transfer ke nomor Virtual Account berikut:\n\n"
                    f"🔢 *Nomor VA / Rekening:* `{payment_number}`\n\n"
                    "Dana akan langsung diverifikasi otomatis oleh sistem."
                )
                await query.edit_message_text(
                    detail_text,
                    parse_mode="Markdown",
                    reply_markup=tx_markup
                )

        # Check Payment Status
        elif data.startswith("chk_"):
            order_id = data.split("_")[1]
            tx = database_crud.get_transaction_by_id(db, order_id)
            if not tx:
                await query.answer("Transaksi tidak ditemukan.", show_alert=True)
                return

            if tx.status == "completed":
                # Already complete
                content = tx.product_item.content if tx.product_item else "Credentials manual (Hubungi Admin)"
                await query.edit_message_text(
                    f"✅ *Pembayaran Berhasil!*\n\n"
                    f"Terima kasih atas pembelian Anda untuk produk *{tx.product.name}*.\n\n"
                    f"🔑 *Data Produk Anda:*\n`{content}`\n\n"
                    "Simpan data ini baik-baik.",
                    parse_mode="Markdown"
                )
                return

            if tx.status == "cancelled":
                await query.edit_message_text("❌ Transaksi ini telah dibatalkan.")
                return

            if tx.status == "expired":
                await query.edit_message_text("❌ Transaksi ini telah kadaluarsa.")
                return

            # If still pending, call Pakasir Detail API to check status
            pakasir_slug = database_crud.get_setting(db, "pakasir_slug")
            pakasir_api_key = database_crud.get_setting(db, "pakasir_api_key")

            res = get_pakasir_transaction_detail(
                project=pakasir_slug,
                order_id=tx.order_id,
                amount=int(tx.amount),
                api_key=pakasir_api_key
            )

            tx_data = res.get("transaction", {})
            status = tx_data.get("status", "")

            if status == "completed":
                # Process completion
                completed_tx, item_content = database_crud.complete_transaction(db, tx.order_id)
                if completed_tx.status == "completed":
                    val_content = item_content if item_content else "Hubungi admin untuk mendapatkan data manual (stok habis saat pembayaran)."
                    await query.edit_message_text(
                        f"✅ *Pembayaran Berhasil Terverifikasi!*\n\n"
                        f"Terima kasih atas pembelian Anda untuk produk *{tx.product.name}*.\n\n"
                        f"🔑 *Data Produk Anda:*\n`{val_content}`\n\n"
                        "Terima kasih telah berbelanja di store kami!",
                        parse_mode="Markdown"
                    )
                else:
                    await query.answer("Gagal memproses transaksi. Hubungi admin.", show_alert=True)
            else:
                await query.answer("❌ Pembayaran belum diterima. Silakan selesaikan pembayaran terlebih dahulu.", show_alert=True)

        # Cancel Transaction
        elif data.startswith("cnl_"):
            order_id = data.split("_")[1]
            tx = database_crud.get_transaction_by_id(db, order_id)
            if not tx:
                await query.answer("Transaksi tidak ditemukan.", show_alert=True)
                return
            
            if tx.status != "pending":
                await query.answer(f"Status transaksi sudah {tx.status}.", show_alert=True)
                return

            # Cancel in Pakasir
            pakasir_slug = database_crud.get_setting(db, "pakasir_slug")
            pakasir_api_key = database_crud.get_setting(db, "pakasir_api_key")

            cancel_pakasir_transaction(
                project=pakasir_slug,
                order_id=tx.order_id,
                amount=int(tx.amount),
                api_key=pakasir_api_key
            )

            # Cancel in DB
            database_crud.cancel_transaction(db, tx.order_id)
            
            await query.edit_message_text(
                "❌ Transaksi ini telah dibatalkan atas permintaan Anda.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu Utama", callback_data="menu_cats")]])
            )

    except Exception as e:
        logger.exception("Error handling callback query")
        await query.answer("Terjadi kesalahan internal. Silakan coba lagi.", show_alert=True)
    finally:
        db.close()

# Generate QR Code binary stream helper
def generate_qr_code(qr_string: str) -> io.BytesIO:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_string)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = io.BytesIO()
    bio.name = 'qris.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

# Webhook completion notifications (sent from main web app to Bot context)
async def notify_user_payment_success(application: Application, order_id: str, item_content: str):
    db = SessionLocal()
    try:
        tx = database_crud.get_transaction_by_id(db, order_id)
        if not tx:
            return

        chat_id = tx.telegram_user_id
        text = (
            f"✅ *PEMBAYARAN DITERIMA!*\n\n"
            f"Pembayaran untuk order `{order_id}` telah terverifikasi otomatis.\n"
            f"Nama Produk: *{clean_md(tx.product.name)}*\n"
            f"Nominal: Rp {tx.total_payment:,.0f}\n\n"
            f"🔑 *Data Produk Anda:*\n`{item_content}`\n\n"
            "Terima kasih telah berbelanja!"
        )
        try:
            await application.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown"
            )
        except Exception as bot_err:
            logger.error(f"Error sending success message to telegram user {chat_id}: {bot_err}")
    finally:
        db.close()

# Init Bot Application instance
def create_bot_app(token: str) -> Application:
    application = Application.builder().token(token).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.Text("🛍️ Beli Produk"), handle_beli_produk))
    application.add_handler(MessageHandler(filters.Text("🧾 Riwayat Transaksi"), handle_riwayat_transaksi))
    application.add_handler(MessageHandler(filters.Text("ℹ️ Informasi Bot"), handle_informasi_bot))
    application.add_handler(MessageHandler(filters.Text("📞 Hubungi Admin"), handle_hubungi_admin))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    return application
