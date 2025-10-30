import json
from app.database import engine
from app.models import Log
from sqlmodel import Session

def log_event(event_type: str, payload: dict | str = None, ticket_pk: str = None,
              user_email: str = None, direction: str = None, status: str = "success"):
    """
    Guarda un evento de log en la base de datos.
    """
    if isinstance(payload, dict):
        payload = json.dumps(payload, ensure_ascii=False, indent=2)

    log_entry = Log(
        event_type=event_type,
        payload=payload,
        ticket_primary_key=ticket_pk,
        user_email=user_email,
        direction=direction,
        status=status
    )

    with Session(engine) as session:
        session.add(log_entry)
        session.commit()
