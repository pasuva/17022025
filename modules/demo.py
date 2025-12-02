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
import hashlib

# Añadir al principio del archivo, después de los imports
@st.cache_data(ttl=3600, show_spinner=False)  # Cache por 1 hora
def load_initial_data():
    # Datos iniciales que cambian poco
    return cached_db_query("SELECT...")

# Y en streamlit avanzado, puedes usar:
st.session_state.update({
    "initial_loaded": True  # Evitar recargas innecesarias
})

# Constantes
COOKIE_NAME = "my_app"
DB_CONNECTION_STRING = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
ALLOWED_OLT_TYPES = ["CTO VERDE", "CTO COMPARTIDA"]

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
        /* Prevenir flickering y parpadeos */
        .stApp {
            background-color: #f0f2f6;
        }
        /* Ocultar spinner por defecto, mostrarlo solo cuando sea necesario */
        div.stSpinner > div {
            opacity: 0;
            transition: opacity 0.3s ease-in-out;
        }
        div.stSpinner[data-testid="stSpinner"] > div {
            opacity: 1;
        }
        /* Mejorar rendimiento de renderizado */
        .element-container {
            contain: layout style paint;
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
            aplicar_filtros = st.button("🔍 Aplicar Filtros", type="primary", width='stretch')
        with col2:
            limpiar_filtros = st.button("🧹 Limpiar", width='stretch')

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
        if st.button("📍 Cargar datos del área", type="primary", width='stretch'):
            load_area_data(area_tipo_olt_filter)
    with col4:
        if st.button("🗑️ Limpiar filtro de área", width='stretch'):
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


# NUEVO: Función para crear popups completos
def create_complete_popup(row):
    """Crea popup completo con toda la información requerida"""
    return f"""
    <div style="font-family: Arial; font-size: 12px; min-width: 280px;">
        <div style="background-color: #f0f2f6; padding: 8px; border-radius: 5px; margin-bottom: 8px;">
            <strong>🏢 ID:</strong> {row['apartment_id']}<br>
        </div>

        <div style="margin-bottom: 8px;">
            <strong>📍 Ubicación:</strong><br>
            {row['provincia']}, {row['municipio']}<br>
            {row['vial']} {row['numero']}{row['letra'] or ''}<br>
            CP: {row['cp']}<br>
            📍 {row['latitud']:.6f}, {row['longitud']:.6f}
        </div>

        <div style="background-color: #e8f4fd; padding: 8px; border-radius: 5px;">
            <strong>🔧 Infraestructura:</strong><br>
            🏢 OLT: {row.get('olt', 'N/D')}<br>
            📡 CTO: {row.get('cto', 'N/D')}<br>
            🔢 CTO ID: {row.get('cto_id', 'N/D')}<br>
            🏭 Tipo OLT: {row.get('tipo_olt_rental', 'N/D')}
        </div>
    </div>
    """


@st.cache_data(ttl=3600, show_spinner=False)
def get_map_config_hash(_df_display):
    """Genera un hash único para la configuración del mapa basado en los datos"""
    if _df_display is None or _df_display.empty:
        return "empty_map"

    # Crear un hash basado en las coordenadas y cantidad de puntos
    coords_hash = hashlib.md5(
        pd.util.hash_pandas_object(_df_display[['latitud', 'longitud']].dropna()).values.tobytes()
    ).hexdigest()[:16]

    return f"map_{len(_df_display)}_{coords_hash}"


def create_map(df_display):
    """Crea y configura el mapa Folium con optimizaciones para muchos puntos"""
    if df_display.empty:
        return create_empty_map()

    # OPTIMIZACIÓN: Para muchos puntos, usar configuración más simple
    if len(df_display) > 1000:
        return create_optimized_map(df_display)

    # Configurar mapa según la cantidad de puntos
    if len(df_display) == 1:
        lat, lon = df_display['latitud'].iloc[0], df_display['longitud'].iloc[0]
        m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=21,
                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                       attr="Google",
                       prefer_canvas=True)
    else:
        lat, lon = df_display['latitud'].mean(), df_display['longitud'].mean()
        m = folium.Map(location=[lat, lon], zoom_start=12, max_zoom=21,
                       tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                       attr="Google",
                       prefer_canvas=True)
        bounds_data = [[df_display['latitud'].min(), df_display['longitud'].min()],
                       [df_display['latitud'].max(), df_display['longitud'].max()]]
        m.fit_bounds(bounds_data)

    # Añadir controles al mapa
    add_map_controls(m)

    # Añadir marcadores optimizados según cantidad
    add_optimized_markers(m, df_display)

    # Añadir leyenda
    add_legend(m)

    return m


