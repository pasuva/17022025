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
    # Cargar datos de la tabla datos_uis
    query_datos_uis = "SELECT apartment_id, latitud, longitud, fecha, provincia, cto_con_proyecto FROM datos_uis WHERE comercial = 'RAFA SANZ'"
    datos_uis = pd.read_sql(query_datos_uis, conn)

    # Cargar datos de la tabla ofertas_comercial
    query_ofertas_comercial = "SELECT apartment_id, serviciable, contrato FROM ofertas_comercial"
    ofertas_comercial = pd.read_sql(query_ofertas_comercial, conn)

    conn.close()

    return datos_uis, ofertas_comercial

def mapa_dashboard():
    """Panel de mapas optimizado para Rafa Sanz"""
    st.set_page_config(page_title="Mapa de Ubicaciones", page_icon="🗺️", layout="wide")
    st.title("🗺️ Mapa de Ubicaciones")

    # Descripción de los íconos (explicación de cada ícono)
    st.markdown("""
        **Iconos:**
        🏠 **Oferta con Proyecto:** Representado por un icono de casa azul.
        ℹ️ **Oferta sin Proyecto:** Representado por un icono de información azul.
        \n
        **Colores:**
        🟢 **Serviciable (Sí)**
        🟠 **Oferta (Contrato: Sí)**
        ⚫ **Oferta (Contrato: No Interesado)**
        🔵 **No Visitado (No existe en ofertas_comercial)**
        🔴 **No Serviciable**
    """)

    # Barra lateral con bienvenida
    st.sidebar.markdown("""<style> .user-circle { width: 100px; height: 100px; border-radius: 50%; background-color: #ff0000; color: white; font-size: 50px; display: flex; align-items: center; justify-content: center; margin-bottom: 30px; text-align: center; margin-left: auto; margin-right: auto; } </style> <div class="user-circle">👤</div> <div>Rol: Visualización Comercial Avanzada</div>""", unsafe_allow_html=True)

    st.sidebar.write(f"Bienvenido, {st.session_state['username']}")

    # Botón de Cerrar Sesión en la barra lateral
    with st.sidebar:
        if st.button("Cerrar sesión"):
            # Registrar trazabilidad del cierre de sesión
            detalles = f"El comercial {st.session_state['username']} cerró sesión."
            log_trazabilidad(st.session_state["username"], "Cierre sesión", detalles)

            # Eliminar los datos de la sesión
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    # Filtros para reducir datos antes de cargarlos
    fecha_min = st.sidebar.date_input("Fecha mínima", value=pd.to_datetime("2024-01-01"))
    fecha_max = st.sidebar.date_input("Fecha máxima", value=pd.to_datetime("2030-12-31"))

    # Cargar los datos
    with st.spinner("Cargando datos..."):
        datos_uis, ofertas_comercial = cargar_datos()
        if datos_uis.empty:
            st.error("❌ No se encontraron datos para Rafa Sanz.")
            return

    # Asegúrate de que la columna 'fecha' sea de tipo datetime64[ns]
    datos_uis['fecha'] = pd.to_datetime(datos_uis['fecha'], errors='coerce')

    # Asegúrate de que fecha_min y fecha_max sean de tipo datetime64[ns]
    fecha_min = pd.to_datetime(fecha_min)
    fecha_max = pd.to_datetime(fecha_max)

    # Filtrar los datos por fecha
    datos_uis = datos_uis[(datos_uis["fecha"] >= fecha_min) & (datos_uis["fecha"] <= fecha_max)]

    # Filtro de provincia
    provincias = datos_uis['provincia'].unique()  # Cargar provincias únicas
    provincia_seleccionada = st.sidebar.selectbox("Selecciona una provincia", provincias)

    # Filtrar los datos por provincia
    datos_uis = datos_uis[datos_uis["provincia"] == provincia_seleccionada]

    # Limpiar datos
    datos_uis = datos_uis.dropna(subset=['latitud', 'longitud'])
    datos_uis['latitud'] = datos_uis['latitud'].astype(float)
    datos_uis['longitud'] = datos_uis['longitud'].astype(float)

    # Reducir datos si hay demasiados puntos
    if len(datos_uis) > 5000:
        st.warning("🔹 Se ha reducido la cantidad de puntos para mejorar la visualización.")
        datos_uis = datos_uis.sample(n=5000, random_state=42)

    # Agrupar puntos si hay demasiados
    if len(datos_uis) > 3000:
        st.warning("🔹 Se han agrupado los puntos cercanos.")
        kmeans = KMeans(n_clusters=100, random_state=42)
        datos_uis["cluster"] = kmeans.fit_predict(datos_uis[["latitud", "longitud"]])

        # Usar centroides de los clusters en lugar de puntos individuales
        datos_uis = datos_uis.groupby("cluster").agg({"latitud": "mean", "longitud": "mean"}).reset_index()

        # Verifica que después de la agrupación haya datos
        if datos_uis.empty:
            st.error("❌ No se encontraron puntos después de agrupar los datos.")
            return

    # Crear mapa centrado en el primer punto
    with st.spinner("Generando mapa..."):
        if not datos_uis.empty:
            centro_mapa = [datos_uis.iloc[0]['latitud'], datos_uis.iloc[0]['longitud']]
            m = folium.Map(
                location=centro_mapa,
                zoom_start=12,
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google"
            )

            # Agregar puntos con FastMarkerCluster
            locations = list(zip(datos_uis["latitud"], datos_uis["longitud"]))
            FastMarkerCluster(locations).add_to(m)

            # Añadir marcadores con diferentes iconos y colores
            for _, row in datos_uis.iterrows():
                lat = row['latitud']
                lon = row['longitud']
                apartment_id = row['apartment_id']

                # Buscar si el apartment_id está en ofertas_comercial
                oferta = ofertas_comercial[ofertas_comercial['apartment_id'] == apartment_id]

                # Determinar el color según los criterios especificados
                if not oferta.empty:
                    serviciable = oferta.iloc[0]['serviciable']
                    contrato = oferta.iloc[0]['contrato']

                    if serviciable == "Sí":
                        color = 'green'  # Serviciable
                    elif serviciable == "No":
                        color = 'red'  # No Serviciable
                    elif contrato == "Sí":
                        color = 'orange'  # Oferta con Contrato
                    elif contrato == "No Interesado":
                        color = 'black'  # Oferta No Interesado
                else:
                    color = 'blue'  # No Visitado (sin datos en ofertas_comercial)

                # Añadir el marcador con el color adecuado
                folium.Marker([lat, lon], icon=folium.Icon(icon='home', color=color)).add_to(m)

            # Renderizar mapa en Streamlit
            st_folium(m, height=500, width=700)

    # Registrar trazabilidad
    log_trazabilidad(st.session_state["username"], "Visualización de mapa", "Usuario visualizó el mapa de Rafa Sanz.")

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
