from fastapi import APIRouter, Request
from app.services.workflows_flow import (
    request_additional_info,
    propose_resolution,
    send_report,
)

router = APIRouter(prefix="/workflows", tags=["Workflows"])

@router.post("/request_info")
def workflows_request_info(request: Request):
    """
    Endpoint de ejemplo: solicita información adicional (flujo Workflows)
    """
    result = request_additional_info(None, "Petición de información de ejemplo", None)
    return {"status": "ok", "detail": result}


@router.post("/propose_resolution")
def workflows_propose_resolution(request: Request):
    """
    Endpoint de ejemplo: propone resolución (flujo Workflows)
    """
    result = propose_resolution(None, None, "Resolución simulada", "Texto de ejemplo", None, None, None, None)
    return {"status": "ok", "detail": result}


@router.post("/send_report")
def workflows_send_report(request: Request):
    """
    Endpoint de ejemplo: envía reporte (flujo Workflows)
    """
    result = send_report(None, "Reporte simulado de trabajo programado", None)
    return {"status": "ok", "detail": result}
