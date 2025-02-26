import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
from folium.plugins import FastMarkerCluster
from sklearn.cluster import KMeans
from datetime import datetime
import io


def log_trazabilidad(usuario, accion, detalles):
    """ Inserta un registro en la tabla de trazabilidad """
    conn = sqlite3.connect("data/usuarios.db")
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))
    conn.commit()
    conn.close()


@st.cache_data
def cargar_datos():
    """Carga los datos de las tablas de base de datos con caché"""
    conn = sqlite3.connect("data/usuarios.db")
    # Cargar datos de la tabla datos_uis (incluimos municipio y población)
    query_datos_uis = """
        SELECT apartment_id, latitud, longitud, fecha, provincia, municipio, vial, numero, letra, poblacion, cto_con_proyecto 
        FROM datos_uis 
        WHERE comercial = 'RAFA SANZ'
    """
    datos_uis = pd.read_sql(query_datos_uis, conn)
    # Cargar datos de la tabla comercial_rafa (incluimos Contrato, municipio, población y comercial)
    query_comercial_rafa = """
        SELECT apartment_id, serviciable, Contrato, municipio, poblacion, comercial 
        FROM comercial_rafa
    """
    comercial_rafa = pd.read_sql(query_comercial_rafa, conn)
    conn.close()
    return datos_uis, comercial_rafa


