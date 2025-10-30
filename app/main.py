from fastapi import FastAPI
from app.routes import webhook, tickets, auth, simulate_flow, logs, web
from app.database import init_db
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

app = FastAPI(title="Ticketing Adamo - Ibiocom")

@app.get("/")
def root():
    # Redirige automáticamente a la ruta de login
    return RedirectResponse("/web/login")

@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(webhook.router)
app.include_router(tickets.router)
app.include_router(simulate_flow.router)
app.include_router(logs.router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web.router)