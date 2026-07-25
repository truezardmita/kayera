"""Integrasi Seller API Markastools (https://ai.markastools.id).

Dipakai untuk meng-inject akun yang dibeli (Weavy / Framia / Roboneo) langsung
ke akun pembeli di aplikasi Markastools segera setelah pembayaran terverifikasi.

Endpoint: POST /api/seller/accounts
Autentikasi: header `Authorization: Bearer <SELLER_API_KEY>` (khusus Roboneo,
dokumentasi juga mengirim api_key di body — keduanya dikirim).
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://ai.markastools.id"
ACCOUNTS_ENDPOINT = f"{BASE_URL}/api/seller/accounts"

# Provider yang didukung Seller API.
SUPPORTED_PROVIDERS = ("weavy", "framia", "roboneo")

# Label untuk ditampilkan ke pembeli / dashboard.
PROVIDER_LABELS = {
    "weavy": "Weavy",
    "framia": "Framia",
    "roboneo": "Roboneo",
}

# API key diisi oleh main.py (hardcoded) atau env MARKASTOOLS_SELLER_API_KEY.
SELLER_API_KEY = os.getenv("MARKASTOOLS_SELLER_API_KEY", "")

# Pesan error berdasarkan HTTP status seperti dijelaskan di dokumentasi Seller API.
ERROR_BY_STATUS = {
    401: "API key seller tidak terkirim (401).",
    403: "Ditolak server (403): API key salah, akun pembeli disuspend, atau token sudah dipakai user lain.",
    404: "Email tujuan tidak ditemukan di Markastools (404). Pastikan pembeli sudah mendaftar & memakai email yang benar.",
}


def configure(api_key: str):
    """Set API key seller yang dipakai untuk semua request."""
    global SELLER_API_KEY
    if api_key:
        SELLER_API_KEY = api_key


def normalize_provider(provider) -> str:
    """Kembalikan nama provider yang valid, atau string kosong bila produk tidak
    memakai fitur auto-inject."""
    value = (provider or "").strip().lower()
    return value if value in SUPPORTED_PROVIDERS else ""


def provider_label(provider) -> str:
    key = normalize_provider(provider)
    return PROVIDER_LABELS.get(key, key.upper() if key else "-")


def parse_stock_line(line) -> tuple[str, str]:
    """Stok produk auto-inject ditulis satu token per baris. Nama akun opsional
    bisa ditambahkan dengan format `token|nama akun`."""
    parts = [part.strip() for part in str(line or "").split("|")]
    token = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""
    return token, name


def build_payload(target_email: str, tokens, provider: str, recipe_id=None, api_key: str = None) -> dict:
    """Susun body request sesuai bentuk yang diminta tiap provider.

    Weavy / Framia memakai array objek `{"token": ..., "name": ...}`, sedangkan
    Roboneo memakai array string berisi API key akun.
    """
    accounts = []
    for raw in tokens or []:
        token, name = parse_stock_line(raw)
        if not token:
            continue
        if provider == "roboneo":
            accounts.append(token)
        else:
            item = {"token": token}
            if name:
                item["name"] = name
            accounts.append(item)

    payload = {
        "target_email": (target_email or "").strip(),
        "provider": provider,
        "accounts": accounts,
    }

    # recipe_id hanya berlaku untuk Weavy, diabaikan provider lain.
    if provider == "weavy" and recipe_id:
        payload["recipe_id"] = str(recipe_id).strip()

    if provider == "roboneo":
        payload["api_key"] = api_key or SELLER_API_KEY

    return payload


def _summarize(data: dict, sent_count: int) -> dict:
    """Ubah response Seller API menjadi ringkasan yang seragam."""
    def as_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    added = as_int(data.get("added"))
    updated = as_int(data.get("updated"))
    total = as_int(data.get("total")) or (added + updated)

    results = data.get("results")
    results = results if isinstance(results, list) else []
    failed = [r for r in results if isinstance(r, dict) and not r.get("ok")]

    server_ok = data.get("ok")
    ok = bool(server_ok) if server_ok is not None else (added + updated) > 0

    # Bila ada item yang ditolak, hitung sebagai sebagian berhasil.
    processed = added + updated
    partial = ok and (failed or (sent_count and processed < sent_count))

    messages = []
    for item in failed[:5]:
        reason = item.get("error") or item.get("message") or "ditolak server"
        line = item.get("line")
        messages.append(f"baris {line}: {reason}" if line else str(reason))

    if not ok:
        detail = data.get("error") or data.get("message") or "Server menolak permintaan tanpa keterangan."
        message = str(detail)
    elif partial:
        message = f"{processed} dari {sent_count} akun berhasil masuk."
        if messages:
            message += " Gagal: " + "; ".join(messages)
    else:
        message = f"{processed} akun berhasil masuk ({added} baru, {updated} diperbarui)."

    return {
        "ok": ok and not partial,
        "partial": bool(partial),
        "added": added,
        "updated": updated,
        "total": total,
        "sent": sent_count,
        "message": message,
        "results": results,
        "raw": data,
    }


def add_accounts(target_email: str, tokens, provider: str = "weavy", recipe_id=None,
                 api_key: str = None, timeout: int = 30) -> dict:
    """Tambahkan satu atau banyak akun ke user Markastools.

    Mengembalikan dict berisi: ok, partial, added, updated, total, sent, message,
    results, status_code.
    """
    provider = normalize_provider(provider)
    if not provider:
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": 0, "message": "Provider tidak didukung.", "results": [], "status_code": 0}

    key = api_key or SELLER_API_KEY
    if not key:
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": 0, "message": "API key seller Markastools belum dikonfigurasi.",
                "results": [], "status_code": 0}

    email = (target_email or "").strip()
    if not email:
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": 0, "message": "Email tujuan kosong.", "results": [], "status_code": 0}

    payload = build_payload(email, tokens, provider, recipe_id=recipe_id, api_key=key)
    sent_count = len(payload["accounts"])
    if sent_count == 0:
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": 0, "message": "Tidak ada token yang bisa dikirim.", "results": [], "status_code": 0}

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(ACCOUNTS_ENDPOINT, json=payload, headers=headers, timeout=timeout)
    except Exception as e:
        logger.exception("Gagal menghubungi Seller API Markastools")
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": sent_count, "message": f"Tidak bisa menghubungi server Markastools: {e}",
                "results": [], "status_code": 0}

    logger.info(
        "Markastools inject: provider=%s email=%s accounts=%s status=%s",
        provider, email, sent_count, response.status_code
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code != 200:
        message = ERROR_BY_STATUS.get(response.status_code)
        if not message:
            detail = data.get("error") or data.get("message") if isinstance(data, dict) else None
            message = f"HTTP {response.status_code}: {detail or response.text[:200]}"
        logger.error(f"Markastools inject gagal ({response.status_code}): {response.text[:500]}")
        return {"ok": False, "partial": False, "added": 0, "updated": 0, "total": 0,
                "sent": sent_count, "message": message, "results": [],
                "status_code": response.status_code}

    if not isinstance(data, dict):
        data = {}

    summary = _summarize(data, sent_count)
    summary["status_code"] = response.status_code
    return summary
