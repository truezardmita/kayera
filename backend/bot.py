import logging
import io
import re
import asyncio
import qrcode
from datetime import datetime, timezone, timedelta

# Waktu Indonesia Barat (WIB / Asia Jakarta = UTC+7)
WIB = timezone(timedelta(hours=7))
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ReplyKeyboardRemove
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
from backend import markastools
from backend.pakasir import create_pakasir_transaction, get_pakasir_transaction_detail, cancel_pakasir_transaction

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

def is_valid_email(value: str) -> bool:
    return bool(EMAIL_REGEX.match((value or "").strip()))

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
    
    if update.effective_chat.type in ["group", "supergroup"]:
        await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

# Command: /id (To get Group/Channel ID)
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    msg = f"🆔 ID {chat_type.capitalize()} ini adalah: `{chat_id}`"
    
    if update.message and update.message.is_topic_message:
        topic_id = update.message.message_thread_id
        msg += f"\n🔖 ID Topic (Thread ID): `{topic_id}`"
        
    if update.effective_chat.type in ["group", "supergroup"]:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")


# Command: /produk (Show all products and stock)
async def produk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        products = database_crud.get_products(db, active_only=True)
        if not products:
            await update.message.reply_text("Maaf, belum ada produk aktif saat ini.")
            return

        text = "📦 *DAFTAR PRODUK & STOK*\n\n"
        for p in products:
            stock = database_crud.get_available_stock_count(db, p.id)
            text += f"▪️ *{clean_md(p.name)}*\n"
            text += f"   📦 Tersedia: `{stock}`\n"
            text += f"   💰 Harga: `Rp {p.price:,.0f}`\n\n"
            
        bot_username = clean_md(context.bot.username)
        
        # If the command was used in a group/supergroup, force remove keyboard
        if update.effective_chat.type in ["group", "supergroup"]:
            text += f"Silakan chat ke @{bot_username} untuk melakukan pembelian."
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        else:
            text += "Gunakan menu di bawah untuk mulai membeli."
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
            
    except Exception as e:
        import traceback
        err_msg = f"❌ Terjadi kesalahan saat memproses /produk:\n`{str(e)}`\n\nTraceback:\n`{traceback.format_exc()[-1000:]}`"
        await update.message.reply_text(err_msg, parse_mode="Markdown")
    finally:
        db.close()


# Handler: Beli Produk (Browse Categories)
async def handle_beli_produk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        return
        
    register_user_interaction(update.effective_user)

    # Mulai belanja dari awal: buang sisa state input jumlah / email yang belum selesai
    # (email Markastools yang sudah tersimpan tetap dipakai agar tidak perlu ketik ulang)
    context.user_data.pop("waiting_email", None)
    context.user_data.pop("pending_order", None)
    context.user_data.pop("waiting_qty_prod_id", None)
    context.user_data.pop("waiting_qty_stock", None)

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
    if update.effective_chat.type in ["group", "supergroup"]:
        return
        
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
    if update.effective_chat.type in ["group", "supergroup"]:
        return
        
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
    if update.effective_chat.type in ["group", "supergroup"]:
        return
        
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


# ---------- Alur checkout: metode pembayaran & email Markastools ----------

def build_payment_method_message(p, qty: int, include_va: bool = False, buyer_email: str = "") -> tuple[str, InlineKeyboardMarkup]:
    """Layar pemilihan metode pembayaran.

    include_va=True menampilkan pilihan Virtual Account (dipakai pada alur input
    jumlah manual), sedangkan alur tombol cepat hanya memakai QRIS.
    """
    text = (
        f"🛒 *Metode Pembayaran*\n\n"
        f"Produk: *{clean_md(p.name)}*\n"
        f"Jumlah: *{qty}x*\n"
        f"Total Harga: Rp {(p.price * qty):,.0f}\n"
    )
    if buyer_email:
        text += f"📧 Email Markastools: `{clean_md(buyer_email)}`\n"
    text += "\nSilakan pilih metode pembayaran yang ingin digunakan:"

    keyboard = [
        [InlineKeyboardButton("📱 QRIS (All E-Wallet / Bank)", callback_data=f"pay_{p.id}_{qty}_qris")]
    ]
    if include_va:
        keyboard.append([
            InlineKeyboardButton("🏦 BNI VA", callback_data=f"pay_{p.id}_{qty}_bni_va"),
            InlineKeyboardButton("🏦 BRI VA", callback_data=f"pay_{p.id}_{qty}_bri_va"),
        ])
        keyboard.append([
            InlineKeyboardButton("🏦 CIMB VA", callback_data=f"pay_{p.id}_{qty}_cimb_niaga_va"),
            InlineKeyboardButton("🏦 Permata VA", callback_data=f"pay_{p.id}_{qty}_permata_va"),
        ])
    keyboard.append([InlineKeyboardButton("🔙 Batal", callback_data=f"prod_{p.id}")])

    return text, InlineKeyboardMarkup(keyboard)


