# -*- coding: utf-8 -*-
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header

# Función para limpiar las cadenas y eliminar saltos de línea problemáticos
def limpiar_texto(texto):
    if texto is not None:
        return texto.replace('\n', ' ').replace('\r', ' ')
    return ""

# Función general para enviar un correo electrónico
def enviar_notificacion(destinatario, asunto, cuerpo):
    try:
        # Configuración del servidor SMTP (Ejemplo con Gmail)
        smtp_server = 'smtp.gmail.com'
        smtp_port = 587
        sender_email = 'psvpasuva@gmail.com'
        password = 'Atenea2024'

        # Crear el mensaje
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = destinatario
        # Se utiliza Header para codificar el asunto en UTF-8
        msg['Subject'] = str(Header(asunto, 'utf-8'))

        # Se adjunta el cuerpo especificando 'utf-8'
        msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))

        # Establecer conexión con el servidor SMTP y enviar el correo
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()  # Activar encriptación
        server.login(sender_email, password)
        text = msg.as_string()
        server.sendmail(sender_email, destinatario, text)
        print(f"Correo enviado exitosamente a {destinatario}")
    except Exception as e:
        print(f"Error al enviar correo: {e}")
    finally:
        server.quit()


# 1. Correo de oferta añadida por el comercial para un apartment_id específico
def correo_oferta_comercial(destinatario, apartment_id, descripcion_oferta):
    asunto = f"Oferta realizada para el apartamento {apartment_id}"
    descripcion_oferta = limpiar_texto(descripcion_oferta)
    cuerpo = (
        f"Estimado Administrador,\n\n"
        f"El comercial ha realizado una oferta para el apartamento con ID {apartment_id}.\n\n"
        f"Descripción de la oferta:\n{descripcion_oferta}\n\n"
        "Saludos cordiales."
    )
    enviar_notificacion(destinatario, asunto, cuerpo)


# 2. Correo de viabilidad añadida por el comercial con ticket XXXXX
def correo_viabilidad_comercial(destinatario, ticket_id, descripcion_viabilidad):
    asunto = f"Viabilidad realizada con ticket {ticket_id}"
    descripcion_viabilidad = limpiar_texto(descripcion_viabilidad)
    cuerpo = (
        f"Estimado Administrador,\n\n"
        f"El comercial ha realizado una viabilidad para el ticket {ticket_id}.\n\n"
        f"Descripción de la viabilidad:\n{descripcion_viabilidad}\n\n"
        "Saludos cordiales."
    )
    enviar_notificacion(destinatario, asunto, cuerpo)


# 3. Correo de viabilidad completada por la administración con ticket XXXX
def correo_viabilidad_administracion(destinatario, ticket_id, descripcion_viabilidad):
    asunto = f"Viabilidad completada para el ticket {ticket_id}"
    descripcion_viabilidad = limpiar_texto(descripcion_viabilidad)
    cuerpo = (
        f"Estimado Comercial,\n\n"
        f"La administración ha completado la viabilidad para el ticket {ticket_id}.\n\n"
        f"Descripción de la viabilidad:\n{descripcion_viabilidad}\n\n"
        "Saludos cordiales."
    )
    enviar_notificacion(destinatario, asunto, cuerpo)
