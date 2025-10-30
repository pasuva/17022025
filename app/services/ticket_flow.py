from app.soap.client import set_trouble_ticket_by_value
from app.models import Ticket
from app.database import engine
from sqlmodel import Session
from datetime import datetime

def handle_incoming_ticket(data: dict, ticket_type: str = "ftth_cliente"):
    """
    Simula el proceso que ocurre cuando Adamo nos envía un ticket.
    Guarda o actualiza el ticket localmente.
    """
    primary_key = data.get("primaryKey")
    state = data.get("baseTroubleTicketState", "OPENACTIVE")
    dialog = data.get("dialog", "")
    mirror_key = data.get("mirrorKey") or f"RED-{int(datetime.now().timestamp())}"

    with Session(engine) as session:
        existing = session.query(Ticket).filter(Ticket.primary_key == primary_key).first()
        if existing:
            existing.state = state
            existing.dialog = dialog
            existing.updated_at = datetime.utcnow()
            session.add(existing)
            ticket = existing
        else:
            ticket = Ticket(
                primary_key=primary_key,
                mirror_key=mirror_key,
                state=state,
                dialog=dialog,
                ticket_type=ticket_type  # <-- Aquí asignamos el tipo
            )
            session.add(ticket)
        session.commit()
        session.refresh(ticket)
    return ticket



def propose_resolution(ticket: Ticket):
    """
    Simula el envío de una resolución hacia Adamo vía SOAP.
    """
    payload = {
        "baseTroubleTicketState": "OPENACTIVE",
        "primaryKey": ticket.primary_key,
        "mirrorKey": ticket.mirror_key,
        "rawRealTipification": "FTTH_INS_NOK_CORTES",
        "rawResolution": "FTTH_REVENTA_ACTUACION_EN_RED",
        "dialog": "Propuesta de resolución desde entorno local",
        "clearancePerson": "ibiocom"
    }

    result = set_trouble_ticket_by_value(payload, env="PRE")
    return result
