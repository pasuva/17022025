from fastapi import APIRouter, HTTPException, Depends, status
from sqlmodel import Session, select
from app.database import engine
from app.models import Ticket
from app.auth.dependencies import get_current_user
from app.soap.client import set_trouble_ticket_by_value
from app.services.logger import log_event

router = APIRouter(prefix="/tickets", tags=["Tickets"])

@router.get("/")
def list_tickets(limit: int = 50, offset: int = 0, user=Depends(get_current_user)):
    """
    Lista tickets locales.
    """
    with Session(engine) as session:
        tickets = session.exec(select(Ticket).offset(offset).limit(limit)).all()
    return tickets

@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, user=Depends(get_current_user)):
    """
    Detalle de un ticket.
    """
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket

@router.post("/{ticket_id}/retry")
def retry_ticket(ticket_id: int, user=Depends(get_current_user)):
    """
    Reintenta enviar un ticket a Adamo si falló previamente.
    """
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")

        payload = {
            "troubleTicketKey": {"primaryKey": ticket.primary_key, "mirrorKey": ticket.mirror_key},
            "baseTroubleTicketState": ticket.state,
            "dialog": ticket.dialog,
            "clearancePerson": "ibiocom",
        }

        response = set_trouble_ticket_by_value(payload)
        if response.get("error"):
            log_event("retry_error", response, ticket.primary_key, direction="out", status="error")
            raise HTTPException(status_code=500, detail=f"Error al reintentar con Adamo: {response['error']}")

        log_event("retry_success", response, ticket.primary_key, direction="out", status="success")
        return {"status": "ok", "message": "Ticket enviado correctamente a Adamo", "response": response}
