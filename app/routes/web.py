from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from app.database import engine
from app.models import User, Ticket
from passlib.context import CryptContext
import os
from datetime import datetime
from typing import List, Optional
import json
from fastapi.responses import FileResponse
from fastapi import HTTPException

import base64

# Flujos específicos
from app.services.ftth_flow import (
    request_additional_info as ftth_request_info,
    propose_resolution as ftth_propose_resolution,
    send_report as ftth_send_report
)

from app.services.ftth_masive_flow import (
    request_additional_info as massive_request_info,
    propose_resolution as massive_propose_resolution,
    send_report as massive_send_report
)

from app.services.workflows_flow import (
    request_additional_info as wf_request_info,
    propose_resolution as wf_propose_resolution,
    send_report as wf_send_report
)

router = APIRouter(prefix="/web", tags=["Web"])
templates = Jinja2Templates(directory="app/templates")

# Filtro personalizado Jinja para convertir strings JSON
def fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except Exception:
        return []

templates.env.filters["fromjson"] = fromjson
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_USER = None  # Sesión simple

# ---------- LOGIN / LOGOUT ----------

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
def login_action(request: Request, email: str = Form(...), password: str = Form(...)):
    global SESSION_USER
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if not user or not pwd_context.verify(password, user.password_hash):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales inválidas"})
        SESSION_USER = user
    return RedirectResponse("/web/dashboard", status_code=302)

@router.get("/logout")
def logout():
    global SESSION_USER
    SESSION_USER = None
    return RedirectResponse("/web/login", status_code=302)


# ---------- DASHBOARD / LISTADO ----------

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    with Session(engine) as session:
        tickets = session.exec(select(Ticket).order_by(Ticket.created_at.desc())).all()

    stats = {
        "total": len(tickets),
        "abierto": sum(1 for t in tickets if t.state == "abierto"),
        "proceso": sum(1 for t in tickets if t.state == "proceso"),
        "cerrado": sum(1 for t in tickets if t.state == "cerrado"),
    }

    new_tickets_count = sum(1 for t in tickets if t.state == "abierto")
    latest_tickets = tickets[:5]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": SESSION_USER,
        "stats": stats,
        "latest_tickets": latest_tickets,
        "new_tickets_count": new_tickets_count
    })


@router.get("/tickets", response_class=HTMLResponse)
def list_tickets(request: Request):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    with Session(engine) as session:
        tickets = session.exec(select(Ticket).order_by(Ticket.created_at.desc())).all()
        tickets_data = [ticket_to_dict(t) for t in tickets]

    return templates.TemplateResponse("tickets.html", {
        "request": request,
        "tickets": tickets_data,
        "current_user": SESSION_USER
    })


# ---------- DETALLE DEL TICKET ----------

@router.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(request: Request, ticket_id: int, msg: Optional[str] = None):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return templates.TemplateResponse(
                "ticket_detail.html",
                {"request": request, "ticket": None, "message": "Ticket no encontrado", "message_type": "error"}
            )
        ticket_data = ticket_to_dict(ticket)

    return templates.TemplateResponse("ticket_detail.html", {
        "request": request,
        "ticket": ticket_data,
        "current_user": SESSION_USER,
        "message": msg,
        "message_type": "info"
    })

@router.get("/files/{ticket_id}/{filename}")
def get_file(ticket_id: int, filename: str):
    path = os.path.join("uploads", str(ticket_id), filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(path)

# ---------- SUBIDA DE ARCHIVO ----------

@router.post("/tickets/{ticket_id}/upload", response_class=HTMLResponse)
async def upload_file(request: Request, ticket_id: int, file: UploadFile = File(...)):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    # Carpeta específica del ticket
    upload_dir = os.path.join("uploads", str(ticket_id))
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, file.filename)

    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    return RedirectResponse(
        f"/web/tickets/{ticket_id}?msg=Archivo '{file.filename}' subido correctamente",
        status_code=302
    )



# ---------- UTILIDADES ----------

def get_ticket_flow(ticket: Ticket):
    tipo = getattr(ticket, "ticket_type", None)
    if tipo == "ftth_masivo":
        return massive_request_info, massive_propose_resolution, massive_send_report
    elif tipo == "trabajos_programados":
        return wf_request_info, wf_propose_resolution, wf_send_report
    return ftth_request_info, ftth_propose_resolution, ftth_send_report

def append_local_record(ticket: Ticket, field: str, record: dict):
    existing_data = []
    if getattr(ticket, field):
        try:
            existing_data = json.loads(getattr(ticket, field))
        except Exception:
            existing_data = []
    existing_data.append(record)
    setattr(ticket, field, json.dumps(existing_data))

def ticket_to_dict(ticket: Ticket):
    """Convierte Ticket SQLModel a diccionario seguro para Jinja2"""
    return {
        "id": ticket.id,
        "primary_key": ticket.primary_key,
        "ticket_type": ticket.ticket_type,
        "state": ticket.state,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "dialog": ticket.dialog,
        "local_requests": ticket.local_requests,
        "local_resolutions": ticket.local_resolutions,
        "local_reports": ticket.local_reports
    }

