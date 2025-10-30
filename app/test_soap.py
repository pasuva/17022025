from app.soap.client import set_trouble_ticket_by_value

payload = {
    "baseTroubleTicketState": "OPENACTIVE",
    "primaryKey": "IB-TEST-001",
    "mirrorKey": "RED-LOCAL-001",
    "dialog": "Prueba de integración local con API Adamo",
    "clearancePerson": "ibiocom"
}

response = set_trouble_ticket_by_value(payload, env="PRE")
print("Respuesta SOAP:", response)