def create_optimized_map(df_display):
    """Crea un mapa optimizado para grandes cantidades de puntos"""
    lat, lon = df_display['latitud'].mean(), df_display['longitud'].mean()

    m = folium.Map(
        location=[lat, lon],
        zoom_start=10,
        max_zoom=19,
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        prefer_canvas=True,
        control_scale=True
    )

    # Ajustar bounds para muchos puntos
    bounds_data = [[df_display['latitud'].min(), df_display['longitud'].min()],
                   [df_display['latitud'].max(), df_display['longitud'].max()]]
    m.fit_bounds(bounds_data, padding=(10, 10))

    # Añadir controles básicos
    add_map_controls(m)

    # Marcadores optimizados para muchos puntos
    add_high_performance_markers(m, df_display)

    # Leyenda simplificada
    add_legend(m)

    return m


def add_optimized_markers(m, df_display):
    """Añade marcadores optimizados según la cantidad de puntos"""
    if len(df_display) < 100:
        # Para pocos puntos: marcadores completos
        add_detailed_markers(m, df_display)
    elif len(df_display) < 1000:
        # Para cantidad media: cluster con información completa
        add_clustered_markers(m, df_display)
    else:
        # Para muchos puntos: cluster optimizado
        add_high_performance_markers(m, df_display)


def add_detailed_markers(m, df_display):
    """Marcadores detallados para pocos puntos"""
    for _, row in df_display.iterrows():
        create_marker(m, row, 0, 0)


def add_clustered_markers(m, df_display):
    """Marcadores con cluster para cantidad media de puntos"""
    marker_cluster = MarkerCluster(
        name="Puntos",
        overlay=True,
        control=True,
        icon_create_function=None,
        maxClusterRadius=10,
        minClusterSize=2,
        spiderfyOnMaxZoom=True
    )

    for _, row in df_display.iterrows():
        create_marker(marker_cluster, row, 0, 0)

    marker_cluster.add_to(m)


def add_high_performance_markers(m, df_display):
    """Marcadores optimizados para alto rendimiento con muchos puntos"""
    marker_cluster = MarkerCluster(
        name="Puntos",
        overlay=True,
        control=True,
        maxClusterRadius=15,
        minClusterSize=3,
        disableClusteringAtZoom=18,
        spiderfyOnMaxZoom=True,
        show_coverage_on_hover=False,
        zoom_to_bounds_on_click=True
    )

    # OPTIMIZACIÓN: Usar popups completos pero con diseño optimizado
    for _, row in df_display.iterrows():
        marker_color = get_marker_color(row.get("tipo_olt_rental", ""))

        # Tooltip simplificado para mejor rendimiento
        tooltip_text = f"🏢 {row['apartment_id']}"

        folium.Marker(
            location=[row['latitud'], row['longitud']],
            popup=folium.Popup(create_complete_popup(row), max_width=300),  # NUEVO: Popup completo
            tooltip=tooltip_text,
            icon=folium.Icon(color=marker_color, icon='info-sign')
        ).add_to(marker_cluster)

    marker_cluster.add_to(m)


def create_empty_map():
    """Crea un mapa vacío con controles básicos"""
    m = folium.Map(
        location=[40.4168, -3.7038],
        zoom_start=6,
        max_zoom=21,
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google",
        prefer_canvas=True
    )
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


