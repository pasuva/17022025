import streamlit as st
import pandas as pd
import sqlitecloud  # Importamos el cliente de SQLite Cloud
import io
from datetime import datetime
from streamlit_option_menu import option_menu
from streamlit_cookies_controller import CookieController  # Se importa localmente

cookie_name = "my_app"


# Función para registrar trazabilidad
def log_trazabilidad(usuario, accion, detalles):
    conn = sqlitecloud.connect(
        "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY")
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
        """,
        (usuario, accion, detalles, fecha)
    )
    conn.commit()
    conn.close()


# Función para crear índice si no existe en una tabla para la columna apartment_id
def create_index_if_not_exists(conn, table, index_name, column):
    cursor = conn.cursor()
    sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column});"
    cursor.execute(sql)
    conn.commit()

# Función para cargar datos de la tabla datos_uis
def load_datos_uis():
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        # Crear índice en datos_uis para apartment_id si no existe
        create_index_if_not_exists(conn, "datos_uis", "idx_datosuis_apartment_id", "apartment_id")

        query = "SELECT * FROM datos_uis"
        datos_uis_data = pd.read_sql(query, conn)

        conn.close()
        if datos_uis_data.empty:
            st.warning(f"⚠ No hay datos disponibles.")
        return datos_uis_data
    except Exception as e:
        st.error(f"❌ Error al cargar Datos UIS: {e}")
        return None


# Función para cargar datos de Ofertas Comerciales (combinando dos tablas)
def load_ofertas_comercial():
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        # Crear índice en ofertas_comercial para apartment_id si no existe
        create_index_if_not_exists(conn, "ofertas_comercial", "idx_ofertas_apartment_id", "apartment_id")
        # También, si es relevante, en comercial_rafa
        create_index_if_not_exists(conn, "comercial_rafa", "idx_comercial_rafa_apartment_id", "apartment_id")

        query_ofertas_comercial = "SELECT * FROM ofertas_comercial"
        query_comercial_rafa = "SELECT * FROM comercial_rafa"

        ofertas_comercial_data = pd.read_sql(query_ofertas_comercial, conn)
        comercial_rafa_data = pd.read_sql(query_comercial_rafa, conn)

        conn.close()

        # Comprobar si ambas tablas tienen datos y unirlos
        if ofertas_comercial_data.empty and comercial_rafa_data.empty:
            st.error("❌ No se encontraron ofertas realizadas por los comerciales.")
            return None

        comercial_rafa_data_filtrada = comercial_rafa_data[comercial_rafa_data['serviciable'].notna()]
        if not comercial_rafa_data_filtrada.empty:
            combined_data = pd.concat([ofertas_comercial_data, comercial_rafa_data_filtrada], ignore_index=True)
        else:
            combined_data = ofertas_comercial_data

        return combined_data
    except Exception as e:
        st.error(f"❌ Error al cargar Ofertas Comerciales: {e}")
        return None


# Función para cargar datos de Viabilidades
def load_viabilidades():
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        # Crear índice en viabilidades para apartment_id si no existe
        create_index_if_not_exists(conn, "viabilidades", "idx_viabilidades_apartment_id", "apartment_id")

        query = "SELECT * FROM viabilidades"
        viabilidades_data = pd.read_sql(query, conn)

        conn.close()
        if viabilidades_data.empty:
            st.warning(f"⚠ No hay datos disponibles.")
        return viabilidades_data
    except Exception as e:
        st.error(f"❌ Error al cargar Viabilidades: {e}")
        return None


# Función principal del dashboard
def supervisor_dashboard():
    controller = CookieController(key="cookies")

    st.sidebar.title("📁 Panel del Supervisor")
    with st.sidebar:
        st.sidebar.markdown(""" 
            <style> 
                .user-circle { 
                    width: 100px; 
                    height: 100px; 
                    border-radius: 50%; 
                    background-color: #28a745; 
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
            <div>Rol: Supervisor</div>
        """, unsafe_allow_html=True)

        st.sidebar.write(f"Bienvenido, {st.session_state['username']}")
        st.sidebar.markdown("---")
        # Menú lateral con las tres opciones
        menu_opcion = option_menu(
            menu_title=None,
            options=["Datos UIS", "Ofertas Comerciales", "Viabilidades"],
            icons=["graph-up", "bar-chart", "check-circle"],
            menu_icon="list",
            default_index=0,
            styles={
                "container": {"padding": "0px", "background-color": "#262730"},
                "icon": {"color": "#ffffff", "font-size": "18px"},
                "nav-link": {
                    "color": "#ffffff", "font-size": "16px", "text-align": "left", "margin": "0px"
                },
                "nav-link-selected": {
                    "background-color": "#0073e6", "color": "white"
                }
            }
        )

    detalles = f"El supervisor seleccionó la vista '{menu_opcion}'."
    log_trazabilidad(st.session_state["username"], "Selección de vista", detalles)

    st.info(
        "ℹ️ En este panel puedes visualizar los datos de Datos UIS, Ofertas Comerciales o Viabilidades, filtrar columnas, buscar elementos concretos y descargar los datos en CSV o Excel."
    )

    with st.sidebar:
        if st.button("Cerrar sesión"):
            detalles = f"El supervisor {st.session_state.get('username', 'N/A')} cerró sesión."
            log_trazabilidad(st.session_state.get("username", "N/A"), "Cierre sesión", detalles)

            # Establecer la expiración de las cookies en el pasado para forzar su eliminación
            controller.set(f'{cookie_name}_session_id', '', max_age=0, expires=datetime(1970, 1, 1))
            controller.set(f'{cookie_name}_username', '', max_age=0, expires=datetime(1970, 1, 1))
            controller.set(f'{cookie_name}_role', '', max_age=0, expires=datetime(1970, 1, 1))

            # Reiniciar el estado de sesión
            st.session_state["login_ok"] = False
            st.session_state["username"] = ""
            st.session_state["role"] = ""
            st.session_state["session_id"] = ""

            # Limpiar parámetros de la URL
            st.experimental_set_query_params()
            st.success("✅ Has cerrado sesión correctamente. Redirigiendo al login...")
            st.rerun()

    if "data" in st.session_state:
        del st.session_state["data"]

    # Dependiendo de la opción seleccionada se carga la vista correspondiente
    if menu_opcion == "Datos UIS":
        with st.spinner("⏳ Cargando Datos UIS..."):
            data = load_datos_uis()
    elif menu_opcion == "Ofertas Comerciales":
        with st.spinner("⏳ Cargando Ofertas Comerciales..."):
            data = load_ofertas_comercial()
    elif menu_opcion == "Viabilidades":
        with st.spinner("⏳ Cargando Viabilidades..."):
            data = load_viabilidades()
    else:
        data = None

    if data is None:
        return

    # Eliminar columnas duplicadas si existen
    if data.columns.duplicated().any():
        st.warning("¡Se encontraron columnas duplicadas! Se eliminarán las duplicadas.")
        data = data.loc[:, ~data.columns.duplicated()]

    st.session_state["data"] = data

    st.subheader("Filtrar Columnas")
    columnas = st.multiselect("Selecciona las columnas a mostrar", data.columns.tolist(), default=data.columns.tolist())

    st.subheader("Datos Cargados")
    st.dataframe(data[columnas], use_container_width=True)

    st.subheader("Descargar Datos")
    descarga_opcion = st.radio("¿Cómo quieres descargar los datos?", ["CSV", "Excel"])

    if descarga_opcion == "CSV":
        detalles = f"El supervisor descargó los datos en formato CSV."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)
        st.download_button(
            label="Descargar como CSV",
            data=data[columnas].to_csv(index=False).encode(),
            file_name="datos_descargados.csv",
            mime="text/csv"
        )
    elif descarga_opcion == "Excel":
        detalles = f"El supervisor descargó los datos en formato Excel."
        log_trazabilidad(st.session_state["username"], "Descarga de datos", detalles)
        with st.spinner("Generando archivo Excel... Esto puede tardar unos segundos."):
            towrite = io.BytesIO()
            with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
                data[columnas].to_excel(writer, index=False, sheet_name="Datos")
            towrite.seek(0)
            st.download_button(
                label="Descargar como Excel",
                data=towrite,
                file_name="datos_descargados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    st.info("Recuerda que, dependiendo del tamaño de los datos, la descarga puede tardar algunos segundos.")


if __name__ == "__main__":
    supervisor_dashboard()
