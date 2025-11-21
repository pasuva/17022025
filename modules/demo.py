import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster, Geocoder, Draw
from branca.element import Template, MacroElement
from streamlit_folium import st_folium
import sqlitecloud
import time
from modules import login
from streamlit_cookies_controller import CookieController
from functools import lru_cache
import contextlib

# Constantes
COOKIE_NAME = "my_app"
DB_CONNECTION_STRING = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
ALLOWED_OLT_TYPES = ["CTO VERDE", "CTO COMPARTIDA"]

# Añadir al principio del archivo, después de los imports
@st.cache_data(ttl=3600, show_spinner=False)  # Cache por 1 hora
def load_initial_data():
    # Datos iniciales que cambian poco
    return cached_db_query("SELECT...")

# Y en streamlit avanzado, puedes usar:
st.session_state.update({
    "initial_loaded": True  # Evitar recargas innecesarias
})


# Cache para consultas frecuentes
@lru_cache(maxsize=32)
def cached_db_query(query: str, *params):
    """Ejecuta consultas con cache para mejorar rendimiento"""
    with contextlib.closing(get_db_connection()) as conn:
        return pd.read_sql(query, conn, params=params)


def get_db_connection():
    """Obtiene conexión a la base de datos"""
    return sqlitecloud.connect(DB_CONNECTION_STRING)


def setup_page():
    """Configuración inicial de la página"""
    st.set_page_config(page_title="Dashboard Demo - Verde tu Operador", layout="wide")

    st.markdown("""
        <style>
        .footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #F7FBF9;
            color: black;
            text-align: center;
            padding: 8px 0;
            font-size: 14px;
            font-family: 'Segoe UI', sans-serif;
            z-index: 999;
        }
        </style>
        <div class="footer">
            <p>© 2025 Verde tu operador · Desarrollado para uso interno</p>
        </div>
        """, unsafe_allow_html=True)


def logout_user():
    """Cierra sesión del usuario"""
    controller = CookieController(key="cookies")
    cookies_to_clear = [f'{COOKIE_NAME}_session_id', f'{COOKIE_NAME}_username', f'{COOKIE_NAME}_role']

    for cookie in cookies_to_clear:
        if controller.get(cookie):
            controller.set(cookie, '', max_age=0, path='/')

    st.session_state.update({
        "login_ok": False,
        "username": "",
        "role": "",
        "session_id": ""
    })
    st.toast("✅ Has cerrado sesión correctamente.")
    st.rerun()


def check_authentication():
    """Verifica si el usuario está autenticado y tiene rol demo"""
    if "username" not in st.session_state or not st.session_state.get("username"):
        st.warning("⚠️ No has iniciado sesión. Por favor, inicia sesión para continuar.")
        time.sleep(1.5)
        try:
            login.login()
        except Exception:
            pass
        return False

    if st.session_state.get("role") != "demo":
        st.toast("❌ No tienes permisos para acceder al dashboard de demostración.")
        st.toast("🔐 Esta área es solo para usuarios con rol 'demo'")
        return False

    return True


def create_user_sidebar():
    """Crea la barra lateral con información del usuario"""
    with st.sidebar:
        st.markdown(f"""
            <style>
                .user-circle {{
                    width: 100px;
                    height: 100px;
                    border-radius: 50%;
                    background-color: #4CAF50;
                    color: white;
                    font-size: 50px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    margin: 0 auto 10px auto;
                    text-align: center;
                }}
                .user-info {{
                    text-align: center;
                    font-size: 16px;
                    color: #333;
                    margin-bottom: 10px;
                }}
                .welcome-msg {{
                    text-align: center;
                    font-weight: bold;
                    font-size: 18px;
                    margin-top: 0;
                }}
            </style>

            <div class="user-circle">👁️</div>
            <div class="user-info">Rol: Demo</div>
            <div class="welcome-msg">Bienvenido, <strong>{st.session_state.get('username', 'N/A')}</strong></div>
            <hr>
            """, unsafe_allow_html=True)

        if st.button("🚪 Cerrar sesión"):
            logout_user()


