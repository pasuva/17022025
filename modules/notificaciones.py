# -*- coding: utf-8 -*-
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from modules import plantilla_email
from datetime import datetime

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

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
        msg['From'] = 'noreply.verdetuoperador@gmail.com'  # Correo remitente
        msg['To'] = destinatario
        msg['Subject'] = str(Header(asunto, 'utf-8'))  # Codificación del asunto en UTF-8
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))  # Se adjunta el contenido en HTML

        # Establecer conexión y enviar correo
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Activar encriptación
        server.login('noreply.verdetuoperador@gmail.com', 'mwht uuwd slzc renq')  # Datos SMTP
        server.sendmail('noreply.verdetuoperador@gmail.com', destinatario, msg.as_string())  # Enviar correo
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

def correo_asignacion_administracion2(destinatario, municipio_sel, poblacion_sel, descripcion_asignacion):
    asunto = f"Asignación realizada para {municipio_sel} - {poblacion_sel}"
    descripcion_asignacion = limpiar_texto(descripcion_asignacion)
    contenido = {
        "mensaje": f"El gestor asignó la zona <strong>{municipio_sel} - {poblacion_sel}</strong>.",
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

def correo_desasignacion_administracion2(destinatario, municipio_sel, poblacion_sel, descripcion_desasignacion):
    asunto = f"Desasignación realizada para {municipio_sel} - {poblacion_sel}"
    descripcion_desasignacion = limpiar_texto(descripcion_desasignacion)
    contenido = {
        "mensaje": f"El gestor desasignó la zona <strong>{municipio_sel} - {poblacion_sel}</strong>. ",
        "Descripción de la desasignación": descripcion_desasignacion
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 6. Correo de gestion de usuarios
def correo_usuario(destinatario, asunto, mensaje):
    """
    Función para enviar un correo a un usuario específico con un asunto y mensaje
    proporcionados. Utiliza el sistema de notificaciones del proyecto.
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

# 7. Correo de notificación de nuevas zonas asignadas tras carga masiva
def correo_nuevas_zonas_comercial(destinatario, nombre_comercial, total_nuevos, poblaciones_nuevas):
    asunto = f"📍 Nuevas zonas asignadas en la última actualización"
    poblaciones_nuevas = limpiar_texto(poblaciones_nuevas)
    contenido = {
        "mensaje": f"Hola <strong>{nombre_comercial}</strong>, se han cargado nuevos datos en el sistema.",
        "Descripción": f"""
        - 🔢 Nuevos registros asignados: <strong>{total_nuevos}</strong><br>
        - 🏘️ Nuevas poblaciones: <strong>{poblaciones_nuevas}</strong><br><br>
        Revisa tu panel de usuario para ver más detalles.
        """
    }
    enviar_notificacion(destinatario, asunto, contenido)

def correo_confirmacion_viab_admin(destinatario, id_viab, comercial_orig):
    asunto = f"✔️ Viabilidad {id_viab} confirmada"
    contenido = {
        "mensaje": (
            f"La viabilidad <strong>#{id_viab}</strong>, enviada por "
            f"<strong>{comercial_orig}</strong>, ha sido confirmada por el Gestor Comercial."
        ),
        "Descripción": (
            "Ya está lista para continuar su flujo de trabajo."
        )
    }
    enviar_notificacion(destinatario, asunto, contenido)


def correo_reasignacion_saliente(destinatario, id_viab, nuevo_comercial):
    asunto = f"⚠️ Viabilidad {id_viab} reasignada"
    contenido = {
        "mensaje": (
            f"La viabilidad <strong>#{id_viab}</strong> ha sido reasignada a "
            f"<strong>{nuevo_comercial}</strong>."
        ),
        "Descripción": (
            "Ya no estás a cargo de ella. "
            "Si tienes dudas, contacta con administración."
        )
    }
    enviar_notificacion(destinatario, asunto, contenido)


def correo_reasignacion_entrante(destinatario, id_viab, comercial_orig):
    asunto = f"📥 Nueva viabilidad asignada (ID {id_viab})"
    contenido = {
        "mensaje": (
            f"Se te ha asignado la viabilidad <strong>#{id_viab}</strong>."
        ),
        "Descripción": (
            f"Fue reportada originalmente por <strong>{comercial_orig}</strong>."
            "<br>Revisa tu panel para gestionarla."
        )
    }
    enviar_notificacion(destinatario, asunto, contenido)

# 8. Envío manual de presupuesto adjunto
def correo_envio_presupuesto_manual(destinatario, proyecto, mensaje_usuario, archivo_bytes, nombre_archivo):
    fecha_envio = datetime.now().strftime("%d/%m/%Y")

    asunto = f"Presupuesto enviado: {proyecto}"

    contenido = {
        "mensaje": f"Se ha enviado un presupuesto para el proyecto <strong>{proyecto}</strong>.",
        "Fecha de envío": fecha_envio,
        "Comentario del remitente": mensaje_usuario
    }

    try:
        html_content = plantilla_email.generar_html(asunto, contenido)

        msg = MIMEMultipart()
        msg['From'] = 'noreply.verdetuoperador@gmail.com'
        msg['To'] = destinatario
        msg['Subject'] = str(Header(asunto, 'utf-8'))
        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # Adjuntar el archivo
        part = MIMEApplication(archivo_bytes, Name=nombre_archivo)
        part['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login('noreply.verdetuoperador@gmail.com', 'mwht uuwd slzc renq')
        server.sendmail('noreply.verdetuoperador@gmail.com', destinatario, msg.as_string())
        server.quit()

        print(f"✅ Correo con presupuesto enviado a {destinatario}")
    except Exception as e:
        print(f"❌ Error al enviar correo con presupuesto: {e}")

def correo_nueva_version(destinatario, version, descripcion):
    asunto = f"🚀 Nueva actualización: Versión {version}"
    contenido = {
        "mensaje": (
            f"Se ha publicado una nueva versión <strong>{version}</strong>."
        ),
        "Descripción": (
            f"{descripcion}<br>"
            "Consulta el panel para más detalles."
        )
    }
    enviar_notificacion(destinatario, asunto, contenido)

def correo_asignacion_puntos_existentes(destinatario, nombre_comercial, provincia, municipio, poblacion, nuevos_puntos):
    asunto = f"Se han asignado {nuevos_puntos} nuevos puntos en {municipio} - {poblacion}"
    contenido = {
        "mensaje": (
            f"Se han detectado <strong>{nuevos_puntos}</strong> nuevos puntos en la zona "
            f"<strong>{municipio} - {poblacion} ({provincia})</strong>, "
            f"que han sido asignados automáticamente al comercial <strong>{nombre_comercial}</strong>."
        ),
        "Descripción de la asignación": (
            "Esta asignación corresponde a puntos que estaban en la base de datos pero aún no "
            "habían sido vinculados. Ahora quedan correctamente asociados."
        )
    }
    enviar_notificacion(destinatario, asunto, contenido)

