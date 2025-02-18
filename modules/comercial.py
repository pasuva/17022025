import streamlit as st
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import sqlite3
import os
import re
from streamlit_folium import st_folium
import streamlit.components.v1 as components
import time
from modules import login

def comercial_dashboard():
    """Muestra el mapa con los puntos asignados al comercial logueado usando folium."""
    st.title("📍 Mapa de Ubicaciones")

    # Verificar si el usuario está logueado
    if "username" not in st.session_state:
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(2)
        login.login()
        return

    # Se usa "username" en lugar de "usuario", ya que en el login se guarda con "username"
    comercial = st.session_state.get("username")

    # Botón de Cerrar Sesión en la barra lateral
    if st.sidebar.button("Cerrar Sesión"):
        cerrar_sesion()

    # Spinner mientras se cargan los datos del comercial desde la base de datos
    with st.spinner("⏳ Cargando los datos del comercial..."):
        try:
            conn = sqlite3.connect("data/usuarios.db")  # Asegúrate de que la ruta sea correcta

            # Verificar que la tabla 'datos_uis' exista
            query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
            tables = pd.read_sql(query_tables, conn)
            if 'datos_uis' not in tables['name'].values:
                st.error("❌ La tabla 'datos_uis' no se encuentra en la base de datos.")
                conn.close()
                return

            # Ejecutar la consulta SQL para obtener los datos asignados al comercial
            query = "SELECT * FROM datos_uis WHERE LOWER(COMERCIAL) = LOWER(?)"
            df = pd.read_sql(query, conn, params=(comercial,))
            conn.close()

            if df.empty:
                st.warning("⚠️ No hay datos asignados a este comercial.")
                return
        except Exception as e:
            st.error(f"❌ Error al cargar los datos de la base de datos: {e}")
            return

    # Asegurarse de que df es un DataFrame válido
    if not isinstance(df, pd.DataFrame):
        st.error("❌ Los datos no se cargaron correctamente.")
        return

    # Verificar que las columnas necesarias existen
    for col in ['latitud', 'longitud', 'address_id']:  # Usar las columnas correctas
        if col not in df.columns:
            st.error(f"❌ No se encuentra la columna '{col}'.")
            return

    # Inicializar la lista de clics en session_state si no existe
    if "clicks" not in st.session_state:
        st.session_state.clicks = []

    # Intentamos obtener la ubicación del usuario
    location = get_user_location()

    if location is None:
        st.warning("❌ No se pudo obtener la ubicación. Cargando el mapa en la ubicación predeterminada.")
        # Si no se obtiene la ubicación, se carga el mapa en el Polígono de Raos en Santander
        lat, lon = 43.463444, -3.790476  # Polígono de Raos, Santander
    else:
        lat, lon = location

    # Spinner mientras se carga el mapa
    with st.spinner("⏳ Cargando mapa..."):
        # Crear el mapa con la latitud y longitud
        m = folium.Map(location=[lat, lon], zoom_start=12)
        marker_cluster = MarkerCluster().add_to(m)

        # Agregar los marcadores al clúster
        for _, row in df.iterrows():
            popup_text = f"🏠 {row['address_id']} - 📍 {row['latitud']}, {row['longitud']}"
            folium.Marker(
                location=[row['latitud'], row['longitud']],
                popup=popup_text,
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(marker_cluster)

        # Renderizar el mapa en Streamlit
        map_data = st_folium(m, height=500, width=700)

    # Capturar clics en los marcadores
    if map_data and "last_object_clicked" in map_data and map_data["last_object_clicked"]:
        st.session_state.clicks.append(map_data["last_object_clicked"])

    # Mostrar las coordenadas registradas del último clic
    if st.session_state.clicks:
        last_click = st.session_state.clicks[-1]
        #st.write(f"✅ Las coordenadas del punto seleccionado son: **{last_click}**")

        # Spinner mientras carga la información del formulario
        with st.spinner("⏳ Cargando formulario..."):
            mostrar_formulario(last_click)

def get_user_location():
    """Obtiene la ubicación del usuario a través de un componente de JavaScript y pasa la ubicación a Python."""
    # Crear un formulario de HTML y JavaScript para obtener las coordenadas de geolocalización
    html_code = """
        <script>
            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(function(position) {
                    var lat = position.coords.latitude;
                    var lon = position.coords.longitude;
                    // Enviar las coordenadas a Streamlit
                    window.parent.postMessage({lat: lat, lon: lon}, "*");
                }, function() {
                    alert("No se pudo obtener la ubicación.");
                });
            } else {
                alert("Geolocalización no soportada por este navegador.");
            }
        </script>
    """

    components.html(html_code, height=0, width=0)

    # Asegúrate de capturar las coordenadas de la ubicación
    if "lat" in st.session_state and "lon" in st.session_state:
        lat = st.session_state["lat"]
        lon = st.session_state["lon"]
        return lat, lon

    return None

def cerrar_sesion():
    """Función para cerrar la sesión y limpiar el estado."""
    # Eliminar la información de la sesión
    del st.session_state["username"]
    del st.session_state["clicks"]
    st.success("✅ Has cerrado sesión correctamente.")
    # Mostrar un mensaje y redirigir a la página de inicio (no es necesario recargar)
    st.warning("👉 Por favor, inicia sesión nuevamente.")
    #st.stop()  # Detener la ejecución del código aquí
    time.sleep(2)
    login.login()

def validar_email(email):
    return re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)