def mapa_dashboard():
    """Panel de mapas optimizado para Rafa Sanz con asignación y desasignación de zonas comerciales"""
    st.set_page_config(page_title="Mapa de Ubicaciones", page_icon="🗺️", layout="wide")
    st.title("🗺️ Mapa de Ubicaciones")

    # Descripción de los íconos
    st.markdown("""
        **Iconos:**
        🏠 **Oferta con Proyecto:** Representado por un icono de casa azul.
        ℹ️ **Oferta sin Proyecto:** Representado por un icono de información azul.
        \n
        **Colores:**
        🟢 **Serviciable (Sí)**
        🔴 **No Serviciable (No)**
        🟠 **Oferta (Contrato: Sí)**
        ⚫ **Oferta (Contrato: No Interesado)**
        🔵 **No Visitado (No existe en comercial_rafa)**
    """)

    # Barra lateral con bienvenida y botón de cerrar sesión
    st.sidebar.markdown("""
                <style>
                    .user-circle {
                        width: 100px;
                        height: 100px;
                        border-radius: 50%;
                        background-color: #0073e6;
                        color: white;
                        font-size: 50px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        margin-bottom: 30px;
                        text-align: center;
                        margin-left: auto;
                        margin-right: auto;
                    }
                </style>
                <div class="user-circle">👤</div>
                <div>Rol: Gestor Comercial</div>
                """, unsafe_allow_html=True)
    st.sidebar.markdown(f"¡Bienvenido, **{st.session_state['username']}**!")
    with st.sidebar:
        if st.button("Cerrar sesión"):
            detalles = f"El comercial {st.session_state['username']} cerró sesión."
            log_trazabilidad(st.session_state["username"], "Cierre sesión", detalles)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()
    st.sidebar.markdown("---")

    st.sidebar.markdown("Filtros generales UUIIs")

    # Filtros por fecha
    fecha_min = st.sidebar.date_input("Fecha mínima", value=pd.to_datetime("2024-01-01"))
    fecha_max = st.sidebar.date_input("Fecha máxima", value=pd.to_datetime("2030-12-31"))

    # Cargar datos
    with st.spinner("Cargando datos..."):
        datos_uis, comercial_rafa = cargar_datos()
        if datos_uis.empty:
            st.error("❌ No se encontraron datos para Rafa Sanz.")
            return

    # Convertir 'fecha' a datetime y filtrar
    datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')
    fecha_min = pd.to_datetime(fecha_min)
    fecha_max = pd.to_datetime(fecha_max)
    datos_uis = datos_uis[(datos_uis["fecha"] >= fecha_min) & (datos_uis["fecha"] <= fecha_max)]

    # Filtro por provincia
    provincias = datos_uis['provincia'].unique()
    provincia_seleccionada = st.sidebar.selectbox("Selecciona una provincia", provincias)
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    # Limpiar datos de latitud y longitud
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)
    if len(datos_uis) > 5000:
        st.warning("🔹 Se ha reducido la cantidad de puntos para mejorar la visualización.")
        datos_uis = datos_uis.sample(n=5000, random_state=42)
    if len(datos_uis) > 3000:
        st.warning("🔹 Se han agrupado los puntos cercanos.")
        kmeans = KMeans(n_clusters=100, random_state=42)
        datos_uis["cluster"] = kmeans.fit_predict(datos_uis[["latitud", "longitud"]])
        datos_uis = datos_uis.groupby("cluster").agg({"latitud": "mean", "longitud": "mean"}).reset_index()
        if datos_uis.empty:
            st.error("❌ No se encontraron puntos después de agrupar los datos.")
            return

    # --- Crear columnas: la columna derecha tendrá el panel de asignación ---
    col1, col2 = st.columns([3, 3])
    with col2:
        st.subheader("Asignación de Zonas para Comerciales")
        # Seleccionar la acción a realizar
        accion = st.radio("Seleccione acción", ["Asignar Zona", "Desasignar Zona"], key="accion")
        if accion == "Asignar Zona":
            municipios = sorted(datos_uis['municipio'].dropna().unique())
            municipio_sel = st.selectbox("Seleccione Municipio", municipios, key="municipio_sel")
            poblacion_sel = None
            if municipio_sel:
                poblaciones = sorted(datos_uis[datos_uis['municipio'] == municipio_sel]['poblacion'].dropna().unique())
                poblacion_sel = st.selectbox("Seleccione Población", poblaciones, key="poblacion_sel")
            comercial_elegido = st.radio("Asignar a:", ["comercial_rafa1", "comercial_rafa2"], key="comercial_elegido")
            if municipio_sel and poblacion_sel:
                conn = sqlite3.connect("data/usuarios.db")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                               (municipio_sel, poblacion_sel))
                count_assigned = cursor.fetchone()[0]
                conn.close()
                if count_assigned > 0:
                    st.warning("🚫 Esta zona ya ha sido asignada.")
                else:
                    if st.button("Asignar Zona"):
                        conn = sqlite3.connect("data/usuarios.db")
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO comercial_rafa (apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, comercial, Contrato)
                            SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp, latitud, longitud, ?, 'Pendiente'
                            FROM datos_uis
                            WHERE municipio = ? AND poblacion = ?
                        """, (comercial_elegido, municipio_sel, poblacion_sel))
                        conn.commit()
                        conn.close()
                        st.success("✅ Zona asignada correctamente.")
                        log_trazabilidad(st.session_state["username"], "Asignación",
                                         f"Asignó zona {municipio_sel} - {poblacion_sel} a {comercial_elegido}")
        elif accion == "Desasignar Zona":
            conn = sqlite3.connect("data/usuarios.db")
            assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
            conn.close()
            if assigned_zones.empty:
                st.warning("No hay zonas asignadas para desasignar.")
            else:
                assigned_zones['zona'] = assigned_zones['municipio'] + " - " + assigned_zones['poblacion']
                zonas_list = sorted(assigned_zones['zona'].unique())
                zona_seleccionada = st.selectbox("Seleccione la zona asignada a desasignar", zonas_list, key="zona_seleccionada")
                if zona_seleccionada:
                    municipio_sel, poblacion_sel = zona_seleccionada.split(" - ")
                    if st.button("Desasignar Zona"):
                        conn = sqlite3.connect("data/usuarios.db")
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM comercial_rafa WHERE municipio = ? AND poblacion = ?",
                                       (municipio_sel, poblacion_sel))
                        conn.commit()
                        conn.close()
                        st.success("✅ Zona desasignada correctamente.")
                        log_trazabilidad(st.session_state["username"], "Desasignación",
                                         f"Desasignó zona {municipio_sel} - {poblacion_sel}")
        # Mostrar la tabla de zonas asignadas (dentro del panel de asignación)
        conn = sqlite3.connect("data/usuarios.db")
        assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
        conn.close()

    # --- Generar el mapa en la columna izquierda, usando los valores de asignación para centrar ---
    with col1:
        # Por defecto, usar el centro del primer registro
        center = [datos_uis.iloc[0]['latitud'], datos_uis.iloc[0]['longitud']]
        zoom_start = 12
        # Si se han seleccionado municipio y población en el panel de asignación, recalcule el centro
        if "municipio_sel" in st.session_state and "poblacion_sel" in st.session_state:
            zone_data = datos_uis[(datos_uis["municipio"] == st.session_state["municipio_sel"]) &
                                  (datos_uis["poblacion"] == st.session_state["poblacion_sel"])]
            if not zone_data.empty:
                center = [zone_data["latitud"].mean(), zone_data["longitud"].mean()]
                zoom_start = 14  # Zoom más cercano para la zona

        m = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
            attr="Google"
        )
        locations = list(zip(datos_uis["latitud"], datos_uis["longitud"]))
        FastMarkerCluster(locations).add_to(m)
        # Añadir marcadores con criterios de color
        for _, row in datos_uis.iterrows():
            lat = row['latitud']
            lon = row['longitud']
            apartment_id = row['apartment_id']
            vial = row.get('vial', None)  # Si existe
            numero = row.get('numero', None)  # Si existe
            letra = row.get('letra', None)  # Si existe
            oferta = comercial_rafa[comercial_rafa['apartment_id'] == apartment_id]

            # Determinamos el color del marcador según los criterios
            if not oferta.empty:
                serviciable = oferta.iloc[0]['serviciable']
                contrato = oferta.iloc[0]['Contrato']
                if serviciable == "Sí":
                    color = 'green'
                elif serviciable == "No":
                    color = 'red'
                elif contrato == "Sí":
                    color = 'orange'
                elif contrato == "No Interesado":
                    color = 'black'
                else:
                    color = 'gray'
            else:
                color = 'blue'

            # Crear el popup con la información
            popup_text = f"""
            <b>Apartment ID:</b> {apartment_id}<br>
            <b>Vial:</b> {vial if vial else 'No Disponible'}<br>
            <b>Número:</b> {numero if numero else 'No Disponible'}<br>
            <b>Letra:</b> {letra if letra else 'No Disponible'}<br>
            """

            # Crear el marcador con el popup
            folium.Marker(
                [lat, lon],
                icon=folium.Icon(icon='home', color=color),
                popup=folium.Popup(popup_text, max_width=300)  # Popup con texto
            ).add_to(m)
        st_folium(m, height=500, width=700)

    # Mostrar la tabla de zonas asignadas ocupando el ancho completo, justo debajo de las columnas
    conn = sqlite3.connect("data/usuarios.db")
    assigned_zones = pd.read_sql("SELECT DISTINCT municipio, poblacion, comercial FROM comercial_rafa", conn)
    total_ofertas = pd.read_sql("SELECT DISTINCT * FROM comercial_rafa", conn)
    conn.close()
    if not assigned_zones.empty:
        st.write("Zonas ya asignadas:")
        st.dataframe(assigned_zones, use_container_width=True)

    # Registro de trazabilidad para la visualización del mapa
    log_trazabilidad(st.session_state["username"], "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")

    st.write("Ofertas comerciales: Visualización del total de ofertas asignadas a cada comercial y su estado actual")
    st.dataframe(total_ofertas, use_container_width=True)

    # Sección de descarga de datos
    st.subheader("Descargar Datos")
    descarga_opcion = st.radio("Formato de descarga:", ["CSV", "Excel"])
    if descarga_opcion == "CSV":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó datos en CSV.")
        st.download_button(
            label="Descargar como CSV",
            data=datos_uis.to_csv(index=False).encode(),
            file_name="datos_rafa_sanz.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó datos en Excel.")
        with io.BytesIO() as towrite:
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                datos_uis.to_excel(writer, index=False, sheet_name="Datos Rafa Sanz")
            towrite.seek(0)
            st.download_button(
                label="Descargar como Excel",
                data=towrite,
                file_name="datos_rafa_sanz.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    st.info("Dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")


if __name__ == "__main__":
    mapa_dashboard()