def extract_message(result):
    """Extrae message y tipo para alertas"""
    if isinstance(result, dict):
        msg = result.get("message", "Operación realizada")
        status = result.get("status", "info")
    else:
        msg = str(result)
        status = "info"
    if status.lower() in ["openactive", "mock"]:
        status = "success"
    elif status.lower() in ["error", "fail"]:
        status = "error"
    else:
        status = status.lower()
    return msg, status


# ---------- ENDPOINTS DE ACCIÓN ----------

@router.post("/tickets/{ticket_id}/request_info", response_class=HTMLResponse)
async def web_request_info(
    request: Request,
    ticket_id: int,
    dialog: str = Form(...),
    attachments: Optional[List[UploadFile]] = File(None)
):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    attachments_data = await prepare_attachments(attachments)

    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return templates.TemplateResponse(
                "ticket_detail.html",
                {"request": request, "ticket": None, "message": "Ticket no encontrado", "message_type": "error"}
            )

        request_func, _, _ = get_ticket_flow(ticket)
        result = request_func(ticket, dialog, attachments_data)

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dialog": dialog,
            "attachments": attachments_data
        }
        append_local_record(ticket, "local_requests", record)
        session.add(ticket)
        session.commit()
        ticket_data = ticket_to_dict(ticket)

    msg, msg_type = extract_message(result)
    return templates.TemplateResponse(
        "ticket_detail.html",
        {"request": request, "ticket": ticket_data, "current_user": SESSION_USER, "message": msg, "message_type": msg_type}
    )


@router.post("/tickets/{ticket_id}/propose_resolution", response_class=HTMLResponse)
async def web_propose_resolution(
    request: Request,
    ticket_id: int,
    date_restore_service: str = Form(...),
    raw_resolution: str = Form(...),
    dialog: Optional[str] = Form(None),
    certification: Optional[str] = Form(None),
    department: Optional[str] = Form(None),
    raw_real_tipification: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = File(None)
):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    attachments_data = await prepare_attachments(attachments)
    date_obj = datetime.fromisoformat(date_restore_service)

    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return templates.TemplateResponse(
                "ticket_detail.html",
                {"request": request, "ticket": None, "message": "Ticket no encontrado", "message_type": "error"}
            )

        _, propose_func, _ = get_ticket_flow(ticket)
        result = propose_func(ticket, date_obj, raw_resolution, dialog, attachments_data,
                              certification, department, raw_real_tipification)

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "raw_resolution": raw_resolution,
            "dialog": dialog,
            "attachments": attachments_data
        }
        append_local_record(ticket, "local_resolutions", record)
        session.add(ticket)
        session.commit()
        ticket_data = ticket_to_dict(ticket)

    msg, msg_type = extract_message(result)
    return templates.TemplateResponse(
        "ticket_detail.html",
        {"request": request, "ticket": ticket_data, "current_user": SESSION_USER, "message": msg, "message_type": msg_type}
    )


@router.post("/tickets/{ticket_id}/send_report", response_class=HTMLResponse)
async def web_send_report(
    request: Request,
    ticket_id: int,
    dialog: str = Form(...),
    attachments: Optional[List[UploadFile]] = File(None)
):
    if not SESSION_USER:
        return RedirectResponse("/web/login")

    attachments_data = await prepare_attachments(attachments)

    with Session(engine) as session:
        ticket = session.get(Ticket, ticket_id)
        if not ticket:
            return templates.TemplateResponse(
                "ticket_detail.html",
                {"request": request, "ticket": None, "message": "Ticket no encontrado", "message_type": "error"}
            )

        _, _, send_func = get_ticket_flow(ticket)
        result = send_func(ticket, dialog, attachments_data)

        record = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "dialog": dialog,
            "attachments": attachments_data
        }
        append_local_record(ticket, "local_reports", record)
        session.add(ticket)
        session.commit()
        ticket_data = ticket_to_dict(ticket)

    msg, msg_type = extract_message(result)
    return templates.TemplateResponse(
        "ticket_detail.html",
        {"request": request, "ticket": ticket_data, "current_user": SESSION_USER, "message": msg, "message_type": msg_type}
    )


# ---------- HELPER: PREPARAR ADJUNTOS ----------

async def prepare_attachments(attachments: Optional[List[UploadFile]], ticket_id: int = None):
    """Convierte los UploadFile a dict con filename + ruta accesible"""
    if not attachments:
        return []

    files_data = []
    for f in attachments:
        content = await f.read()

        # Guardar archivo físicamente
        if ticket_id:
            upload_dir = os.path.join("uploads", str(ticket_id))
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, f.filename)
            with open(filepath, "wb") as file_out:
                file_out.write(content)

        files_data.append({
            "filename": f.filename,
            "path": f"/web/files/{ticket_id}/{f.filename}"
        })

    return files_data




