import requests
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://app.pakasir.com"

def create_pakasir_transaction(method: str, project: str, order_id: str, amount: int, api_key: str):
    """
    Creates a transaction via Pakasir API.
    methods: qris, cimb_niaga_va, bni_va, bri_va, etc.
    """
    url = f"{BASE_URL}/api/transactioncreate/{method}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "project": project,
        "order_id": order_id,
        "amount": int(amount),
        "api_key": api_key
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        logger.info(f"Pakasir Create Response Status: {response.status_code}")
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Pakasir error response: {response.text}")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        logger.exception("Failed to connect to Pakasir API")
        return {"error": str(e)}

def get_pakasir_transaction_detail(project: str, order_id: str, amount: int, api_key: str):
    """
    Retrieves transaction status/details from Pakasir.
    """
    url = f"{BASE_URL}/api/transactiondetail"
    params = {
        "project": project,
        "amount": int(amount),
        "order_id": order_id,
        "api_key": api_key
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Pakasir Detail error response: {response.text}")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        logger.exception("Failed to fetch Pakasir transaction status")
        return {"error": str(e)}

def cancel_pakasir_transaction(project: str, order_id: str, amount: int, api_key: str):
    """
    Cancels transaction.
    """
    url = f"{BASE_URL}/api/transactioncancel"
    headers = {"Content-Type": "application/json"}
    payload = {
        "project": project,
        "order_id": order_id,
        "amount": int(amount),
        "api_key": api_key
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Pakasir Cancel error response: {response.text}")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        logger.exception("Failed to cancel Pakasir transaction")
        return {"error": str(e)}

def simulate_pakasir_payment(project: str, order_id: str, amount: int, api_key: str):
    """
    Simulates sandbox payment to trigger webhook.
    """
    url = f"{BASE_URL}/api/paymentsimulation"
    headers = {"Content-Type": "application/json"}
    payload = {
        "project": project,
        "order_id": order_id,
        "amount": int(amount),
        "api_key": api_key
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Pakasir Simulation error response: {response.text}")
            return {"error": response.text, "status_code": response.status_code}
    except Exception as e:
        logger.exception("Failed to simulate Pakasir payment")
        return {"error": str(e)}