def mostrar_formulario(click_data):
    """Muestra un formulario con los datos correspondientes a las coordenadas seleccionadas."""

    st.subheader("📄 Enviar Oferta")

    # Extraer datos del clic en el mapa
    popup_text = click_data.get("popup", "")
    apartment_id = popup_text.split(" - ")[0] if " - " in popup_text else "N/D"
    lat_value = click_data.get("lat", "N/D")
    lng_value = click_data.get("lng", "N/D")

    # Conectamos a la base de datos para obtener los datos según coordenadas
    try:
        conn = sqlite3.connect("data/usuarios.db")
        query = """
            SELECT * FROM datos_uis 
            WHERE latitud = ? AND longitud = ?
        """
        df = pd.read_sql(query, conn, params=(lat_value, lng_value))
        conn.close()

        if df.empty:
            st.warning("⚠️ No se encontraron datos para estas coordenadas.")
            provincia = municipio = poblacion = vial = numero = letra = cp = "No disponible"
        else:
            apartment_id = df.iloc[0]["apartment_id"]
            provincia = df.iloc[0]["provincia"]
            municipio = df.iloc[0]["municipio"]
            poblacion = df.iloc[0]["poblacion"]
            vial = df.iloc[0]["vial"]
            numero = df.iloc[0]["numero"]
            letra = df.iloc[0]["letra"]
            cp = df.iloc[0]["cp"]

    except Exception as e:
        st.error(f"❌ Error al obtener datos de la base de datos: {e}")
        return

    # ID de apartamento (bloqueado)
    st.text_input("🏢 Apartment ID", value=apartment_id, disabled=True)

    # 👉 Provincia, Municipio y Población en la misma línea
    col1, col2, col3 = st.columns(3)
    with col1:
        st.text_input("📍 Provincia", value=provincia, disabled=True)
    with col2:
        st.text_input("🏙️ Municipio", value=municipio, disabled=True)
    with col3:
        st.text_input("👥 Población", value=poblacion, disabled=True)

    # 👉 Vial, Número, Letra y Código Postal en otra línea
    col4, col5, col6, col7 = st.columns([2, 1, 1, 1])
    with col4:
        st.text_input("🚦 Vial", value=vial, disabled=True)
    with col5:
        st.text_input("🔢 Número", value=numero, disabled=True)
    with col6:
        st.text_input("🔠 Letra", value=letra, disabled=True)
    with col7:
        st.text_input("📮 Código Postal", value=cp, disabled=True)

    # 👉 Latitud y Longitud en la misma línea
    col8, col9 = st.columns(2)
    with col8:
        st.text_input("📌 Latitud", value=lat_value, disabled=True)
    with col9:
        st.text_input("📌 Longitud", value=lng_value, disabled=True)

    # 👉 Campos editables
    client_name = st.text_input("👤 Nombre del Cliente", max_chars=100)
    phone = st.text_input("📞 Teléfono", max_chars=15)
    alt_address = st.text_input("📌 Dirección Alternativa (Rellenar si difiere de la original)")
    observations = st.text_area("📝 Observaciones")

    # 👉 Campo de contestación "¿Es serviciable?"
    es_serviciable = st.radio("🛠️ ¿Es serviciable?", ["Sí", "No"], index=0, horizontal=True)

    motivo_no_serviciable = ""
    contiene_incidencias = ""
    motivo_incidencia = ""
    imagen_incidencia = None

    # Si "Es serviciable" es "No", aparece el campo de motivo
    if es_serviciable == "No":
        motivo_no_serviciable = st.text_area("❌ Motivo de No Servicio")

    # Si "Es serviciable" es "Sí", aparece la opción "¿Contiene incidencias?"
    if es_serviciable == "Sí":
        contiene_incidencias = st.radio("⚠️ ¿Contiene incidencias?", ["Sí", "No"], index=1, horizontal=True)

        # Si "Contiene incidencias" es "Sí", aparecen el campo de motivo y el de subir imagen
        if contiene_incidencias == "Sí":
            motivo_incidencia = st.text_area("📄 Motivo de la Incidencia")
            imagen_incidencia = st.file_uploader("📷 Adjuntar Imagen (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

    # Botón de enviar
    if st.button("🚀 Enviar Oferta"):
        if not client_name or not phone:
            st.error("❌ Todos los campos obligatorios deben estar llenos.")
            return
        if not phone.isdigit():
            st.error("❌ El teléfono debe contener solo números.")
            return

        oferta_data = {
            "Apartment ID": apartment_id,
            "Provincia": provincia,
            "Municipio": municipio,
            "Población": poblacion,
            "Vial": vial,
            "Número": numero,
            "Letra": letra,
            "Código Postal": cp,
            "Latitud": lat_value,
            "Longitud": lng_value,
            "Nombre Cliente": client_name,
            "Teléfono": phone,
            "Dirección Alternativa": alt_address,
            "Observaciones": observations,
            "Es Serviciable": es_serviciable,
            "Motivo No Serviciable": motivo_no_serviciable if es_serviciable == "No" else "",
            "Contiene Incidencias": contiene_incidencias if es_serviciable == "Sí" else "",
            "Motivo Incidencia": motivo_incidencia if contiene_incidencias == "Sí" else "",
            "Fecha Envío": pd.Timestamp.now()
        }

        excel_filename = "ofertas.xlsx"
        with st.spinner("⏳ Guardando la oferta en Excel..."):
            try:
                if os.path.exists(excel_filename):
                    existing_df = pd.read_excel(excel_filename)
                    new_df = pd.DataFrame([oferta_data])
                    df_total = pd.concat([existing_df, new_df], ignore_index=True)
                else:
                    df_total = pd.DataFrame([oferta_data])

                df_total.to_excel(excel_filename, index=False)

                # Guardar la imagen si hay incidencia
                if contiene_incidencias == "Sí" and imagen_incidencia:
                    img_path = f"incidencias/{apartment_id}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    with open(img_path, "wb") as f:
                        f.write(imagen_incidencia.getbuffer())
                    st.success("✅ Imagen de incidencia guardada correctamente.")

                st.success("✅ ¡Oferta enviada y guardada en Excel con éxito!")

            except Exception as e:
                st.error(f"❌ Error al guardar la oferta en Excel: {e}")


if __name__ == "__main__":
    comercial_dashboard()
