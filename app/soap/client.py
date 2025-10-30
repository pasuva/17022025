from zeep import Client, Settings
from zeep.transports import Transport
from zeep.exceptions import Fault
from requests import Session
from requests.auth import HTTPBasicAuth
import os
from app.services.logger import log_event

WSDL_PRE = os.getenv("ADAMO_WSDL_PRE")
WSDL_PRO = os.getenv("ADAMO_WSDL_PRO")
ADAMO_USER = os.getenv("ADAMO_USER")
ADAMO_PASS = os.getenv("ADAMO_PASS")

def get_client(env: str = "PRE"):
    wsdl = WSDL_PRE if env == "PRE" else WSDL_PRO
    session = Session()
    if ADAMO_USER and ADAMO_PASS:
        session.auth = HTTPBasicAuth(ADAMO_USER, ADAMO_PASS)
    transport = Transport(session=session, timeout=10)
    settings = Settings(strict=False, xml_huge_tree=True)
    return Client(wsdl=wsdl, transport=transport, settings=settings)

def set_trouble_ticket_by_value(payload: dict, env: str = "PRE", simulate_offline: bool = None):
    """
    Envía un ticket a Adamo. Maneja errores OSS/J específicos.
    """
    if simulate_offline is None:
        simulate_offline = os.getenv("ADAMO_SIMULATE", "true").lower() == "true"

    log_event("soap_out", payload, payload.get("primaryKey"), direction="out", status="pending")

    if simulate_offline:
        result = {"status": "mock", "echo_payload": payload, "message": "Simulación local"}
        log_event("soap_out", result, payload.get("primaryKey"), direction="out", status="success")
        return result

    try:
        client = get_client(env)
        response = client.service.setTroubleTicketByValue(**payload)
        log_event("soap_out", response, payload.get("primaryKey"), direction="out", status="success")
        return response
    except Fault as fault:
        # Extraer tipo de excepción OSS/J
        error_type = None
        if hasattr(fault, "detail") and fault.detail is not None:
            detail = fault.detail
            if hasattr(detail, "illegalArgumentException"):
                error_type = "illegalArgumentException"
            elif hasattr(detail, "setException"):
                error_type = "setException"
            elif hasattr(detail, "objectNotFoundException"):
                error_type = "objectNotFoundException"
            elif hasattr(detail, "remoteException"):
                error_type = "remoteException"

        log_event("soap_out", str(fault), payload.get("primaryKey"), direction="out", status="error")
        return {"error": str(fault), "type": error_type}
    except Exception as e:
        log_event("soap_out", str(e), payload.get("primaryKey"), direction="out", status="error")
        return {"error": str(e), "type": "unknown"}

