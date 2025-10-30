from fastapi import APIRouter, Request, HTTPException
from sqlmodel import Session, select
from app.database import engine
from app.models import Ticket
from datetime import datetime
from app.services.logger import log_event
from app.soap.client import set_trouble_ticket_by_value  # Nuestro cliente SOAP

router = APIRouter()

@router.post("/webhook/adamo")
async def webhook_adamo(request: Request):
    """
    Recibe notificaciones desde Adamo (OSS/J).
    Guarda ticket localmente y envía feedback a Adamo.
    """
    data = await request.json()
    primary_key = data.get("primaryKey")
    if not primary_key:
        raise HTTPException(status_code=400, detail="primaryKey es requerido")

    mirror_key = data.get("mirrorKey") or f"RED-{int(datetime.now().timestamp())}"

    try:
        with Session(engine) as session:
            stmt = select(Ticket).where(Ticket.primary_key == primary_key)
            existing = session.exec(stmt).first()

            if existing:
                # Actualizar ticket local
                existing.state = data.get("baseTroubleTicketState") or existing.state
                existing.dialog = data.get("dialog") or existing.dialog
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)
                ticket = existing
            else:
                # Crear nuevo ticket
                ticket = Ticket(
                    primary_key=primary_key,
                    mirror_key=mirror_key,
                    state=data.get("baseTroubleTicketState"),
                    dialog=data.get("dialog"),
                )
                session.add(ticket)
                session.commit()
                session.refresh(ticket)

        # Después de guardar localmente, enviamos a Adamo
        payload = {
            "troubleTicketKey": {"primaryKey": ticket.primary_key, "mirrorKey": ticket.mirror_key},
            "baseTroubleTicketState": ticket.state,
            "dialog": ticket.dialog,
            "clearancePerson": "ibiocom",
        }

        response = set_trouble_ticket_by_value(payload)

        if response.get("error"):
            # Rollback local si falla Adamo
            with Session(engine) as session:
                t = session.get(Ticket, ticket.id)
                if t:
                    session.delete(t)
                    session.commit()
            log_event("rollback", {"ticket_id": ticket.id, "response": response}, ticket.primary_key, direction="local", status="rolled_back")
            raise HTTPException(status_code=500, detail=f"Error al enviar a Adamo: {response.get('error')}")

        # Log de éxito
        log_event("webhook_in", data, ticket.primary_key, direction="in", status="success")
        return {"status": "ok", "mirrorKey": ticket.mirror_key}

    except Exception as e:
        log_event("webhook_error", str(e), primary_key, direction="in", status="error")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