def load_filter_options():
    """Carga las opciones para los filtros"""
    try:
        provincias = cached_db_query(
            "SELECT DISTINCT provincia FROM datos_uis WHERE provincia IS NOT NULL ORDER BY provincia"
        )["provincia"].tolist()

        tipos_olt = cached_db_query(
            "SELECT DISTINCT tipo_olt_rental FROM datos_uis WHERE tipo_olt_rental IS NOT NULL ORDER BY tipo_olt_rental"
        )["tipo_olt_rental"].tolist()

        # Filtrar solo tipos OLT permitidos
        tipos_olt = [tipo for tipo in tipos_olt if tipo in ALLOWED_OLT_TYPES]

        return provincias, tipos_olt
    except Exception as e:
        st.error(f"❌ Error al cargar opciones de filtro: {e}")
        return [], []


def create_filters(provincias, tipos_olt):
    """Crea los controles de filtro en la barra lateral"""
    with st.sidebar:
        st.header("🔍 Filtros de Visualización")

        # Información del modo demo
        with st.expander("ℹ️ Información del Modo Demo", expanded=False):
            st.markdown("""
                **💡 Modo Demostración**
                Este dashboard es solo para visualización y demostraciones.

                **Características disponibles:**
                - Visualización de puntos en mapa
                - Filtrado por ubicación geográfica
                - Filtrado por CTO y tipo OLT
                - Selección de área en el mapa
                - Descarga de datos en CSV
                - Estadísticas básicas
                """)

        # Filtros principales
        provincia_sel = st.selectbox("🌍 Provincia", ["Todas"] + provincias, key="demo_provincia")

        # Filtros dependientes
        municipio_sel, poblacion_sel, cto_filter = create_dependent_filters(provincia_sel)

        tipo_olt_filter = st.selectbox("🏢 Tipo OLT Rental", ["Todos"] + tipos_olt, key="demo_tipo_olt")

        # Botones de acción
        col1, col2 = st.columns(2)
        with col1:
            aplicar_filtros = st.button("🔍 Aplicar Filtros", type="primary", use_container_width=True)
        with col2:
            limpiar_filtros = st.button("🧹 Limpiar", use_container_width=True)

        # Filtro por área
        create_area_filter()

        return (provincia_sel, municipio_sel, poblacion_sel, cto_filter, tipo_olt_filter,
                aplicar_filtros, limpiar_filtros)


def create_dependent_filters(provincia_sel):
    """Crea filtros dependientes (municipio, población, CTO)"""
    municipio_sel, poblacion_sel, cto_filter = "Todos", "Todas", "Todas"

    if provincia_sel != "Todas":
        municipios = cached_db_query(
            "SELECT DISTINCT municipio FROM datos_uis WHERE provincia = ? AND municipio IS NOT NULL ORDER BY municipio",
            provincia_sel
        )["municipio"].tolist()
        municipio_sel = st.selectbox("🏘️ Municipio", ["Todos"] + municipios, key="demo_municipio")

        if municipio_sel != "Todos":
            poblaciones = cached_db_query(
                "SELECT DISTINCT poblacion FROM datos_uis WHERE provincia = ? AND municipio = ? AND poblacion IS NOT NULL ORDER BY poblacion",
                provincia_sel, municipio_sel
            )["poblacion"].tolist()
            poblacion_sel = st.selectbox("🏡 Población", ["Todas"] + poblaciones, key="demo_poblacion")

    # Filtro de CTO
    ctos = load_ctos(provincia_sel, municipio_sel, poblacion_sel)
    cto_filter = st.selectbox("📡 CTO", ["Todas"] + ctos, key="demo_cto")

    return municipio_sel, poblacion_sel, cto_filter


def load_ctos(provincia_sel, municipio_sel, poblacion_sel):
    """Carga las CTOs basado en los filtros seleccionados"""
    query = "SELECT DISTINCT cto FROM datos_uis WHERE cto IS NOT NULL AND cto != ''"
    params = []

    conditions = []
    if provincia_sel != "Todas":
        conditions.append("provincia = ?")
        params.append(provincia_sel)
    if municipio_sel != "Todos":
        conditions.append("municipio = ?")
        params.append(municipio_sel)
    if poblacion_sel != "Todas":
        conditions.append("poblacion = ?")
        params.append(poblacion_sel)

    if conditions:
        query += " AND " + " AND ".join(conditions)

    query += " ORDER BY cto"

    try:
        return cached_db_query(query, *params)["cto"].tolist()
    except Exception:
        return cached_db_query(
            "SELECT DISTINCT cto FROM datos_uis WHERE cto IS NOT NULL AND cto != '' ORDER BY cto"
        )["cto"].tolist()


