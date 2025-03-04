# -*- coding: utf-8 -*-
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header

from modules import plantilla_email

# Función para limpiar las cadenas y eliminar saltos de línea problemáticos
def limpiar_texto(texto):
    if texto is not None:
        return texto.replace('\n', ' ').replace('\r', ' ')
    return ""

# Función general para enviar un correo electrónico en formato HTML
def enviar_notificacion(destinatario, asunto, contenido):
    try:
        html_content = plantilla_email.generar_html(asunto, contenido)  # Genera el contenido en HTML

        msg = MIMEMultipart()
        msg['From'] = 'psvpasuva@gmail.com'  # Correo remitente
        msg['To'] = destinatario
        msg['Subject'] = str(Header(asunto, 'utf-8'))  # Codificación del asunto en UTF-8
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))  # Se adjunta el contenido en HTML

        # Establecer conexión y enviar correo
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Activar encriptación
        server.login('psvpasuva@gmail.com', 'quhl gvsn nujb sqgm')  # Datos SMTP
        server.sendmail('psvpasuva@gmail.com', destinatario, msg.as_string())  # Enviar correo
        server.quit()

        print(f"✅ Correo enviado exitosamente a {destinatario}")
    except Exception as e:
        print(f"❌ Error al enviar correo: {e}")

# 1. Correo de oferta añadida por el comercial para un apartment_id específico
def correo_oferta_comercial(destinatario, apartment_id, descripcion_oferta):
    asunto = f"Oferta realizada para el apartamento {apartment_id}"
    descripcion_oferta = limpiar_texto(descripcion_oferta)
    contenido = {
        "mensaje": f"El comercial ha realizado una oferta para el apartamento con ID <strong>{apartment_id}</strong>.",
        "Descripción de la oferta": descripcion_oferta
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 2. Correo de viabilidad añadida por el comercial con ticket XXXXX
def correo_viabilidad_comercial(destinatario, ticket_id, descripcion_viabilidad):
    asunto = f"Viabilidad realizada con ticket {ticket_id}"
    descripcion_viabilidad = limpiar_texto(descripcion_viabilidad)
    contenido = {
        "mensaje": f"El comercial ha realizado una viabilidad para el ticket <strong>{ticket_id}</strong>.",
        "Descripción de la viabilidad": descripcion_viabilidad
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 3. Correo de viabilidad completada por la administración con ticket XXXX
def correo_viabilidad_administracion(destinatario, ticket_id, descripcion_viabilidad):
    asunto = f"Viabilidad completada para el ticket {ticket_id}"
    descripcion_viabilidad = limpiar_texto(descripcion_viabilidad)
    contenido = {
        "mensaje": f"La administración ha completado la viabilidad para el ticket <strong>{ticket_id}</strong>.",
        "Descripción de la viabilidad": descripcion_viabilidad
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 4. Correo de asignacion de zona a comercial
def correo_asignacion_administracion(destinatario, municipio_sel, poblacion_sel, descripcion_asignacion):
    asunto = f"Asignación realizada para {municipio_sel} - {poblacion_sel}"
    descripcion_asignacion = limpiar_texto(descripcion_asignacion)
    contenido = {
        "mensaje": f"Se le ha asignado la zona <strong>{municipio_sel} - {poblacion_sel}</strong>. Ya puede "
                   f"comenzar a realizar ofertas en la zona asignada. Entre en su panel de usuario para ver mas detalles.",
        "Descripción de la asignación": descripcion_asignacion
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 5. Correo de desasignacion de zona a comercial
def correo_desasignacion_administracion(destinatario, municipio_sel, poblacion_sel, descripcion_desasignacion):
    asunto = f"Desasignación realizada para {municipio_sel} - {poblacion_sel}"
    descripcion_desasignacion = limpiar_texto(descripcion_desasignacion)
    contenido = {
        "mensaje": f"Se le ha desasignado la zona por errores de asignación u otros motivos <strong>{municipio_sel} - {poblacion_sel}</strong>. "
                   f"Entre en su panel de usuario para ver mas detalles.",
        "Descripción de la desasignación": descripcion_desasignacion
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 6. Correo de gestion de usuarios
def correo_usuario(destinatario, asunto, mensaje):
    """
    Función para enviar un correo a un usuario específico con un asunto y mensaje
    proporcionados. Utiliza el sistema de notificaciones del proyecto.

    :param destinatario: Email del destinatario.
    :param asunto: Asunto del correo.
    :param mensaje: Cuerpo del correo en formato de texto.
    """
    # Limpiar el texto del mensaje para evitar errores en el HTML
    mensaje = limpiar_texto(mensaje)

    # Definir el contenido del correo
    contenido = {
        "mensaje": asunto,
        "Descripción": f"{mensaje}"
    }

    # Llamada a la función que envía la notificación
    enviar_notificacion(destinatario, asunto, contenido)
