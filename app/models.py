from datetime import datetime
from sqlmodel import SQLModel, Field, JSON
from typing import Optional

class Ticket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    primary_key: str = Field(max_length=50)
    mirror_key: Optional[str] = Field(default=None, max_length=50)
    state: Optional[str] = Field(default=None, max_length=50)
    dialog: Optional[str] = None  # Datos de Adamo
    clearance_person: Optional[str] = Field(default="ibiocom", max_length=50)
    ticket_type: str = Field(default="ftth_cliente", max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # NUEVOS CAMPOS PARA DATOS ENVIADOS POR NOSOTROS
    local_requests: Optional[str] = None  # JSON de request_info enviadas
    local_resolutions: Optional[str] = None  # JSON de resolutions enviadas
    local_reports: Optional[str] = None  # JSON de reportes enviados

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: str = Field(default="tecnico")
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Log(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_type: str = Field(max_length=50)  # Ej: 'webhook_in', 'soap_out', 'user_action'
    ticket_primary_key: Optional[str] = None
    user_email: Optional[str] = None
    direction: Optional[str] = None  # 'in' o 'out'
    payload: Optional[str] = None  # JSON serializado o texto
    status: Optional[str] = None  # success, error, pending
    created_at: datetime = Field(default_factory=datetime.utcnow)