def create_area_filter():
    """Crea el filtro por área geográfica"""
    st.markdown("---")
    st.subheader("🗺️ Filtro por Área")
    st.info("💡 **Filtro independiente:** Este filtro funciona por separado de los filtros de campos anteriores")

    # Inicializar estado del área
    if "drawn_bounds" not in st.session_state:
        st.session_state.update({
            "drawn_bounds": None,
            "apply_area_filter": False,
            "area_filtered_df": None
        })

    # Mostrar información del área actual
    if st.session_state.drawn_bounds:
        bounds = st.session_state.drawn_bounds
        st.info(f"📍 Área seleccionada: \n"
                f"Lat: {bounds['south']:.4f} a {bounds['north']:.4f}\n"
                f"Lon: {bounds['west']:.4f} a {bounds['east']:.4f}")

    area_tipo_olt_filter = st.selectbox(
        "🏢 Tipo OLT en el Área",
        ["Todos", "CTO VERDE", "CTO COMPARTIDA"],
        key="area_tipo_olt"
    )

    col3, col4 = st.columns(2)
    with col3:
        if st.button("📍 Cargar datos del área", type="primary", use_container_width=True):
            load_area_data(area_tipo_olt_filter)
    with col4:
        if st.button("🗑️ Limpiar filtro de área", use_container_width=True):
            st.session_state.update({
                "apply_area_filter": False,
                "drawn_bounds": None,
                "area_filtered_df": None
            })
            st.rerun()


def load_area_data(area_tipo_olt_filter):
    """Carga datos del área seleccionada"""
    if not st.session_state.drawn_bounds:
        st.warning("⚠️ Primero debes dibujar un área en el mapa")
        return

    with st.spinner("⏳ Cargando datos del área..."):
        try:
            bounds = st.session_state.drawn_bounds
            query = """
                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp,
                       latitud, longitud, olt, cto, cto_id, tipo_olt_rental
                FROM datos_uis 
                WHERE latitud BETWEEN ? AND ? AND longitud BETWEEN ? AND ?
            """
            params = [bounds['south'], bounds['north'], bounds['west'], bounds['east']]

            if area_tipo_olt_filter != "Todos":
                query += " AND tipo_olt_rental = ?"
                params.append(area_tipo_olt_filter)
            else:
                query += " AND tipo_olt_rental IN ('CTO VERDE', 'CTO COMPARTIDA')"

            area_df = cached_db_query(query, *params)

            if area_df.empty:
                st.warning("⚠️ No hay datos en el área seleccionada.")
                st.session_state.area_filtered_df = None
            else:
                st.session_state.update({
                    "area_filtered_df": area_df,
                    "demo_filtered_df": None
                })
                st.success(f"✅ Se cargaron {len(area_df)} puntos del área seleccionada")

        except Exception as e:
            st.error(f"❌ Error al cargar datos del área: {e}")


def apply_field_filters(provincia_sel, municipio_sel, poblacion_sel, cto_filter, tipo_olt_filter):
    """Aplica los filtros de campos a los datos"""
    with st.spinner("⏳ Cargando datos filtrados..."):
        try:
            query = """
                SELECT apartment_id, provincia, municipio, poblacion, vial, numero, letra, cp,
                       latitud, longitud, olt, cto, cto_id, tipo_olt_rental
                FROM datos_uis 
                WHERE 1=1
            """
            params = []

            conditions = {
                "provincia": (provincia_sel, "Todas"),
                "municipio": (municipio_sel, "Todos"),
                "poblacion": (poblacion_sel, "Todas"),
                "cto": (cto_filter, "Todas"),
                "tipo_olt_rental": (tipo_olt_filter, "Todos")
            }

            for field, (value, default) in conditions.items():
                if value != default:
                    query += f" AND {field} = ?"
                    params.append(value)

            df = cached_db_query(query, *params)

            if df.empty:
                st.warning("⚠️ No hay datos para los filtros seleccionados.")
                st.session_state.demo_filtered_df = None
                st.session_state.area_filtered_df = None
            else:
                st.session_state.update({
                    "demo_filtered_df": df,
                    "area_filtered_df": None
                })
                st.success(f"✅ Se cargaron {len(df)} puntos en el mapa")

        except Exception as e:
            st.error(f"❌ Error al cargar los datos: {e}")


