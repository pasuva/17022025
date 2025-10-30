from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from typing import List, Optional
from sqlmodel import Session, select
from datetime import datetime
from app.database import engine
from app.models import Ticket
from app.services.ftth_flow import request_additional_info, propose_resolution, send_report
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/ftth", tags=["FTTH"])

@router.post("/{ticket_id}/request_info")
async def api_request_info(ticket_id: int, dialog: str = Form(...), attachments: Optional[List[UploadFile]] = File(None),
                           user=Depends(get_current_user)):
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
    result = request_additional_info(ticket, dialog, attachments)
    return result

@router.post("/{ticket_id}/propose_resolution")
async def api_propose_resolution(ticket_id: int,
                                 date_restore_service: str = Form(...),
                                 raw_resolution: str = Form(...),
                                 dialog: Optional[str] = Form(None),
                                 certification: Optional[str] = Form(None),
                                 department: Optional[str] = Form(None),
                                 raw_real_tipification: Optional[str] = Form(None),
                                 attachments: Optional[List[UploadFile]] = File(None),
                                 user=Depends(get_current_user)):
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
    date_obj = datetime.fromisoformat(date_restore_service)
    result = propose_resolution(ticket, date_obj, raw_resolution, dialog, attachments,
                                certification, department, raw_real_tipification)
    return result

@router.post("/{ticket_id}/send_report")
async def api_send_report(ticket_id: int, dialog: str = Form(...), attachments: Optional[List[UploadFile]] = File(None),
                          user=Depends(get_current_user)):
    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket no encontrado")
    result = send_report(ticket, dialog, attachments)
    return result
