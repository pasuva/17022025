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
    """Carga los datos de la base de datos con caché"""
    conn = sqlite3.connect("data/usuarios.db")
    query = "SELECT apartment_id, latitud, longitud, fecha, provincia, cto_con_proyecto FROM datos_uis WHERE comercial = 'RAFA SANZ'"
    data = pd.read_sql(query, conn)
    conn.close()
    return data

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
        🟢 **Serviciable:** Representado por un icono de casa verde.
        🟠 **Oferta (Contrato: Sí):** Representado por un icono de casa naranja.
        ⚫ **Oferta (No Interesado):** Representado por un icono de casa gris.
        🔵 **Sin Oferta:** Representado por un icono de casa azul.
        🔴 **No Serviciable:** Representado por un icono de casa roja.
    """)

    # Barra lateral con bienvenida
    st.sidebar.markdown("""<style> .user-circle { width: 100px; height: 100px; border-radius: 50%; background-color: #ff0000; color: white; font-size: 50px; display: flex; align-items: center; justify-content: center; margin-bottom: 30px; text-align: center; margin-left: auto; margin-right: auto; } </style> <div class="user-circle">👤</div> <div>Rol: Visualización Comercial Avanzada</div>""", unsafe_allow_html=True)

    st.sidebar.write(f"Bienvenido, {st.session_state['username']}")

    # Filtros para reducir datos antes de cargarlos
    fecha_min = st.sidebar.date_input("Fecha mínima", value=pd.to_datetime("2024-01-01"))
    fecha_max = st.sidebar.date_input("Fecha máxima", value=pd.to_datetime("2030-12-31"))

    # Cargar los datos
    with st.spinner("Cargando datos..."):
        data = cargar_datos()
        if data.empty:
            st.error("❌ No se encontraron datos para Rafa Sanz.")
            return

    # Asegúrate de que la columna 'fecha' sea de tipo datetime64[ns]
    data['fecha'] = pd.to_datetime(data['fecha'], errors='coerce')

    # Asegúrate de que fecha_min y fecha_max sean de tipo datetime64[ns]
    fecha_min = pd.to_datetime(fecha_min)
    fecha_max = pd.to_datetime(fecha_max)

    # Filtrar los datos por fecha
    data = data[(data["fecha"] >= fecha_min) & (data["fecha"] <= fecha_max)]

    # Filtro de provincia
    provincias = data['provincia'].unique()  # Cargar provincias únicas
    provincia_seleccionada = st.sidebar.selectbox("Selecciona una provincia", provincias)

    # Filtrar los datos por provincia
    data = data[data["provincia"] == provincia_seleccionada]

    # Limpiar datos
    data = data.dropna(subset=['latitud', 'longitud'])
    data['latitud'] = data['latitud'].astype(float)
    data['longitud'] = data['longitud'].astype(float)

    # Reducir datos si hay demasiados puntos
    if len(data) > 5000:
        st.warning("🔹 Se ha reducido la cantidad de puntos para mejorar la visualización.")
        data = data.sample(n=5000, random_state=42)

    # Agrupar puntos si hay demasiados
    if len(data) > 3000:
        st.warning("🔹 Se han agrupado los puntos cercanos.")
        kmeans = KMeans(n_clusters=100, random_state=42)
        data["cluster"] = kmeans.fit_predict(data[["latitud", "longitud"]])

        # Usar centroides de los clusters en lugar de puntos individuales
        data = data.groupby("cluster").agg({"latitud": "mean", "longitud": "mean"}).reset_index()

        # Verifica que después de la agrupación haya datos
        if data.empty:
            st.error("❌ No se encontraron puntos después de agrupar los datos.")
            return

    # Crear mapa centrado en el primer punto
    with st.spinner("Generando mapa..."):
        if not data.empty:
            centro_mapa = [data.iloc[0]['latitud'], data.iloc[0]['longitud']]
            m = folium.Map(
                location=centro_mapa,
                zoom_start=12,
                tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
                attr="Google"
            )

            # Agregar puntos con FastMarkerCluster
            locations = list(zip(data["latitud"], data["longitud"]))
            FastMarkerCluster(locations).add_to(m)

            # Añadir marcadores con diferentes iconos (SI/NO) para la columna `cto_con_proyecto`
            for _, row in data.iterrows():
                lat = row['latitud']
                lon = row['longitud']
                cto_con_proyecto = row['cto_con_proyecto']

                # Añadir los marcadores con diferentes iconos
                if cto_con_proyecto == "SI":
                    folium.Marker([lat, lon], icon=folium.Icon(icon='home', color='blue')).add_to(m)
                else:
                    folium.Marker([lat, lon], icon=folium.Icon(icon='info-sign', color='blue')).add_to(m)

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
            data=data.to_csv(index=False).encode(),
            file_name="datos_rafa_sanz.csv",
            mime="text/csv"
        )

    elif descarga_opcion == "Excel":
        log_trazabilidad(st.session_state["username"], "Descarga de datos", "Usuario descargó datos en Excel.")
        with io.BytesIO() as towrite:
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data.to_excel(writer, index=False, sheet_name="Datos Rafa Sanz")
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