def create_map(df_display):
    """Crea y configura el mapa Folium"""
    if df_display.empty:
        return create_empty_map()

    # Configurar mapa según la cantidad de puntos
    if len(df_display) == 1:
        lat, lon = df_display['latitud'].iloc[0], df_display['longitud'].iloc[0]
        m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=21,
                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
    else:
        lat, lon = df_display['latitud'].mean(), df_display['longitud'].mean()
        m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
        bounds_data = [[df_display['latitud'].min(), df_display['longitud'].min()],
                       [df_display['latitud'].max(), df_display['longitud'].max()]]
        m.fit_bounds(bounds_data)

    # Añadir controles al mapa
    add_map_controls(m)

    # Añadir marcadores
    add_markers_to_map(m, df_display)

    # Añadir leyenda
    add_legend(m)

    return m


def create_empty_map():
    """Crea un mapa vacío con controles básicos"""
    m = folium.Map(location=[40.4168, -3.7038], zoom_start=6, max_zoom=21,
                   tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", attr="Google")
    add_map_controls(m)
    return m


def add_map_controls(m):
    """Añade controles al mapa (geocoder, herramientas de dibujo)"""
    Geocoder().add_to(m)

    draw_options = {
        'rectangle': {'shapeOptions': {'color': '#3388ff', 'fillColor': '#3388ff', 'fillOpacity': 0.2}},
        'polygon': {'shapeOptions': {'color': '#3388ff', 'fillColor': '#3388ff', 'fillOpacity': 0.2}},
        'circle': False, 'marker': False, 'circlemarker': False, 'polyline': False
    }

    Draw(export=False, position="topleft", draw_options=draw_options).add_to(m)


def add_markers_to_map(m, df_display):
    """Añade marcadores al mapa"""
    if len(df_display) < 500:
        cluster_layer = m
    else:
        cluster_layer = MarkerCluster(maxClusterRadius=5, minClusterSize=3).add_to(m)

    # Contar coordenadas duplicadas para ajustar posición
    coord_counts = df_display[['latitud', 'longitud']].value_counts().to_dict()

    for _, row in df_display.iterrows():
        coord = (row['latitud'], row['longitud'])
        count = coord_counts.get(coord, 1)

        # Ajustar posición para marcadores superpuestos
        lat_offset = count * 0.00003 if count > 1 else 0
        lon_offset = count * -0.00003 if count > 1 else 0
        coord_counts[coord] = count - 1

        # Crear marcador
        create_marker(cluster_layer, row, lat_offset, lon_offset)


def create_marker(layer, row, lat_offset, lon_offset):
    """Crea un marcador individual"""
    marker_color = get_marker_color(row.get("tipo_olt_rental", ""))

    popup_text = f"""
    <div style="min-width: 250px">
        <h4>🏢 ID: {row['apartment_id']}</h4>
        <hr>
        <b>📍 Ubicación:</b><br>
        {row['provincia']}, {row['municipio']}<br>
        {row['vial']} {row['numero']}{row['letra'] or ''}<br>
        CP: {row['cp']}<br>
        📍 {row['latitud']:.6f}, {row['longitud']:.6f}<br>
        <br>
        <b>🔧 Infraestructura:</b><br>
        🏢 OLT: {row.get('olt', 'N/D')}<br>
        📡 CTO: {row.get('cto', 'N/D')}<br>
        🔢 CTO ID: {row.get('cto_id', 'N/D')}<br>
        🏭 Tipo OLT: {row.get('tipo_olt_rental', 'N/D')}<br>
    </div>
    """

    folium.Marker(
        location=[row['latitud'] + lat_offset, row['longitud'] + lon_offset],
        popup=folium.Popup(popup_text, max_width=300),
        tooltip=f"🏢 {row['apartment_id']} - {row['vial']} {row['numero']}",
        icon=folium.Icon(color=marker_color, icon='info-sign')
    ).add_to(layer)


def get_marker_color(tipo_olt):
    """Determina el color del marcador basado en el tipo OLT"""
    tipo_olt_val = str(tipo_olt).strip()
    return 'darkgreen' if tipo_olt_val == "CTO VERDE" else 'purple' if tipo_olt_val == "CTO COMPARTIDA" else 'gray'


def add_legend(m):
    """Añade leyenda al mapa"""
    legend = """
        {% macro html(this, kwargs) %}
        <div style="
            position: fixed; 
            bottom: 50px; left: 50px; width: 180px; 
            z-index:9999; 
            font-size:14px;
            background-color: white;
            color: black;
            border:2px solid grey;
            border-radius:8px;
            padding: 10px;
            box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
        ">
        <b>🎨 Leyenda de Colores</b><br>
        <i style="color:darkgreen;">●</i> CTO VERDE<br>
        <i style="color:purple;">●</i> CTO COMPARTIDA<br>
        </div>
        {% endmacro %}
    """
    macro = MacroElement()
    macro._template = Template(legend)
    m.get_root().add_child(macro)


def process_drawn_area(map_data):
    """Procesa el área dibujada en el mapa"""
    if not (map_data and map_data.get("last_active_drawing") and map_data["last_active_drawing"].get("geometry")):
        return

    geometry = map_data["last_active_drawing"]["geometry"]
    if geometry["type"] not in ["Polygon", "Rectangle"]:
        return

    # Extraer coordenadas según el tipo de geometría
    coords = geometry["coordinates"][0] if geometry["type"] == "Polygon" else geometry["coordinates"][0]
    lats = [coord[1] for coord in coords]
    lons = [coord[0] for coord in coords]

    new_bounds = {
        'north': max(lats),
        'south': min(lats),
        'east': max(lons),
        'west': min(lons)
    }

    st.session_state.drawn_bounds = new_bounds
    st.toast(
        f"📍 Área seleccionada: Lat: {new_bounds['south']:.4f} a {new_bounds['north']:.4f}, Lon: {new_bounds['west']:.4f} a {new_bounds['east']:.4f}")


def display_data_table(df_display):
    """Muestra la tabla de datos y opciones de descarga"""
    st.subheader("📋 Datos Detallados")

    columnas_mostrar = [
        'apartment_id', 'provincia', 'municipio', 'poblacion', 'vial', 'numero', 'letra', 'cp',
        'olt', 'cto', 'cto_id', 'tipo_olt_rental', 'latitud', 'longitud'
    ]

    df_table_display = df_display[columnas_mostrar].copy()
    st.dataframe(df_table_display, use_container_width=True)

    # Botón de descarga
    csv = df_table_display.to_csv(index=False)
    st.download_button(
        label="📥 Descargar datos como CSV",
        data=csv,
        file_name=f"datos_demo_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )


def get_data_to_display():
    """Determina qué datos mostrar basado en los filtros activos"""
    if st.session_state.get("area_filtered_df") is not None:
        df_to_show = st.session_state.area_filtered_df
        st.info("📊 **Visualizando:** Datos filtrados por ÁREA GEOGRÁFICA")
    elif st.session_state.get("demo_filtered_df") is not None:
        df_to_show = st.session_state.demo_filtered_df
        st.info("📊 **Visualizando:** Datos filtrados por CAMPOS")
    else:
        df_to_show = None
        st.info("👆 **Selecciona un método de filtrado:** Usa los filtros de campos o dibuja un área en el mapa")

    return df_to_show


def demo_dashboard():
    """Dashboard de demostración para visualización de puntos en mapa"""
    setup_page()

    if not check_authentication():
        return

    create_user_sidebar()

    # Cargar opciones de filtro
    provincias, tipos_olt = load_filter_options()
    if not provincias:
        return

    # Crear filtros
    filter_results = create_filters(provincias, tipos_olt)
    if not filter_results:
        return

    provincia_sel, municipio_sel, poblacion_sel, cto_filter, tipo_olt_filter, aplicar_filtros, limpiar_filtros = filter_results

    # Manejar eventos de filtros
    if aplicar_filtros:
        apply_field_filters(provincia_sel, municipio_sel, poblacion_sel, cto_filter, tipo_olt_filter)

    if limpiar_filtros:
        for key in ["demo_filtered_df", "area_filtered_df"]:
            if key in st.session_state:
                del st.session_state[key]
        st.session_state.update({"apply_area_filter": False, "drawn_bounds": None})
        st.rerun()

    # Determinar qué datos mostrar
    df_to_show = get_data_to_display()

    # Visualización del mapa
    if df_to_show is not None:
        m = create_map(df_to_show)
        with st.spinner("⏳ Renderizando mapa..."):
            map_data = st_folium(m, height=700, width="100%", key="demo_map",
                                 returned_objects=["last_active_drawing", "bounds"])
        process_drawn_area(map_data)
        display_data_table(df_to_show)
    else:
        m = create_empty_map()
        map_data = st_folium(m, height=500, width="100%", key="demo_map_empty",
                             returned_objects=["last_active_drawing", "bounds"])
        process_drawn_area(map_data)


if __name__ == "__main__":
    demo_dashboard()