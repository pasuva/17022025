from flask import Flask, request, render_template_string
import sqlitecloud
from datetime import datetime
import smtplib
from email.message import EmailMessage
from plantilla_email import generar_html
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO

app = Flask(__name__)

DB_PATH = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"

# -------------------- CONEXIÓN A BD --------------------
def get_db_connection():
    conn = sqlitecloud.connect(DB_PATH)
    conn.row_factory = None  # devuelve lista de tuplas
    return conn

# -------------------- VALIDAR TOKEN --------------------
def validar_token(precontrato_id, token):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM precontrato_links
        WHERE precontrato_id = ? AND token = ? AND usado = 0
    """, (precontrato_id, token))
    link = cursor.fetchone()
    conn.close()

    if not link:
        return False, "❌ Enlace no válido o ya utilizado."

    expiracion = datetime.fromisoformat(link[3])
    if datetime.now() > expiracion:
        return False, "⚠️ El enlace ha caducado. Solicita uno nuevo."

    return True, None

# -------------------- GENERAR PDF --------------------
def generar_pdf(precontrato_datos, lineas=[]):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            rightMargin=50, leftMargin=50,
                            topMargin=50, bottomMargin=50)
    elements = []

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='CustomTitle',
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.darkgreen,
        spaceAfter=20
    ))
    styles.add(ParagraphStyle(
        name='CustomHeading',
        fontSize=14,
        leading=18,
        textColor=colors.darkblue,
        spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        name='NormalBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold'
    ))

    # --- TÍTULO ---
    elements.append(Paragraph(f"Precontrato {precontrato_datos['precontrato_id']}", styles['CustomTitle']))
    elements.append(Spacer(1, 12))

    # --- Función auxiliar para crear tabla ---
    def tabla_seccion(titulo, datos):
        elements.append(Paragraph(titulo, styles['CustomHeading']))
        data = [[Paragraph(f"<b>{k}</b>", styles['Normal']), Paragraph(str(v or ''), styles['Normal'])]
                for k, v in datos.items()]
        table = Table(data, colWidths=[150, 350])
        table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 12))

    # --- SECCIONES ---
    tabla_seccion("Datos del Precontrato", {
        "Apartment ID": precontrato_datos["apartment_id"],
        "Tarifa": precontrato_datos["tarifa"],
        "Comercial": precontrato_datos["comercial"],
        "Observaciones": precontrato_datos["observaciones"],
        "Precio (€)": precontrato_datos["precio"],
        "Fecha": precontrato_datos["fecha"],
        "Permanencia": precontrato_datos["permanencia"],
        "Servicio Adicional": precontrato_datos["servicio_adicional"],
    })

    tabla_seccion("Datos del Cliente", {
        "Nombre": precontrato_datos["nombre"],
        "Nombre legal / Razón social": precontrato_datos["nombre_legal"],
        "NIF": precontrato_datos["nif"],
        "CIF": precontrato_datos["cif"],
        "Teléfono 1": precontrato_datos["telefono1"],
        "Teléfono 2": precontrato_datos["telefono2"],
        "Email": precontrato_datos["mail"],
        "Dirección": precontrato_datos["direccion"],
        "CP": precontrato_datos["cp"],
        "Población": precontrato_datos["poblacion"],
        "Provincia": precontrato_datos["provincia"],
        "IBAN": precontrato_datos["iban"],
        "BIC": precontrato_datos["bic"],
        "Firma": precontrato_datos["firma"]
    })

    # --- LÍNEAS ADICIONALES ---
    if lineas:
        for i, l in enumerate(lineas, start=1):
            tabla_seccion(f"Línea adicional {i}", {
                "Tipo": l.get('tipo', ''),
                "Número nuevo": l.get('numero_nuevo_portabilidad', ''),
                "Número a portar": l.get('numero_a_portar', ''),
                "Titular": l.get('titular', ''),
                "DNI": l.get('dni', ''),
                "Operador donante": l.get('operador_donante', ''),
                "ICC": l.get('icc', '')
            })

    # --- PIE ---
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        "Verdetuoperador.com · atencioncliente@verdetuoperador.com",
        styles['Normal']
    ))

    # ✅ Generar PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


# -------------------- ENVIAR CORREO --------------------
def enviar_correo_pdf(precontrato_datos, archivos=[], lineas=[]):
    # Generar PDF
    pdf_buffer = generar_pdf(precontrato_datos, lineas=lineas)

    # Asunto del correo
    asunto = f"Precontrato completado: {precontrato_datos['precontrato_id']}"

    # Contenido del correo (para versión HTML)
    contenido = {
        "mensaje": "El cliente ha completado el formulario de precontrato. Datos resumidos:",
        "Precontrato": {
            "Apartment ID": precontrato_datos["apartment_id"],
            "Tarifa": precontrato_datos["tarifa"],
            "Comercial": precontrato_datos["comercial"],
            "Observaciones": precontrato_datos["observaciones"],
            "Precio": precontrato_datos["precio"],
            "Fecha": precontrato_datos["fecha"],
            "Permanencia": precontrato_datos["permanencia"],
            "Servicio Adicional": precontrato_datos["servicio_adicional"]
        },
        "Cliente": {
            "Nombre": precontrato_datos["nombre"],
            "Nombre legal": precontrato_datos["nombre_legal"],
            "NIF": precontrato_datos["nif"],
            "CIF": precontrato_datos["cif"],
            "Teléfono 1": precontrato_datos["telefono1"],
            "Teléfono 2": precontrato_datos["telefono2"],
            "Email": precontrato_datos["mail"],
            "Dirección": precontrato_datos["direccion"],
            "CP": precontrato_datos["cp"],
            "Población": precontrato_datos["poblacion"],
            "Provincia": precontrato_datos["provincia"],
            "IBAN": precontrato_datos["iban"],
            "BIC": precontrato_datos["bic"],
            "Firma": precontrato_datos["firma"]
        },
        "Líneas adicionales": {
            f"Línea {i+1}": (
                f"Tipo: {l['tipo']}, Número nuevo: {l['numero_nuevo_portabilidad']}, "
                f"Número a portar: {l['numero_a_portar']}, Titular: {l['titular']}, "
                f"DNI: {l['dni']}, Operador: {l['operador_donante']}, ICC: {l['icc']}"
            )
            for i, l in enumerate(lineas)
        }
    }

    # Generar cuerpo HTML
    html_body = generar_html(asunto, contenido)

    # Crear mensaje
    msg = EmailMessage()
    msg['Subject'] = asunto
    msg['From'] = "noreply.verdetuoperador@gmail.com"

    # ✅ Destinatarios múltiples
    destinatarios = [
        "patricia@verdetuoperador.com",
        "bo@verdetuoperador.com",
        "jpterrel@verdetuoperador.com"
    ]
    msg['To'] = ", ".join(destinatarios)

    # Cuerpo del mensaje
    msg.set_content("Tu cliente ha completado el formulario. Ver versión HTML para más detalles.")
    msg.add_alternative(html_body, subtype='html')

    # Adjuntar PDF principal
    msg.add_attachment(
        pdf_buffer.read(),
        maintype='application',
        subtype='pdf',
        filename=f"Precontrato_{precontrato_datos['precontrato_id']}.pdf"
    )

    # Adjuntar otros archivos subidos por el cliente
    for archivo in archivos:
        nombre = archivo.filename
        tipo = archivo.mimetype.split('/')
        maintype = tipo[0]
        subtype = tipo[1] if len(tipo) > 1 else 'octet-stream'
        msg.add_attachment(archivo.read(), maintype=maintype, subtype=subtype, filename=nombre)

    # Enviar correo
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login("noreply.verdetuoperador@gmail.com", "mwht uuwd slzc renq")
        smtp.send_message(msg)

# -------------------- RUTA DEL FORMULARIO --------------------
@app.route("/formulario_cliente", methods=["GET", "POST"])
def formulario_cliente():
    precontrato_id = request.args.get("id")
    token = request.args.get("token")

    if not precontrato_id or not token:
        return "❌ Faltan parámetros en el enlace.", 400

    valido, mensaje = validar_token(precontrato_id, token)
    if not valido:
        return mensaje, 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM precontratos WHERE id = ?", (int(precontrato_id),))
    precontrato = cursor.fetchone()
    conn.close()

    if not precontrato:
        return "❌ No se encontró el precontrato asociado a este enlace.", 404

    if request.method == "POST":
        # -------------------- GUARDAR DATOS --------------------
        nombre = request.form.get("nombre")
        nif = request.form.get("nif")
        telefono1 = request.form.get("telefono1")
        telefono2 = request.form.get("telefono2")
        mail = request.form.get("mail")
        direccion = request.form.get("direccion")
        cp = request.form.get("cp")
        poblacion = request.form.get("poblacion")
        provincia = request.form.get("provincia")
        iban = request.form.get("iban")
        bic = request.form.get("bic")
        firma = request.form.get("firma")
        nombre_legal = request.form.get("nombre_legal")
        cif = request.form.get("cif")

        if not nombre or not nif or not firma:
            return "⚠️ Por favor, completa los campos obligatorios (nombre, NIF y firma).", 400

        archivos = request.files.getlist("archivos[]")

        # -------------------- LÍNEAS PRINCIPALES --------------------
        movil = {
            "precontrato_id": int(precontrato_id),  # obligatorio
            "tipo": "movil",  # debe coincidir con la constraint de la tabla
            "numero_nuevo_portabilidad": request.form.get("movil_numero_nuevo_portabilidad"),
            "numero_a_portar": request.form.get("movil_numero_a_portar"),
            "titular": request.form.get("movil_titular"),
            "dni": request.form.get("movil_dni"),
            "operador_donante": request.form.get("movil_operador_donante"),
            "icc": request.form.get("movil_icc")
        }

        fija = {
            "precontrato_id": int(precontrato_id),  # obligatorio
            "tipo": "fija",  # debe coincidir con la constraint de la tabla
            "numero_nuevo_portabilidad": request.form.get("fija_numero_nuevo_portabilidad"),
            "numero_a_portar": request.form.get("fija_numero_a_portar"),
            "titular": request.form.get("fija_titular"),
            "dni": request.form.get("fija_dni"),
            "operador_donante": request.form.get("fija_operador_donante"),
            "icc": request.form.get("fija_icc")
        }

        # -------------------- GUARDAR LÍNEAS ADICIONALES --------------------
        lineas_adicionales = []
        for i in range(1,6):
            tipo = request.form.get(f"tipo_{i}")
            if tipo:
                linea = {
                    "precontrato_id": precontrato_id,
                    "tipo": tipo,
                    "numero_nuevo_portabilidad": request.form.get(f"numero_nuevo_{i}"),
                    "numero_a_portar": request.form.get(f"numero_a_portar_{i}"),
                    "titular": request.form.get(f"titular_{i}"),
                    "dni": request.form.get(f"dni_{i}"),
                    "operador_donante": request.form.get(f"operador_donante_{i}"),
                    "icc": request.form.get(f"icc_{i}")
                }
                lineas_adicionales.append(linea)

        # -------------------- AGREGAR LÍNEAS PRINCIPALES AL INICIO --------------------
        lineas_adicionales.insert(0, movil)
        lineas_adicionales.insert(1, fija)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE precontratos
                SET nombre=?, nombre_legal=?, cif=?, nif=?, telefono1=?, telefono2=?, mail=?, direccion=?,
                    cp=?, poblacion=?, provincia=?, iban=?, bic=?, firma=?
                WHERE id=?
            """, (
                nombre, nombre_legal, cif, nif, telefono1, telefono2, mail, direccion,
                cp, poblacion, provincia, iban, bic, firma, int(precontrato_id)
            ))

            cursor.execute("""
                UPDATE precontrato_links
                SET usado = 1
                WHERE precontrato_id = ? AND token = ?
            """, (int(precontrato_id), token))

            # Guardar líneas adicionales en BD
            for linea in lineas_adicionales:
                cursor.execute("""
                    INSERT INTO lineas (precontrato_id, tipo, numero_nuevo_portabilidad, numero_a_portar,
                                        titular, dni, operador_donante, icc)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (linea["precontrato_id"], linea["tipo"], linea["numero_nuevo_portabilidad"],
                      linea["numero_a_portar"], linea["titular"], linea["dni"],
                      linea["operador_donante"], linea["icc"]))

            conn.commit()
            conn.close()

            # -------------------- GENERAR PDF Y ENVIAR CORREO --------------------
            datos_pdf = {
                "precontrato_id": precontrato[23],
                "apartment_id": precontrato[1],
                "tarifa": precontrato[2],
                "comercial": precontrato[5],
                "observaciones": precontrato[3],
                "precio": precontrato[4],
                "fecha": precontrato[19],
                "permanencia": precontrato[21],
                "servicio_adicional": precontrato[22],
                "nombre": nombre,
                "nombre_legal": nombre_legal,
                "cif": cif,
                "nif": nif,
                "telefono1": telefono1,
                "telefono2": telefono2,
                "mail": mail,
                "direccion": direccion,
                "cp": cp,
                "poblacion": poblacion,
                "provincia": provincia,
                "iban": iban,
                "bic": bic,
                "firma": firma
            }

            try:
                enviar_correo_pdf(datos_pdf, archivos=archivos, lineas=lineas_adicionales)
            except Exception as e:
                print(f"⚠️ No se pudo enviar el correo: {e}")

            return "✅ ¡Formulario completado correctamente! Gracias por enviar tus datos."

        except Exception as e:
            return f"❌ Error al guardar tus datos: {e}", 500

    # -------------------- FORMULARIO HTML CON BOOTSTRAP Y ACORDEÓN --------------------
    html_form = f"""
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/formulario.css') }}">
    <div class="container mt-4 mb-5">
        <h2 class="mb-4">Formulario de Cliente – Precontrato {precontrato[23]}</h2>
        <form method="POST" enctype="multipart/form-data" class="needs-validation" novalidate>
            <!-- Datos bloqueados -->
            <div class="row mb-3">
                <div class="col-md-4"><label class="form-label">Apartment ID:</label><input type="text" class="form-control" value="{precontrato[1]}" disabled></div>
                <div class="col-md-4"><label class="form-label">Tarifa:</label><input type="text" class="form-control" value="{precontrato[2]}" disabled></div>
                <div class="col-md-4"><label class="form-label">Comercial:</label><input type="text" class="form-control" value="{precontrato[5]}" disabled></div>
            </div>
            <div class="mb-3"><label class="form-label">Observaciones:</label><textarea class="form-control" rows="2" disabled>{precontrato[3]}</textarea></div>
            <div class="row mb-3">
                <div class="col-md-4"><label class="form-label">Precio (€):</label><input type="text" class="form-control" value="{precontrato[4]}" disabled></div>
                <div class="col-md-4"><label class="form-label">Fecha:</label><input type="text" class="form-control" value="{precontrato[19]}" disabled></div>
                <div class="col-md-4"><label class="form-label">Permanencia (meses):</label><input type="text" class="form-control" value="{precontrato[21]}" disabled></div>
            </div>
            <div class="mb-3"><label class="form-label">Servicio Adicional:</label><textarea class="form-control" rows="2" disabled>{precontrato[22]}</textarea></div>
            <hr>
            <!-- Datos editables -->
            <div class="row mb-3">
                <div class="col-md-6">
                    <label class="form-label">Nombre completo*:</label>
                    <input type="text" name="nombre" class="form-control" value="{precontrato[6] or ''}" required>
                    <div class="invalid-feedback">Por favor, introduce tu nombre completo.</div>
                </div>
                <div class="col-md-6">
                    <label class="form-label">NIF / DNI*:</label>
                    <input type="text" name="nif" class="form-control" value="{precontrato[9] or ''}" required pattern="^[0-9]{{8}}[A-Za-z]$"  title="Formato NIF/DNI válido">
                    <div class="invalid-feedback">Introduce un NIF/DNI válido.</div>
                </div>
            </div>
            <div class="row mb-3">
                <div class="col-md-6">
                    <label class="form-label">Nombre legal / Razón social:</label>
                    <input type="text" name="nombre_legal" class="form-control" value="{precontrato[7] or ''}">
                </div>
                <div class="col-md-6">
                    <label class="form-label">CIF:</label>
                    <input type="text" name="cif" class="form-control" value="{precontrato[8] or ''}" pattern="^[A-Za-z]\d{{7}}[A-Za-z0-9]$" title="Formato CIF válido">
                    <div class="invalid-feedback">Introduce un CIF válido (letra, 7 números y letra final).</div>
                </div>
            </div>
            <div class="row mb-3">
                <div class="col-md-6">
                    <label class="form-label">Teléfono principal*:</label>
                    <input type="text" name="telefono1" class="form-control" value="{precontrato[10] or ''}" required pattern="\\+?\\d{{9,15}}" title="Teléfono válido, 9-15 dígitos, opcional + al inicio">
                    <div class="invalid-feedback">Introduce un Teléfono válido.</div>
                </div>
                <div class="col-md-6">
                    <label class="form-label">Teléfono alternativo:</label>
                    <input type="text" name="telefono2" class="form-control" value="{precontrato[11] or ''}" pattern="\\+?\\d{{9,15}}" title="Teléfono válido, 9-15 dígitos, opcional + al inicio">
                    <div class="invalid-feedback">Introduce un Teléfono válido.</div>
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Email*:</label>
                <input type="email" name="mail" class="form-control" value="{precontrato[12] or ''}" required>
                <div class="invalid-feedback">Introduce email válido.</div>
            </div>
            <div class="mb-3">
                <label class="form-label">Dirección*:</label>
                <input type="text" name="direccion" class="form-control" value="{precontrato[13] or ''}" required>
                <div class="invalid-feedback">Introduce una dirección válida.</div>
            </div>
            <div class="row mb-3">
                <div class="col-md-4">
                    <label class="form-label">Código Postal*:</label>
                    <input type="text" name="cp" class="form-control" value="{precontrato[14] or ''}" required pattern="\\d{{5}}" title="Código postal de 5 dígitos">
                    <div class="invalid-feedback">Introduce un código postal válido.</div>
                </div>
                <div class="col-md-4">
                    <label class="form-label">Población*:</label>
                    <input type="text" name="poblacion" class="form-control" value="{precontrato[15] or ''}" required>
                    <div class="invalid-feedback">Introduce una población válida.</div>
                </div>
                <div class="col-md-4">
                    <label class="form-label">Provincia*:</label>
                    <input type="text" name="provincia" class="form-control" value="{precontrato[16] or ''}" required>
                    <div class="invalid-feedback">Introduce una provincia válida.</div>
                </div>
            </div>
            <div class="row mb-3">
                <div class="col-md-6">
                    <label class="form-label">IBAN*:</label>
                    <input type="text" name="iban" class="form-control" value="{precontrato[17] or ''}" required pattern="[A-Z]{{2}}\\d{{22}}" title="IBAN válido, 2 letras seguidas de 22 números">
                    <div class="invalid-feedback">Introduce un IBAN válido.</div>
                </div>
                <div class="col-md-6">
                    <label class="form-label">BIC:</label>
                    <input type="text" name="bic" class="form-control" value="{precontrato[18] or ''}">
                </div>
            </div>
            <div class="mb-3">
                <label class="form-label">Adjuntar documentos* (DNI, fotos, etc.)</label>
                <input type="file" name="archivos[]" class="form-control" required multiple accept=".pdf,.png,.jpg,.jpeg">
                <div class="invalid-feedback">Introduce documentación válida.</div>
            </div>
            <div class="mb-4">
                <label class="form-label">Firma*:</label>
                <input type="text" name="firma" class="form-control" value="" required>
            </div>

            
            <!-- Línea Móvil principal -->
            <h5>Línea Móvil principal</h5>
            <div class="row mb-3">
                <div class="col-md-4"><label>Número nuevo / portabilidad:</label><input type="text" name="movil_numero_nuevo_portabilidad" class="form-control"></div>
                <div class="col-md-4"><label>Número a portar:</label><input type="text" name="movil_numero_a_portar" class="form-control"></div>
                <div class="col-md-4"><label>Titular:</label><input type="text" name="movil_titular" class="form-control"></div>
                <div class="col-md-4"><label>DNI:</label><input type="text" name="movil_dni" class="form-control"></div>
                <div class="col-md-4"><label>Operador donante:</label><input type="text" name="movil_operador_donante" class="form-control"></div>
                <div class="col-md-4"><label>ICC:</label><input type="text" name="movil_icc" class="form-control"></div>
            </div>
            
            <!-- Línea Fija principal -->
            <h5>Línea Fija principal</h5>
            <div class="row mb-3">
                <div class="col-md-4"><label>Número nuevo / portabilidad:</label><input type="text" name="fija_numero_nuevo_portabilidad" class="form-control"></div>
                <div class="col-md-4"><label>Número a portar:</label><input type="text" name="fija_numero_a_portar" class="form-control"></div>
                <div class="col-md-4"><label>Titular:</label><input type="text" name="fija_titular" class="form-control"></div>
                <div class="col-md-4"><label>DNI:</label><input type="text" name="fija_dni" class="form-control"></div>
                <div class="col-md-4"><label>Operador donante:</label><input type="text" name="fija_operador_donante" class="form-control"></div>
                <div class="col-md-4"><label>ICC:</label><input type="text" name="fija_icc" class="form-control"></div>
            </div>
            
            <!-- ACORDEÓN LÍNEAS ADICIONALES -->
            <div class="accordion mb-4" id="lineasAdicionales">
                {"".join([f'''
                <div class="accordion-item">
                    <h2 class="accordion-header" id="heading{i}">
                      <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapse{i}" aria-expanded="false" aria-controls="collapse{i}">
                        Línea adicional {i}
                      </button>
                    </h2>
                    <div id="collapse{i}" class="accordion-collapse collapse" aria-labelledby="heading{i}" data-bs-parent="#lineasAdicionales">
                      <div class="accordion-body">
                        <div class="mb-2"><label class="form-label">Tipo de línea:</label>
                          <select name="tipo_{i}" class="form-select">
                            <option value="">Selecciona</option>
                            <option value="movil_adicional">Móvil adicional</option>
                            <option value="fijo_adicional">Fijo adicional</option>
                          </select>
                        </div>
                        <div class="mb-2"><label class="form-label">Número nuevo / portabilidad:</label><input type="text" name="numero_nuevo_{i}" class="form-control"></div>
                        <div class="mb-2"><label class="form-label">Número a portar:</label><input type="text" name="numero_a_portar_{i}" class="form-control"></div>
                        <div class="mb-2"><label class="form-label">Titular:</label><input type="text" name="titular_{i}" class="form-control"></div>
                        <div class="mb-2"><label class="form-label">DNI:</label><input type="text" name="dni_{i}" class="form-control"></div>
                        <div class="mb-2"><label class="form-label">Operador donante:</label><input type="text" name="operador_donante_{i}" class="form-control"></div>
                        <div class="mb-2"><label class="form-label">ICC:</label><input type="text" name="icc_{i}" class="form-control"></div>
                      </div>
                    </div>
                </div>
                ''' for i in range(1,6)])}
            </div>

            <div class="d-grid mt-4">
              <button type="submit" class="btn btn-success btn-lg">
                📤 Enviar formulario
              </button>
            </div>
            <p class="mt-2 text-muted"><small>* Campos obligatorios</small></p>
        </form>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
    // Activar validación de Bootstrap 5
    (function () {{
      'use strict'
      const forms = document.querySelectorAll('.needs-validation')
      Array.prototype.slice.call(forms).forEach(function (form) {{
        form.addEventListener('submit', function (event) {{
          if (!form.checkValidity()) {{
            event.preventDefault()
            event.stopPropagation()
          }}
          form.classList.add('was-validated')
        }}, false)
      }})
    }})();
    </script>
    """

    return render_template_string(html_form)


if __name__ == "__main__":
    app.run(debug=True)



