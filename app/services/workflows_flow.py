# app/services/workflows_flow.py
from datetime import datetime
from app.models import Ticket
from app.soap.client import set_trouble_ticket_by_value

def request_additional_info(ticket: Ticket, dialog: str, attachments: list[dict] = None):
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "dialog": dialog,
        "clearancePerson": "ibiocom",
        "attachments": attachments or []
    }
    result = set_trouble_ticket_by_value(payload, env="PRE")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}

def propose_resolution(ticket: Ticket, date_restore_service: datetime, raw_resolution: str,
                       dialog: str = None, attachments: list[dict] = None, certification=None,
                       department=None, raw_real_tipification=None):
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "certification": certification,
        "department": department,
        "rawRealTipification": raw_real_tipification,
        "dateRestoreService": date_restore_service.isoformat(),
        "rawResolution": raw_resolution,
        "dialog": dialog or "",
        "clearancePerson": "ibiocom",
        "attachments": attachments or []
    }
    result = set_trouble_ticket_by_value(payload, env="PRE")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}

def send_report(ticket: Ticket, dialog: str, attachments: list[dict] = None):
    payload = {
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "dialog": dialog,
        "clearancePerson": "ibiocom",
        "attachments": attachments or []
    }
    result = set_trouble_ticket_by_value(payload, env="PRE")
    # ✅ Mensaje amigable para frontend
    if "error" in result:
        return {"message": "Error al enviar la solicitud", "message_type": "error"}
    else:
        return {"message": "Solicitud enviada correctamente", "message_type": "success"}