def build_email_prompt_message(p, qty: int, provider: str) -> tuple[str, InlineKeyboardMarkup]:
    """Minta email akun Markastools milik pembeli sebelum invoice dibuat."""
    text = (
        f"📧 *Masukkan Email Markastools Anda*\n\n"
        f"Produk: *{clean_md(p.name)}*\n"
        f"Jumlah: *{qty}x*\n"
        f"Total: Rp {(p.price * qty):,.0f}\n\n"
        f"Akun *{markastools.provider_label(provider)}* ini akan otomatis dimasukkan "
        f"ke akun Anda di ai.markastools.id setelah pembayaran terverifikasi.\n\n"
        f"Balas pesan ini dengan email akun Markastools Anda.\n"
        f"⚠️ Pastikan email sudah terdaftar di ai.markastools.id dan tidak salah tulis."
    )
    keyboard = [[InlineKeyboardButton("🔙 Batal", callback_data=f"prod_{p.id}")]]
    return text, InlineKeyboardMarkup(keyboard)


def build_email_confirm_message(p, qty: int, email: str, provider: str) -> tuple[str, InlineKeyboardMarkup]:
    """Konfirmasi email yang sudah pernah dipakai pembeli di sesi ini."""
    text = (
        f"📧 *Konfirmasi Email Markastools*\n\n"
        f"Produk: *{clean_md(p.name)}*\n"
        f"Jumlah: *{qty}x*\n"
        f"Total: Rp {(p.price * qty):,.0f}\n\n"
        f"Akun *{markastools.provider_label(provider)}* akan dikirim ke:\n"
        f"`{clean_md(email)}`\n\n"
        f"Sudah benar?"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Lanjut Bayar", callback_data=f"payok_{p.id}_{qty}")],
        [InlineKeyboardButton("✏️ Ganti Email", callback_data=f"email_{p.id}_{qty}")],
        [InlineKeyboardButton("🔙 Batal", callback_data=f"prod_{p.id}")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_next_step_after_qty(context, p, qty: int, include_va: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    """Tentukan layar berikutnya setelah jumlah pembelian diketahui.

    Produk auto-inject wajib punya email Markastools dulu, produk biasa langsung
    ke pemilihan metode pembayaran.
    """
    provider = markastools.normalize_provider(p.inject_provider)
    if not provider:
        context.user_data.pop("waiting_email", None)
        context.user_data.pop("pending_order", None)
        return build_payment_method_message(p, qty, include_va=include_va)

    context.user_data["pending_order"] = {"prod_id": p.id, "qty": qty, "include_va": include_va}
    email = (context.user_data.get("markastools_email") or "").strip()
    if email:
        context.user_data.pop("waiting_email", None)
        return build_email_confirm_message(p, qty, email, provider)

    context.user_data["waiting_email"] = True
    return build_email_prompt_message(p, qty, provider)


# Handle Callback Queries (Inline Keyboards)
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        bot_username = context.bot.username
        await update.callback_query.answer(f"Pemesanan hanya bisa di Private Message @{bot_username}", show_alert=True)
        return

    try:
        register_user_interaction(update.effective_user)
    except Exception:
        pass  # Don't let user registration failure block button interactions

    query = update.callback_query
    await query.answer()

    data = query.data
    db = SessionLocal()
    try:
        # Category selected: list products
        if data.startswith("cat_") or data.startswith("menu_prods_"):
            cat_id = int(data.split("_")[1]) if data.startswith("cat_") else int(data.split("_")[2])
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
                f"💵 *Harga:* Rp {p.price:,.0f} / item\n"
                f"📊 *Stok Tersedia:* {stock_count}\n"
            )

            keyboard = []
            if stock_count > 0:
                keyboard.append([InlineKeyboardButton("🛒 Beli Sekarang", callback_data=f"qty_{p.id}")])
            else:
                keyboard.append([InlineKeyboardButton("🚫 Stok Habis", callback_data="stock_empty")])
            
            keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"menu_prods_{p.category_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Alert if stock empty
        elif data == "stock_empty":
            await query.answer("Maaf, stok untuk produk ini sedang kosong. Silakan hubungi admin.", show_alert=True)

        # Quantity selection step
        elif data.startswith("qty_") and not data.startswith("qty_custom_"):
            prod_id = int(data.split("_")[1])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)

            if stock_count <= 0:
                await query.answer("Stok habis!", show_alert=True)
                return

            text = (
                f"🛒 *Pilih Jumlah Pembelian*\n\n"
                f"Produk: *{clean_md(p.name)}*\n"
                f"Harga Satuan: Rp {p.price:,.0f}\n"
                f"Stok Tersedia: {stock_count}\n\n"
                f"Pilih jumlah cepat atau ketik manual:"
            )

            # Quick-select buttons: 1, 2, 3, 5, 10 (capped to stock)
            quick_qtys = [q for q in [1, 2, 3, 5, 10] if q <= stock_count]
            qty_buttons = []
            row = []
            for q in quick_qtys:
                total = p.price * q
                total_str = f"{total:,.0f}".replace(",", ".")
                row.append(InlineKeyboardButton(f"{q}x — Rp{total_str}", callback_data=f"buy_{p.id}_{q}"))
                if len(row) == 2:
                    qty_buttons.append(row)
                    row = []
            if row:
                qty_buttons.append(row)

            # Manual input button
            qty_buttons.append([InlineKeyboardButton("✏️ Ketik Jumlah Sendiri", callback_data=f"qty_custom_{p.id}")])
            qty_buttons.append([InlineKeyboardButton("🔙 Kembali", callback_data=f"prod_{p.id}")])
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(qty_buttons))

        # Manual quantity input: ask user to type a number
        elif data.startswith("qty_custom_"):
            prod_id = int(data.split("_")[2])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)

            if stock_count <= 0:
                await query.answer("Stok habis!", show_alert=True)
                return

            # Save state in user_data so the next text message is treated as qty input
            context.user_data["waiting_qty_prod_id"] = prod_id
            context.user_data["waiting_qty_stock"] = stock_count

            await query.edit_message_text(
                f"✏️ *Ketik Jumlah Pembelian*\n\n"
                f"Produk: *{clean_md(p.name)}*\n"
                f"Harga Satuan: Rp {p.price:,.0f}\n"
                f"Stok Tersedia: {stock_count}\n\n"
                f"Balas pesan ini dengan angka jumlah yang ingin dibeli (1 – {stock_count}):",
                parse_mode="Markdown"
            )

        # Buy clicked: ask for Markastools email (auto-inject) or show payment methods
        elif data.startswith("buy_"):
            parts = data.split("_")
            prod_id = int(parts[1])
            qty = int(parts[2])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)

            if qty > stock_count:
                await query.answer("Stok tidak mencukupi!", show_alert=True)
                return

            text, reply_markup = build_next_step_after_qty(context, p, qty)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Email Markastools dikonfirmasi: lanjut ke pemilihan metode pembayaran
        elif data.startswith("payok_"):
            parts = data.split("_")
            prod_id = int(parts[1])
            qty = int(parts[2])
            p = database_crud.get_product_by_id(db, prod_id)
            stock_count = database_crud.get_available_stock_count(db, p.id)

            if qty > stock_count:
                await query.answer(f"Stok hanya tersisa {stock_count}!", show_alert=True)
                return

            pending = context.user_data.get("pending_order") or {}
            email = (context.user_data.get("markastools_email") or "").strip()
            if not email:
                # Email hilang (mis. bot sempat restart) — minta ulang
                text, reply_markup = build_next_step_after_qty(context, p, qty, include_va=pending.get("include_va", False))
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                return

            text, reply_markup = build_payment_method_message(
                p, qty, include_va=pending.get("include_va", False), buyer_email=email
            )
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Ganti email Markastools
        elif data.startswith("email_"):
            parts = data.split("_")
            prod_id = int(parts[1])
            qty = int(parts[2])
            p = database_crud.get_product_by_id(db, prod_id)
            provider = markastools.normalize_provider(p.inject_provider)

            pending = context.user_data.get("pending_order") or {}
            context.user_data["pending_order"] = {
                "prod_id": p.id, "qty": qty, "include_va": pending.get("include_va", False)
            }
            context.user_data["waiting_email"] = True

            text, reply_markup = build_email_prompt_message(p, qty, provider)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        # Create payment & order
        elif data.startswith("pay_"):
            parts = data.split("_")
            prod_id = int(parts[1])
            qty = int(parts[2])  # quantity is always the 3rd part
            method = "_".join(parts[3:])  # method may contain underscores like cimb_niaga_va

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
            if qty > stock_count:
                await query.answer(f"Stok hanya tersisa {stock_count}!", show_alert=True)
                return

            # Produk auto-inject wajib punya email Markastools sebelum invoice dibuat
            provider = markastools.normalize_provider(p.inject_provider)
            buyer_email = (context.user_data.get("markastools_email") or "").strip() if provider else ""
            if provider and not buyer_email:
                text, reply_markup = build_next_step_after_qty(context, p, qty)
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                return

            # Calculate totals based on qty
            subtotal = p.price * qty

            # Initial message to show loading state
            await query.edit_message_text("⏳ Sedang memproses invoice pembayaran, mohon tunggu...")

            # Generate unique transaction order_id and record it
            tx = database_crud.create_transaction(
                db=db,
                telegram_user_id=query.from_user.id,
                telegram_username=query.from_user.username,
                product_id=p.id,
                amount=subtotal,
                fee=0,
                total_payment=subtotal,
                payment_method=method,
                buyer_email=buyer_email or None
            )

            # Store qty in telegram_username field as a note (workaround — store as JSON prefix)
            # Better: we store qty in the order_id notes via DB quantity field if available
            # For now store qty in a separate way by encoding in transaction
            # We'll use product_item_id temporarily to store qty until payment completes
            # Actually the cleanest is to just remember qty from callback at complete time
            # We store qty as a note in a new DB field — but for now encode in order metadata
            # Simple approach: store qty in the transaction's fee field temporarily (0 * qty trick)
            # REAL solution: add quantity column — but migration needed. Use amount/price to derive.
            # qty = round(tx.amount / p.price) can recover qty at completion time!

            # Call Pakasir API to generate invoice
            res = create_pakasir_transaction(
                method=method,
                project=pakasir_slug,
                order_id=tx.order_id,
                amount=int(subtotal),
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
                # Konversi otomatis ke waktu WIB (Asia/Jakarta)
                expired_formatted = dt.astimezone(WIB).strftime("%d %b %Y, %H:%M:%S WIB")
            except:
                expired_formatted = expired_str

            detail_text = (
                f"🧾 *INVOICE PEMBAYARAN*\n\n"
                f"ID Order: `{tx.order_id}`\n"
                f"Produk: *{clean_md(p.name)}*\n"
                f"Jumlah: *{qty}x*\n"
                f"Metode: *{method.upper()}*\n\n"
                f"Harga Satuan: Rp {p.price:,.0f}\n"
                f"Subtotal: Rp {subtotal:,.0f}\n"
                f"Biaya Admin: Rp {fee:,.0f}\n"
                f"🏦 *Total Pembayaran:* `Rp {total_payment:,.0f}`\n"
                f"⏳ *Batas Waktu:* {expired_formatted}\n\n"
            )

            if provider:
                detail_text += (
                    f"📧 Akun *{markastools.provider_label(provider)}* otomatis dikirim ke "
                    f"`{clean_md(buyer_email)}`\n\n"
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
                sent_msg = await query.message.reply_photo(
                    photo=qr_bio,
                    caption=detail_text,
                    parse_mode="Markdown",
                    reply_markup=tx_markup
                )
                tx.invoice_msg_id = sent_msg.message_id
                db.commit()
                # Delete the loading message
                await query.message.delete()
            else:
                detail_text += (
                    "👉 Silakan lakukan transfer ke nomor Virtual Account berikut:\n\n"
                    f"🔢 *Nomor VA / Rekening:* `{payment_number}`\n\n"
                    "Dana akan langsung diverifikasi otomatis oleh sistem."
                )
                sent_msg = await query.message.reply_text(
                    detail_text,
                    parse_mode="Markdown",
                    reply_markup=tx_markup
                )
                tx.invoice_msg_id = sent_msg.message_id
                db.commit()
                # Hapus pesan "sedang memproses..."
                await query.message.delete()
                
            # Schedule payment timeout task (15 minutes)
            asyncio.create_task(handle_payment_timeout(context.application, tx.order_id))

        # Check Payment Status
        elif data.startswith("chk_"):
            order_id = data.split("_", 1)[1]  # Use maxsplit=1 to safely handle any order_id format
            tx = database_crud.get_transaction_by_id(db, order_id)
            if not tx:
                await query.answer("Transaksi tidak ditemukan.", show_alert=True)
                return

            if tx.status == "completed":
                # Already complete — resend as file (pakai seluruh item yang terkirim)
                content = tx.delivered_content or (
                    tx.product_item.content if tx.product_item else "Credentials manual (Hubungi Admin)"
                )
                note = ""
                if tx.inject_status:
                    provider = markastools.normalize_provider(tx.product.inject_provider if tx.product else None)
                    note = _inject_note(
                        tx.inject_status, provider, tx.buyer_email or "-",
                        {"message": tx.inject_detail or ""}
                    )
                await query.edit_message_text(
                    f"✅ *Pembayaran sudah terverifikasi!*\n"
                    f"Mengirimkan ulang file data produk Anda...",
                    parse_mode="Markdown"
                )
                await send_product_as_file(
                    bot=query.get_bot(),
                    chat_id=query.from_user.id,
                    order_id=tx.order_id,
                    product_name=tx.product.name if tx.product else "Produk",
                    item_content=content,
                    inject_note=note
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

                    # Auto-inject ke Markastools (kosong bila produk tidak memakai fitur ini)
                    note = await inject_purchase(tx.order_id)

                    try:
                        await query.message.delete()
                    except Exception:
                        pass
                    await send_product_as_file(
                        bot=query.get_bot(),
                        chat_id=query.from_user.id,
                        order_id=tx.order_id,
                        product_name=tx.product.name if tx.product else "Produk",
                        item_content=val_content,
                        inject_note=note
                    )
                else:
                    await query.answer("Gagal memproses transaksi. Hubungi admin.", show_alert=True)
            else:
                await query.answer("❌ Pembayaran belum diterima. Silakan selesaikan pembayaran terlebih dahulu.", show_alert=True)

        # Cancel Transaction
        elif data.startswith("cnl_"):
            order_id = data.split("_", 1)[1]  # Use maxsplit=1 to safely handle any order_id format
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

# Helper: Send product data as a .txt file
async def send_product_as_file(bot, chat_id: int, order_id: str, product_name: str, item_content: str,
                               inject_note: str = ""):
    """Sends the product data as a downloadable .txt file to the user.

    inject_note (opsional) berisi hasil auto-inject ke Markastools dan
    ditempelkan pada caption serta isi file.
    """
    file_content = (
        f"============================\n"
        f"  ORDER: {order_id}\n"
        f"  PRODUK: {product_name}\n"
        f"============================\n\n"
        f"{item_content}\n\n"
    )
    if inject_note:
        # Buang formatting Markdown agar rapi di dalam file teks
        plain_note = inject_note.replace("*", "").replace("`", "")
        file_content += f"----------------------------\n{plain_note}\n\n"
    file_content += (
        f"============================\n"
        f"Terima kasih telah berbelanja!\n"
        f"Simpan file ini dengan aman.\n"
        f"============================"
    )
    file_bio = io.BytesIO(file_content.encode("utf-8"))
    file_bio.name = f"order_{order_id}.txt"
    file_bio.seek(0)

    caption = (
        f"✅ *PEMBAYARAN DITERIMA!*\n\n"
        f"Order: `{order_id}`\n"
        f"Produk: *{product_name}*\n\n"
    )
    if inject_note:
        caption += f"{inject_note}\n\n"
    caption += (
        f"📄 Data produk Anda ada di file di atas.\n"
        f"Simpan file tersebut dengan aman!"
    )

    await bot.send_document(
        chat_id=chat_id,
        document=file_bio,
        filename=f"order_{order_id}.txt",
        caption=caption,
        parse_mode="Markdown"
    )


# ---------- Auto-inject ke Markastools ----------

def tokens_from_delivered_content(content: str) -> list:
    """Isi stok tersimpan satu item per baris (lihat complete_transaction)."""
    return [line.strip() for line in (content or "").split("\n") if line.strip()]


def _inject_note(status: str, provider: str, email: str, summary: dict) -> str:
    """Rangkum hasil auto-inject menjadi teks singkat untuk pembeli."""
    label = markastools.provider_label(provider)
    detail = (summary.get("message") or "")[:300]

    if status == "success":
        return (
            f"🚀 *Akun {label} sudah otomatis masuk ke Markastools*\n"
            f"📧 Email: `{clean_md(email)}`\n"
            f"✅ {clean_md(detail)}\n"
            f"Buka ai.markastools.id lalu refresh halaman akun Anda."
        )
    if status == "partial":
        return (
            f"⚠️ *Auto-inject {label} hanya sebagian berhasil*\n"
            f"📧 Email: `{clean_md(email)}`\n"
            f"{clean_md(detail)}\n"
            f"Token mentah ada di file. Hubungi admin untuk sisanya."
        )
    return (
        f"⚠️ *Auto-inject {label} ke Markastools gagal*\n"
        f"📧 Email: `{clean_md(email)}`\n"
        f"{clean_md(detail)}\n"
        f"Token mentah tetap terkirim di file. Hubungi admin untuk bantuan."
    )


def save_inject_result(order_id: str, email: str, status: str, detail: str):
    """Simpan hasil auto-inject ke transaksi memakai sesi DB tersendiri."""
    db = SessionLocal()
    try:
        tx = database_crud.get_transaction_by_id(db, order_id)
        if tx:
            if email:
                tx.buyer_email = email
            tx.inject_status = status
            tx.inject_detail = (detail or "")[:500]
            db.commit()
    except Exception:
        logger.exception(f"Gagal menyimpan status auto-inject {order_id}")
        db.rollback()
    finally:
        db.close()


async def inject_purchase(order_id: str, override_email: str = None) -> str:
    """Kirim stok yang sudah dibayar ke akun Markastools pembeli.

    Mengembalikan catatan siap-tampil untuk pembeli, atau string kosong bila
    produk tidak memakai fitur auto-inject.
    """
    # Fase 1 — baca data pesanan lalu tutup sesi DB. Koneksi database tidak boleh
    # ditahan selama panggilan HTTP ke Markastools (bisa sampai 30 detik), karena
    # jatah koneksi Postgres di hosting terbatas.
    db = SessionLocal()
    try:
        tx = database_crud.get_transaction_by_id(db, order_id)
        if not tx:
            return ""

        product = tx.product
        provider = markastools.normalize_provider(product.inject_provider if product else None)
        if not provider:
            return ""

        email = (override_email or tx.buyer_email or "").strip()
        recipe_id = product.inject_recipe_id if product else None
        tokens = tokens_from_delivered_content(tx.delivered_content)
    except Exception:
        logger.exception(f"Gagal membaca data pesanan {order_id} untuk auto-inject")
        return (
            "⚠️ *Auto-inject ke Markastools gagal karena kesalahan internal*\n"
            "Token mentah tetap terkirim di file. Hubungi admin untuk bantuan."
        )
    finally:
        db.close()

    if not email:
        msg = "Email Markastools pembeli tidak tersedia."
        save_inject_result(order_id, "", "failed", msg)
        return _inject_note("failed", provider, "-", {"message": msg})

    if not tokens:
        msg = "Tidak ada stok terkirim untuk di-inject (stok habis saat pembayaran)."
        save_inject_result(order_id, email, "failed", msg)
        return _inject_note("failed", provider, email, {"message": msg})

    # Fase 2 — requests bersifat blocking, jalankan di thread agar event loop bot tidak macet
    try:
        summary = await asyncio.to_thread(
            markastools.add_accounts, email, tokens, provider, recipe_id
        )
    except Exception as e:
        logger.exception(f"Error saat auto-inject order {order_id}")
        msg = f"Kesalahan internal: {e}"
        save_inject_result(order_id, email, "failed", msg)
        return _inject_note("failed", provider, email, {"message": msg})

    if summary.get("ok"):
        status = "success"
    elif summary.get("partial"):
        status = "partial"
    else:
        status = "failed"

    # Fase 3 — catat hasilnya
    detail = summary.get("message") or ""
    save_inject_result(order_id, email, status, detail)

    logger.info(f"Auto-inject {order_id} -> {email} ({provider}): {status} | {detail}")
    return _inject_note(status, provider, email, summary)


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

# Catch-all text handler: routes free text to whichever input step is active
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type in ["group", "supergroup"]:
        return  # Ignore random text in groups

    if context.user_data.get("waiting_email"):
        await handle_email_input(update, context)
        return

    if context.user_data.get("waiting_qty_prod_id"):
        await handle_manual_qty_input(update, context)


# Handle Markastools email input (user types the email for an auto-inject product)
async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_order") or {}
    prod_id = pending.get("prod_id")
    qty = pending.get("qty")
    if not prod_id or not qty:
        # State hilang — bersihkan dan minta pembeli mulai ulang
        context.user_data.pop("waiting_email", None)
        await update.message.reply_text(
            "Sesi pemesanan sudah kedaluwarsa. Silakan pilih produk lagi lewat menu 🛍️ Beli Produk."
        )
        return

    email = (update.message.text or "").strip()
    if not is_valid_email(email):
        await update.message.reply_text(
            "❌ Format email tidak valid. Contoh: `nama@gmail.com`\n"
            "Silakan kirim ulang email akun Markastools Anda:",
            parse_mode="Markdown"
        )
        return

    db = SessionLocal()
    try:
        p = database_crud.get_product_by_id(db, prod_id)
        if not p:
            context.user_data.pop("waiting_email", None)
            await update.message.reply_text("❌ Produk tidak ditemukan. Silakan pilih produk lagi.")
            return

        stock_count = database_crud.get_available_stock_count(db, p.id)
        if qty > stock_count:
            context.user_data.pop("waiting_email", None)
            await update.message.reply_text(
                f"❌ Maaf, stok sudah berubah. Sisa stok sekarang *{stock_count}*. Silakan pesan ulang.",
                parse_mode="Markdown"
            )
            return

        # Simpan email agar bisa dipakai lagi pada pembelian berikutnya di sesi ini
        context.user_data["markastools_email"] = email
        context.user_data.pop("waiting_email", None)

        text, reply_markup = build_payment_method_message(
            p, qty, include_va=pending.get("include_va", False), buyer_email=email
        )
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error handling email input: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    finally:
        db.close()


# Handle manual quantity input (user types a number after clicking "Ketik Jumlah Sendiri")
async def handle_manual_qty_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod_id = context.user_data.get("waiting_qty_prod_id")
    if not prod_id:
        # Not waiting for qty input, ignore
        return

    text = update.message.text.strip()
    db = SessionLocal()
    try:
        p = database_crud.get_product_by_id(db, prod_id)
        stock_count = database_crud.get_available_stock_count(db, p.id)

        # Validate input
        if not text.isdigit():
            await update.message.reply_text(
                f"❌ Masukkan angka yang valid (1 – {stock_count}):"
            )
            return

        qty = int(text)
        if qty < 1:
            await update.message.reply_text("❌ Jumlah minimal adalah 1.")
            return
        if qty > stock_count:
            await update.message.reply_text(
                f"❌ Stok hanya tersisa *{stock_count}*. Masukkan angka yang sesuai:",
                parse_mode="Markdown"
            )
            return

        # Clear waiting state
        context.user_data.pop("waiting_qty_prod_id", None)
        context.user_data.pop("waiting_qty_stock", None)

        # Produk auto-inject minta email dulu, produk biasa langsung ke pembayaran
        text_msg, reply_markup = build_next_step_after_qty(context, p, qty, include_va=True)
        await update.message.reply_text(
            text_msg,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error handling manual qty input: {e}")
        await update.message.reply_text("❌ Terjadi kesalahan. Silakan coba lagi.")
    finally:
        db.close()


# Payment timeout background task
async def handle_payment_timeout(application: Application, order_id: str):
    # Wait for 15 minutes
    await asyncio.sleep(15 * 60)
    
    db = SessionLocal()
    try:
        tx = db.query(database_crud.Transaction).filter(database_crud.Transaction.order_id == order_id).first()
        if not tx or tx.status != "pending":
            return # Already handled (paid, cancelled, or not found)
            
        # Cancel the transaction in DB
        tx.status = "cancelled"
        db.commit()
        
        chat_id = tx.telegram_user_id
        
        # Cancel the transaction in Pakasir
        pakasir_slug = database_crud.get_setting(db, "pakasir_slug")
        pakasir_api_key = database_crud.get_setting(db, "pakasir_api_key")
        if pakasir_slug and pakasir_api_key:
            cancel_pakasir_transaction(
                project=pakasir_slug,
                order_id=tx.order_id,
                amount=int(tx.amount),
                api_key=pakasir_api_key
            )
        
        # Delete the invoice message
        if tx.invoice_msg_id:
            try:
                await application.bot.delete_message(chat_id=chat_id, message_id=tx.invoice_msg_id)
            except Exception as e:
                logger.error(f"Failed to delete expired invoice {order_id}: {e}")
                
        # Send timeout notification
        cancel_msg = (
            f"❌ *WAKTU PEMBAYARAN HABIS*\n\n"
            f"Order ID: `{tx.order_id}`\n\n"
            f"Mohon maaf, Anda tidak menyelesaikan pembayaran dalam waktu 15 menit. "
            f"Pesanan Anda telah otomatis dibatalkan dan stok dilepas kembali.\n\n"
            f"Silakan buat pesanan baru jika Anda masih berminat!"
        )
        try:
            await application.bot.send_message(chat_id=chat_id, text=cancel_msg, parse_mode="Markdown")
        except Exception:
            pass
            
    finally:
        db.close()


# Webhook completion notifications (sent from main web app to Bot context)
async def notify_user_payment_success(application: Application, order_id: str, item_content: str):
    db = SessionLocal()
    try:
        tx = db.query(database_crud.Transaction).filter(database_crud.Transaction.order_id == order_id).first()
        if not tx:
            return

        chat_id = tx.telegram_user_id
        product_name = tx.product.name if tx.product else "Produk"
    finally:
        db.close()

    # Auto-inject ke Markastools sebelum notifikasi dikirim (string kosong bila
    # produk tidak memakai fitur ini). Sesi DB sendiri, di luar sesi di atas.
    inject_note = await inject_purchase(order_id)

    db = SessionLocal()
    try:
        tx = db.query(database_crud.Transaction).filter(database_crud.Transaction.order_id == order_id).first()
        invoice_msg_id = tx.invoice_msg_id if tx else None
    finally:
        db.close()

    # Hapus pesan invoice pembayaran sebelumnya jika ada
    if invoice_msg_id:
        try:
            await application.bot.delete_message(chat_id=chat_id, message_id=invoice_msg_id)
        except Exception as del_err:
            logger.error(f"Failed to delete invoice message for {order_id}: {del_err}")

    try:
        await send_product_as_file(
            bot=application.bot,
            chat_id=chat_id,
            order_id=order_id,
            product_name=product_name,
            item_content=item_content,
            inject_note=inject_note
        )
    except Exception as bot_err:
        logger.error(f"Error sending success file to telegram user {chat_id}: {bot_err}")

# Init Bot Application instance
def create_bot_app(token: str) -> Application:
    application = Application.builder().token(token).build()
    
    # Handlers — order matters: specific text filters first, catch-all last
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("produk", produk_command))
    application.add_handler(MessageHandler(filters.Text("🛍️ Beli Produk"), handle_beli_produk))
    application.add_handler(MessageHandler(filters.Text("🧾 Riwayat Transaksi"), handle_riwayat_transaksi))
    application.add_handler(MessageHandler(filters.Text("ℹ️ Informasi Bot"), handle_informasi_bot))
    application.add_handler(MessageHandler(filters.Text("📞 Hubungi Admin"), handle_hubungi_admin))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    # Catch-all text handler for manual qty / email input (lowest priority)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    return application