def create_marker(layer, row, lat_offset, lon_offset):
    """Crea un marcador individual con popup completo"""
    marker_color = get_marker_color(row.get("tipo_olt_rental", ""))

    # NUEVO: Usar la función create_complete_popup para todos los marcadores
    popup_content = create_complete_popup(row)

    folium.Marker(
        location=[row['latitud'] + lat_offset, row['longitud'] + lon_offset],
        popup=folium.Popup(popup_content, max_width=300),
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
    if geometry["type"] == "Polygon":
        coords = geometry["coordinates"][0]
    else:
        coords = geometry["coordinates"][0]

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
    """Muestra la tabla de datos y opciones de descarga con optimizaciones"""
    st.subheader("📋 Datos Detallados")

    columnas_mostrar = [
        'apartment_id', 'provincia', 'municipio', 'poblacion', 'vial', 'numero', 'letra', 'cp',
        'olt', 'cto', 'cto_id', 'tipo_olt_rental', 'latitud', 'longitud'
    ]

    df_table_display = df_display[columnas_mostrar].copy()

    if len(df_table_display) > 500:
        st.info(f"📊 Mostrando {len(df_table_display)} registros. Use la descarga CSV para ver todos los datos.")

    st.dataframe(df_table_display, width='stretch')

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
        point_count = len(df_to_show)
        if point_count > 1000:
            st.toast(f"⚠️ Se están cargando {point_count} puntos. Esto puede afectar el rendimiento.")
        st.toast(f"📊 **Visualizando:** {point_count} puntos filtrados por ÁREA GEOGRÁFICA")
    elif st.session_state.get("demo_filtered_df") is not None:
        df_to_show = st.session_state.demo_filtered_df
        st.toast(f"📊 **Visualizando:** {len(df_to_show)} puntos filtrados por CAMPOS")
    else:
        df_to_show = None
        st.info("👆 **Selecciona un método de filtrado:** Usa los filtros de campos o dibuja un área en el mapa")

    return df_to_show


# NUEVO: Estado de sesión para evitar recargas innecesarias
def initialize_session_state():
    """Inicializa el estado de sesión para optimizar recargas"""
    if "map_initialized" not in st.session_state:
        st.session_state.map_initialized = False
    if "current_map_data" not in st.session_state:
        st.session_state.current_map_data = None
    if "map_hash" not in st.session_state:
        st.session_state.map_hash = None


def demo_dashboard():
    """Dashboard de demostración para visualización de puntos en mapa"""
    setup_page()

    # Inicializar estado de sesión
    initialize_session_state()

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

    # OPTIMIZACIÓN: Usar container para evitar re-render completo
    map_container = st.container()

    with map_container:
        # Visualización del mapa
        if df_to_show is not None:
            # Generar hash único para el mapa
            current_map_hash = get_map_config_hash(df_to_show)

            # Solo regenerar el mapa si los datos han cambiado
            if (not st.session_state.map_initialized or
                    st.session_state.map_hash != current_map_hash or
                    st.session_state.current_map_data is None or
                    len(st.session_state.current_map_data) != len(df_to_show)):

                # OPTIMIZACIÓN: Mostrar progreso solo si hay muchos puntos
                if len(df_to_show) > 500:
                    progress_text = f"Renderizando {len(df_to_show)} puntos en el mapa..."
                    progress_bar = st.progress(0, text=progress_text)

                    m = create_map(df_to_show)
                    progress_bar.progress(50, text="Mapa creado, cargando interfaz...")

                    map_data = st_folium(
                        m,
                        height=700,
                        width="100%",
                        key=f"demo_map_{current_map_hash}",
                        returned_objects=["last_active_drawing", "bounds"]
                    )

                    progress_bar.progress(100, text="¡Mapa cargado!")
                    time.sleep(0.5)
                    progress_bar.empty()
                else:
                    m = create_map(df_to_show)
                    map_data = st_folium(
                        m,
                        height=700,
                        width="100%",
                        key=f"demo_map_{current_map_hash}",
                        returned_objects=["last_active_drawing", "bounds"]
                    )

                # Actualizar estado de sesión
                st.session_state.update({
                    "map_initialized": True,
                    "current_map_data": df_to_show.copy(),
                    "map_hash": current_map_hash
                })
            else:
                # Reutilizar el mapa existente
                m = create_map(df_to_show)
                map_data = st_folium(
                    m,
                    height=700,
                    width="100%",
                    key=f"demo_map_{current_map_hash}",
                    returned_objects=["last_active_drawing", "bounds"]
                )

            process_drawn_area(map_data)
            display_data_table(df_to_show)
        else:
            m = create_empty_map()
            map_data = st_folium(
                m,
                height=500,
                width="100%",
                key="demo_map_empty",
                returned_objects=["last_active_drawing", "bounds"]
            )
            process_drawn_area(map_data)


if __name__ == "__main__":
    demo_dashboard()