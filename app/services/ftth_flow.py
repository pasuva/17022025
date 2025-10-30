from typing import List, Optional
from datetime import datetime
from app.soap.client import set_trouble_ticket_by_value
from app.models import Ticket
from app.services.logger import log_event

def request_additional_info(ticket: Ticket, dialog: str, attachments: Optional[List[dict]] = None, env: str = "PRE"):
    """
    Solicita información adicional a Adamo para un ticket FTTH.
    attachments: lista de dicts con keys ["filename", "content", "content_type"]
    """
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "dialog": dialog,
        "clearancePerson": "ibiocom",
        "attachments": []
    }

    if attachments:
        for f in attachments:
            payload["attachments"].append({
                "content": f["content"],
                "mimeType": f.get("content_type", "application/octet-stream"),
                "name": f["filename"]
            })

    result = set_trouble_ticket_by_value(payload, env=env)
    log_event("ftth_request_info", payload, ticket.primary_key, direction="out", status="success" if "error" not in result else "error")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}


def propose_resolution(ticket: Ticket, date_restore_service: datetime, raw_resolution: str,
                       dialog: Optional[str] = None, attachments: Optional[List[dict]] = None,
                       certification: Optional[str] = None, department: Optional[str] = None,
                       raw_real_tipification: Optional[str] = None, env: str = "PRE"):
    """
    Envía propuesta de resolución a Adamo para un ticket FTTH.
    attachments: lista de dicts con keys ["filename", "content", "content_type"]
    """
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "dateRestoreService": date_restore_service.isoformat(),
        "rawResolution": raw_resolution,
        "clearancePerson": "ibiocom",
        "dialog": dialog or "",
        "certification": certification,
        "department": department,
        "rawRealTipification": raw_real_tipification,
        "attachments": []
    }

    if attachments:
        for f in attachments:
            payload["attachments"].append({
                "content": f["content"],
                "mimeType": f.get("content_type", "application/octet-stream"),
                "name": f["filename"]
            })

    result = set_trouble_ticket_by_value(payload, env=env)
    log_event("ftth_propose_resolution", payload, ticket.primary_key, direction="out", status="success" if "error" not in result else "error")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}


def send_report(ticket: Ticket, dialog: str, attachments: Optional[List[dict]] = None, env: str = "PRE"):
    """
    Envía reporte a Adamo para un ticket FTTH.
    attachments: lista de dicts con keys ["filename", "content", "content_type"]
    """
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "dialog": dialog,
        "clearancePerson": "ibiocom",
        "attachments": []
    }

    if attachments:
        for f in attachments:
            payload["attachments"].append({
                "content": f["content"],
                "mimeType": f.get("content_type", "application/octet-stream"),
                "name": f["filename"]
            })

    result = set_trouble_ticket_by_value(payload, env=env)
    log_event("ftth_send_report", payload, ticket.primary_key, direction="out", status="success" if "error" not in result else "error")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}
