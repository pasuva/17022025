from fastapi import APIRouter
from app.services.ticket_flow import handle_incoming_ticket, propose_resolution

router = APIRouter(prefix="/simulate", tags=["Simulation"])

@router.post("/adamo-to-ibiocom-multiple")
def simulate_multiple_tickets():
    """
    Simula que Adamo nos envía varios tickets nuevos vía webhook.
    """
    fake_tickets = [
        {
            "primaryKey": "IB-LOCAL-001",
            "baseTroubleTicketState": "OPENACTIVE",
            "dialog": "Incidencia FTTH Cliente",
            "ticket_type": "ftth_cliente"
        },
        {
            "primaryKey": "IB-LOCAL-002",
            "baseTroubleTicketState": "OPENACTIVE",
            "dialog": "Incidencia FTTH Masivo",
            "ticket_type": "ftth_masivo"
        },
        {
            "primaryKey": "IB-LOCAL-003",
            "baseTroubleTicketState": "OPENACTIVE",
            "dialog": "Otra incidencia cliente",
            "ticket_type": "ftth_cliente"
        },
        {
            "primaryKey": "IB-WORKFLOW-004",
            "baseTroubleTicketState": "OPENACTIVE",
            "dialog": "Otra incidencia cliente",
            "ticket_type": "trabajos_programados"
        },
    ]

    created_tickets = []
    for ft in fake_tickets:
        ticket = handle_incoming_ticket(ft, ticket_type=ft["ticket_type"])
        created_tickets.append(ticket)

    return {"status": "received", "tickets": created_tickets}


@router.post("/ibiocom-to-adamo")
def simulate_ibiocom_to_adamo():
    """
    Simula que Ibiocom propone una resolución y la envía a Adamo vía SOAP.
    """
    # Reutilizamos el ticket anterior
    from app.database import engine
    from sqlmodel import Session, select
    from app.models import Ticket

    with Session(engine) as session:
        ticket = session.exec(select(Ticket).order_by(Ticket.id.desc())).first()
        if not ticket:
            return {"error": "No hay tickets en la base de datos para enviar"}

    response = propose_resolution(ticket)
    return {"status": "sent", "soap_response": response}
