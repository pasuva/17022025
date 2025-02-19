import streamlit as st
import pandas as pd
import io  # Necesario para trabajar con flujos de bytes
import sqlite3
import datetime
import bcrypt
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DB_PATH = "../data/usuarios.db"


def obtener_conexion():
    """Retorna una nueva conexión a la base de datos."""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None


def cargar_usuarios():
    """Carga los usuarios desde la base de datos."""
    conn = obtener_conexion()  # Abre la conexión
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, username, role FROM usuarios")
            usuarios = cursor.fetchall()
            return usuarios
        except sqlite3.Error as e:
            print(f"Error al cargar los usuarios: {e}")
            return []
        finally:
            conn.close()  # Cierra la conexión
    else:
        return []  # Retorna una lista vacía si no pudo conectarse


# Función para agregar un nuevo usuario
def agregar_usuario(username, rol, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        cursor.execute("INSERT INTO usuarios (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, rol))
        conn.commit()
        st.success(f"Usuario '{username}' creado con éxito.")
    except sqlite3.IntegrityError:
        st.error(f"El usuario '{username}' ya existe.")
    finally:
        conn.close()


# Función para editar un usuario existente
def editar_usuario(id, username, rol, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode() if password else None

    if password:
        cursor.execute("UPDATE usuarios SET username = ?, role = ?, password = ? WHERE id = ?",
                       (username, rol, hashed_pw, id))
    else:
        cursor.execute("UPDATE usuarios SET username = ?, role = ? WHERE id = ?", (username, rol, id))

    conn.commit()
    conn.close()
    st.success(f"Usuario con ID {id} actualizado correctamente.")


# Función para eliminar un usuario
def eliminar_usuario(id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    st.success(f"Usuario con ID {id} eliminado correctamente.")


# Función para generar PDF con los datos del informe
def generar_pdf(df, encabezado_titulo, mensaje_intro, fecha_generacion, pie_de_pagina):
    # Crear un archivo PDF en memoria
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    # Título del informe
    c.setFont("Helvetica-Bold", 16)
    c.drawString(30, 750, encabezado_titulo)

    # Mensaje introductorio
    c.setFont("Helvetica", 12)
    c.drawString(30, 730, mensaje_intro)

    # Fecha de generación
    c.setFont("Helvetica", 10)
    c.drawString(30, 710, f"Fecha de generación: {fecha_generacion}")

    # Añadir datos del informe (limitado a la primera página)
    y_position = 690
    c.setFont("Helvetica", 8)
    for index, row in df.iterrows():
        y_position -= 10
        if y_position < 40:
            c.showPage()  # Crear nueva página si es necesario
            c.setFont("Helvetica", 8)
            y_position = 750

        c.drawString(30, y_position, str(row.tolist()))

    # Pie de página
    c.setFont("Helvetica", 10)
    c.drawString(30, 30, pie_de_pagina)

    c.save()
    buffer.seek(0)
    return buffer


# Función principal de la app (Dashboard de administración)
def admin_dashboard():
    """Panel del administrador."""
    st.set_page_config(page_title="Panel de Administración", page_icon="📊", layout="wide")

    # Personalizar la barra lateral
    st.sidebar.title("📊 Panel de Administración")
    st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**! (Admin)")
    st.sidebar.markdown("---")

    # Opciones de navegación con iconos
    opcion = st.sidebar.radio(
        "Selecciona una opción:",
        ("📈 Ver Datos", "📊 Ofertas Comerciales", "📤 Cargar Nuevos Datos", "👥 Gestionar Usuarios", "📑 Generador de informes", "📜 Trazabilidad y logs", "⚙️ Ajustes"),
        index=0,
        key="menu",
    )

    # Botón de Cerrar sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Opción: Visualizar datos de la tabla datos_uis
    if opcion == "📈 Ver Datos":
        st.header("📊 Visualizar y gestionar datos (Datos UIS)")
        st.write("Aquí puedes cargar y gestionar la base de datos de datos_uis.")

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("Cargando datos..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)
                if 'datos_uis' not in tables['name'].values:
                    st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM datos_uis"
                data = pd.read_sql(query, conn)
                conn.close()
                if data.empty:
                    st.error("❌ No se encontraron datos en la base de datos.")
                    return
            except Exception as e:
                st.error(f"❌ Error al cargar datos de la base de datos: {e}")
                return

        for col in data.select_dtypes(include=["object"]).columns:
            data[col] = data[col].replace({'true': True, 'false': False})
            data[col] = pd.to_numeric(data[col], errors='ignore')

        if data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            data = data.loc[:, ~data.columns.duplicated()]

        st.session_state["df"] = data
        st.write("Filtra las columnas del dataframe:")
        columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(),
                                  default=data.columns.tolist())
        st.dataframe(data[columnas], use_container_width=True)

        st.subheader("Selecciona el formato para la descarga:")
        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"])
        if download_format == "Excel":
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name='Datos')
            towrite.seek(0)
            with st.spinner("Preparando archivo Excel..."):
                st.download_button(
                    label="📥 Descargar Excel",
                    data=towrite,
                    file_name="datos.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        elif download_format == "CSV":
            csv = data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="datos.csv",
                    mime="text/csv"
                )

    # Opción: Visualizar datos de la tabla ofertas_comercial
    elif opcion == "📊 Ofertas Comerciales":
        st.header("📊 Visualizar Ofertas Comerciales")
        st.write("Aquí puedes ver las ofertas comerciales registradas.")

        if "df" in st.session_state:
            del st.session_state["df"]

        with st.spinner("Cargando ofertas comerciales..."):
            try:
                conn = sqlite3.connect("data/usuarios.db")
                query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
                tables = pd.read_sql(query_tables, conn)
                if 'ofertas_comercial' not in tables['name'].values:
                    st.error("❌ La tabla 'ofertas_comercial' no se encuentra en la base de datos.")
                    conn.close()
                    return
                query = "SELECT * FROM ofertas_comercial"
                data = pd.read_sql(query, conn)
                conn.close()
                if data.empty:
                    st.error("❌ No se encontraron ofertas comerciales en la base de datos.")
                    return
            except Exception as e:
                st.error(f"❌ Error al cargar ofertas comerciales de la base de datos: {e}")
                return

        if data.columns.duplicated().any():
            st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
            data = data.loc[:, ~data.columns.duplicated()]

        st.session_state["df"] = data
        st.write("Filtra las columnas del dataframe:")
        columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(),
                                  default=data.columns.tolist())
        st.dataframe(data[columnas], use_container_width=True)

        st.subheader("Selecciona el formato para la descarga:")
        download_format = st.radio("Selecciona el formato de descarga:", ["Excel", "CSV"], key="oferta_download")
        if download_format == "Excel":
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name='Ofertas')
            towrite.seek(0)
            with st.spinner("Preparando archivo Excel..."):
                st.download_button(
                    label="📥 Descargar Excel",
                    data=towrite,
                    file_name="ofertas_comerciales.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        elif download_format == "CSV":
            csv = data[columnas].to_csv(index=False).encode()
            with st.spinner("Preparando archivo CSV..."):
                st.download_button(
                    label="📥 Descargar CSV",
                    data=csv,
                    file_name="ofertas_comerciales.csv",
                    mime="text/csv"
                )

    # Opción: Generar Informes
    elif opcion == "📑 Generador de informes":
        st.header("📑 Generador de Informes")
        st.write("Aquí puedes generar informes basados en los datos disponibles.")

        # Selección de tipo de informe
        informe_tipo = st.selectbox("Selecciona el tipo de informe:",
                                    ["Informe de Datos UIS", "Informe de Ofertas Comerciales"])

        # Filtros comunes para ambos informes
        st.sidebar.subheader("Filtros de Información")

        # Inicializamos df_filtrado con el dataframe original
        df_filtrado = st.session_state.get("df", pd.DataFrame())

        # Verificar columnas disponibles
        columnas_disponibles = df_filtrado.columns.tolist()

        # Mostrar un desplegable con las columnas disponibles
        filtro_columna = st.selectbox("Selecciona la columna para filtrar en Datos UIS:", columnas_disponibles)

        # Filtros específicos según el tipo de informe seleccionado
        if informe_tipo == "Informe de Datos UIS":
            st.write("Generando informe para los datos UIS...")

            # Filtro por provincia (si la columna existe)
            if "provincia" in df_filtrado.columns:
                provincias = st.selectbox("Selecciona la provincia:",
                                          ["Todas"] + df_filtrado.provincia.unique().tolist())

            # Filtro por fecha (si la columna existe y está en formato datetime)
            if "fecha" in df_filtrado.columns:
                df_filtrado['fecha'] = pd.to_datetime(df_filtrado['fecha'], errors='coerce')
                fecha_inicio = st.date_input("Fecha de inicio:", pd.to_datetime("2022-01-01"))
                fecha_fin = st.date_input("Fecha de fin:", pd.to_datetime("2025-12-31"))

                # Convertir las fechas de los filtros a datetime
                fecha_inicio = pd.to_datetime(fecha_inicio)
                fecha_fin = pd.to_datetime(fecha_fin)

            # Filtros según la columna seleccionada
            if filtro_columna:
                valor_filtro = st.text_input(f"Filtra por {filtro_columna}:")
                if valor_filtro:
                    df_filtrado = df_filtrado[
                        df_filtrado[filtro_columna].astype(str).str.contains(valor_filtro, case=False)]

            # Filtrar por provincia y fecha si se aplican
            if provincias != "Todas":
                df_filtrado = df_filtrado[df_filtrado["provincia"] == provincias]

            if "fecha" in df_filtrado.columns:
                df_filtrado = df_filtrado[df_filtrado["fecha"].between(fecha_inicio, fecha_fin)]

        elif informe_tipo == "Informe de Ofertas Comerciales":
            st.write("Generando informe para las ofertas comerciales...")

            # Inicializamos ofertas_filtradas con el dataframe original
            ofertas_filtradas = st.session_state.get("df", pd.DataFrame())

            # Verificar columnas disponibles en ofertas
            columnas_ofertas = ofertas_filtradas.columns.tolist()

            # Mostrar los desplegables para cada columna disponible en las ofertas comerciales
            filtro_columna_ofertas = st.selectbox("Selecciona la columna para filtrar en Ofertas Comerciales:",
                                                  columnas_ofertas)

            # Filtro por provincia (si la columna existe)
            if "provincia" in ofertas_filtradas.columns:
                provincias_ofertas = st.selectbox("Selecciona la provincia para ofertas:",
                                                  ["Todas"] + ofertas_filtradas.provincia.unique().tolist())

            # Filtro por fecha (si la columna existe y está en formato datetime)
            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas['fecha'] = pd.to_datetime(ofertas_filtradas['fecha'], errors='coerce')
                fecha_inicio_oferta = st.date_input("Fecha de inicio para ofertas:", pd.to_datetime("2022-01-01"))
                fecha_fin_oferta = st.date_input("Fecha de fin para ofertas:", pd.to_datetime("2025-12-31"))

                # Convertir las fechas de los filtros a datetime
                fecha_inicio_oferta = pd.to_datetime(fecha_inicio_oferta)
                fecha_fin_oferta = pd.to_datetime(fecha_fin_oferta)

            # Filtros según la columna seleccionada para las ofertas
            if filtro_columna_ofertas:
                valor_filtro_oferta = st.text_input(f"Filtra por {filtro_columna_ofertas}:")
                if valor_filtro_oferta:
                    ofertas_filtradas = ofertas_filtradas[
                        ofertas_filtradas[filtro_columna_ofertas].astype(str).str.contains(valor_filtro_oferta,
                                                                                           case=False)]

            # Filtrar por provincia y fecha si se aplican
            if provincias_ofertas != "Todas":
                ofertas_filtradas = ofertas_filtradas[ofertas_filtradas["provincia"] == provincias_ofertas]

            if "fecha" in ofertas_filtradas.columns:
                ofertas_filtradas = ofertas_filtradas[
                    ofertas_filtradas["fecha"].between(fecha_inicio_oferta, fecha_fin_oferta)]

        # Personalización del encabezado
        st.sidebar.subheader("Personalización del Informe")
        encabezado_titulo = st.sidebar.text_input("Título del Informe:", "Informe de Datos")
        mensaje_intro = st.sidebar.text_area("Mensaje Introductorio:",
                                             "Este informe contiene datos filtrados según tus criterios.")

        # Personalización del pie de página
        pie_de_pagina = st.sidebar.text_input("Pie de Página:", "Firma: Tu Empresa S.A.")

        # Fecha de generación
        fecha_generacion = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Botón para generar el informe
        if st.button("Generar Informe", key="generar_informe"):
            if informe_tipo == "Informe de Datos UIS":
                # Generar el informe con los datos filtrados
                if not df_filtrado.empty:
                    # Generar archivo Excel
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                        df_filtrado.to_excel(writer, index=False, sheet_name='Informe Datos UIS')
                        worksheet = writer.sheets['Informe Datos UIS']

                        # Personalización del encabezado
                        worksheet.write('A1', encabezado_titulo)
                        worksheet.write('A2', mensaje_intro)
                        worksheet.write('A3', f"Fecha de generación: {fecha_generacion}")

                        # Personalización del pie de página
                        worksheet.write(len(df_filtrado) + 3, 0, pie_de_pagina)
                    towrite.seek(0)

                    # Descargar archivo Excel
                    st.download_button(
                        label="📥 Descargar Informe de Datos UIS en Excel",
                        data=towrite,
                        file_name="informe_datos_uis.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                    # Descargar archivo PDF
                    pdf_buffer = generar_pdf(df_filtrado, encabezado_titulo, mensaje_intro, fecha_generacion,
                                             pie_de_pagina)
                    st.download_button(
                        label="📥 Descargar Informe de Datos UIS en PDF",
                        data=pdf_buffer,
                        file_name="informe_datos_uis.pdf",
                        mime="application/pdf"
                    )

                else:
                    st.error("❌ No se han encontrado datos que coincidan con los filtros para generar el informe.")

            elif informe_tipo == "Informe de Ofertas Comerciales":
                # Generar el informe con los datos filtrados
                if not ofertas_filtradas.empty:
                    # Generar archivo Excel
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                        ofertas_filtradas.to_excel(writer, index=False, sheet_name='Informe Ofertas Comerciales')
                        worksheet = writer.sheets['Informe Ofertas Comerciales']

                        # Personalización del encabezado
                        worksheet.write('A1', encabezado_titulo)
                        worksheet.write('A2', mensaje_intro)
                        worksheet.write('A3', f"Fecha de generación: {fecha_generacion}")

                        # Personalización del pie de página
                        worksheet.write(len(ofertas_filtradas) + 3, 0, pie_de_pagina)
                    towrite.seek(0)

                    # Descargar archivo Excel
                    st.download_button(
                        label="📥 Descargar Informe de Ofertas Comerciales en Excel",
                        data=towrite,
                        file_name="informe_ofertas_comerciales.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                    # Descargar archivo PDF
                    pdf_buffer = generar_pdf(ofertas_filtradas, encabezado_titulo, mensaje_intro, fecha_generacion,
                                             pie_de_pagina)
                    st.download_button(
                        label="📥 Descargar Informe de Ofertas Comerciales en PDF",
                        data=pdf_buffer,
                        file_name="informe_ofertas_comerciales.pdf",
                        mime="application/pdf"
                    )

                else:
                    st.error(
                        "❌ No se han encontrado ofertas comerciales que coincidan con los filtros para generar el informe.")


    # Opción: Gestionar Usuarios
    elif opcion == "👥 Gestionar Usuarios":
        st.header("👥 Gestionar Usuarios")
        st.write("Aquí puedes gestionar los usuarios registrados.")

        usuarios = cargar_usuarios()
        if usuarios:
            st.subheader("Lista de Usuarios")
            df_usuarios = pd.DataFrame(usuarios, columns=["ID", "Nombre", "Rol"])
            st.dataframe(df_usuarios)

        st.subheader("Agregar Nuevo Usuario")
        nombre = st.text_input("Nombre del Usuario")
        rol = st.selectbox("Selecciona el Rol", ["admin", "supervisor", "comercial"])
        password = st.text_input("Contraseña", type="password")
        if st.button("Agregar Usuario"):
            if nombre and password:
                agregar_usuario(nombre, rol, password)
            else:
                st.error("Por favor, completa todos los campos.")

        st.subheader("Editar Usuario")
        usuario_id = st.number_input("ID del Usuario a Editar", min_value=1, step=1)
        if usuario_id:
            conn = obtener_conexion()
            cursor = conn.cursor()
            cursor.execute("SELECT username, role FROM usuarios WHERE id = ?", (usuario_id,))
            usuario = cursor.fetchone()
            conn.close()
            if usuario:
                nuevo_nombre = st.text_input("Nuevo Nombre", value=usuario[0])
                nuevo_rol = st.selectbox("Nuevo Rol", ["admin", "supervisor", "comercial"],
                                         index=["admin", "supervisor", "comercial"].index(usuario[1]))
                nueva_contraseña = st.text_input("Nueva Contraseña", type="password")
                if st.button("Guardar Cambios"):
                    editar_usuario(usuario_id, nuevo_nombre, nuevo_rol, nueva_contraseña)
            else:
                st.error("Usuario no encontrado.")

        st.subheader("Eliminar Usuario")
        eliminar_id = st.number_input("ID del Usuario a Eliminar", min_value=1, step=1)
        if eliminar_id:
            if st.button("Eliminar Usuario"):
                eliminar_usuario(eliminar_id)

    # Opción: Cargar Nuevos Datos
    elif opcion == "📤 Cargar Nuevos Datos":
        st.header("📤 Cargar Nuevos Datos")
        st.write("Aquí puedes cargar un archivo Excel o CSV para agregar nuevos datos a la base de datos.")

        # Opción de carga de archivo
        uploaded_file = st.file_uploader("Selecciona un archivo Excel o CSV", type=["xlsx", "csv"])

        if uploaded_file is not None:
            try:
                # Cargar el archivo según el tipo
                if uploaded_file.name.endswith(".xlsx"):
                    # Si es un archivo Excel
                    data = pd.read_excel(uploaded_file)
                elif uploaded_file.name.endswith(".csv"):
                    # Si es un archivo CSV
                    data = pd.read_csv(uploaded_file)

                # Definir las columnas que nos interesan
                columnas_requeridas = [
                    "id_ams", "apartment_id", "address_id", "provincia", "municipio", "poblacion",
                    "vial", "numero", "parcela_catastral", "letra", "cp", "site_operational_state",
                    "apartment_operational_state", "cto_id", "olt", "cto", "LATITUD", "LONGITUD",
                    "cto_con_proyecto", "COMERCIAL", "ZONA", "FECHA", "SERVICIABLE", "MOTIVO", "contrato_uis"
                ]

                # Filtrar las columnas relevantes
                data_filtrada = data[columnas_requeridas] if all(
                    col in data.columns for col in columnas_requeridas) else None

                if data_filtrada is not None:
                    st.write("Datos filtrados correctamente. Procediendo a cargar en la base de datos...")

                    # Conectar a la base de datos y agregar los datos
                    conn = obtener_conexion()
                    cursor = conn.cursor()

                    # Insertar los datos fila por fila en la base de datos
                    for index, row in data_filtrada.iterrows():
                        cursor.execute("""SELECT * FROM datos_uis WHERE apartment_id = ?""", (row['apartment_id'],))
                        if not cursor.fetchone():
                            # Convertir latitud y longitud a float y con puntos
                            latitud = float(row["LATITUD"].replace(",", "."))
                            longitud = float(row["LONGITUD"].replace(",", "."))
                            cursor.execute("""INSERT INTO datos_uis (id_ams, apartment_id, address_id, provincia, 
                                              municipio, poblacion, vial, numero, parcela_catastral, letra, cp, 
                                              site_operational_state, apartment_operational_state, cto_id, olt, 
                                              cto, LATITUD, LONGITUD, cto_con_proyecto, COMERCIAL, ZONA, FECHA, 
                                              SERVICIABLE, MOTIVO, contrato_uis) 
                                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                           (row["id_ams"], row["apartment_id"], row["address_id"], row["provincia"],
                                            row["municipio"], row["poblacion"], row["vial"], row["numero"],
                                            row["parcela_catastral"], row["letra"], row["cp"], row["site_operational_state"],
                                            row["apartment_operational_state"], row["cto_id"], row["olt"], row["cto"],
                                            latitud, longitud, row["cto_con_proyecto"], row["COMERCIAL"], row["ZONA"],
                                            row["FECHA"], row["SERVICIABLE"], row["MOTIVO"], row["contrato_uis"]))
                    conn.commit()
                    conn.close()
                    st.success("Datos cargados exitosamente.")
                else:
                    st.error("❌ El archivo no contiene las columnas requeridas o está mal formateado.")

            except Exception as e:
                st.error(f"❌ Error al cargar el archivo: {e}")
