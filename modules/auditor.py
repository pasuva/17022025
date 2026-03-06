# auditor.py
# Módulo para auditoría de facturación comparando contratos internos con fichero del partner.

import streamlit as st
import pandas as pd
import io
import sqlite3
import sqlitecloud
import re
from datetime import datetime
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_cookies_controller import CookieController
import warnings

cookie_name = "my_app"

# -------------------------------------------------------------------
# Funciones de conexión y trazabilidad
# -------------------------------------------------------------------
def obtener_conexion():
    """Retorna una nueva conexión a la base de datos SQLite Cloud."""
    try:
        conn = sqlitecloud.connect(
            "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
        )
        return conn
    except sqlite3.Error as e:
        print(f"Error al conectar con la base de datos: {e}")
        return None

def log_trazabilidad(usuario, accion, detalles):
    """Inserta un registro en la tabla de trazabilidad (opcional)."""
    try:
        conn = obtener_conexion()
        cursor = conn.cursor()
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
            VALUES (?, ?, ?, ?)
        """, (usuario, accion, detalles, fecha))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error registrando trazabilidad: {e}")

# -------------------------------------------------------------------
# Función de limpieza de identificadores
# -------------------------------------------------------------------
def limpiar_identificador(valor, modo='strip'):
    """
    Limpia un identificador según el modo:
    - 'strip': elimina espacios y convierte a string
    - 'digits': extrae solo dígitos (para IDs numéricos)
    """
    if pd.isna(valor) or valor is None:
        return ""
    valor = str(valor).strip()
    if modo == 'digits':
        # Extraer solo dígitos (eliminar cualquier carácter no numérico)
        valor = re.sub(r'\D', '', valor)
    return valor

# -------------------------------------------------------------------
# Carga de datos desde la base de datos (seguimiento_contratos)
# -------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner="Cargando contratos desde la BD...")
def cargar_contratos_bd() -> pd.DataFrame:
    """Carga todos los registros de la tabla seguimiento_contratos."""
    conn = obtener_conexion()
    if conn is None:
        st.error("No se pudo conectar a la base de datos.")
        return pd.DataFrame()
    try:
        query = "SELECT * FROM seguimiento_contratos"
        df = pd.read_sql(query, conn)
        # Normalizar nombres de columnas a minúsculas para facilitar manejo
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error al cargar contratos: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# -------------------------------------------------------------------
# Procesamiento de la comparación
# -------------------------------------------------------------------
def procesar_comparacion(df_bd: pd.DataFrame, df_partner: pd.DataFrame,
                         col_id_bd: str, col_id_partner: str,
                         modo_limpieza: str = 'strip'):
    """
    Compara dos DataFrames usando las columnas indicadas como identificador.
    Aplica limpieza según modo_limpieza ('strip' o 'digits').
    Devuelve tres DataFrames: coincidentes, solo_bd, solo_partner.
    """
    if df_bd.empty or df_partner.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Asegurar que las columnas existen
    if col_id_bd not in df_bd.columns:
        st.error(f"La columna '{col_id_bd}' no existe en los datos de la base de datos.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    if col_id_partner not in df_partner.columns:
        st.error(f"La columna '{col_id_partner}' no existe en el fichero subido.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Limpiar identificadores
    df_bd['_clean_id'] = df_bd[col_id_bd].apply(lambda x: limpiar_identificador(x, modo_limpieza))
    df_partner['_clean_id'] = df_partner[col_id_partner].apply(lambda x: limpiar_identificador(x, modo_limpieza))

    # Eliminar filas con ID vacío después de limpieza
    df_bd_clean = df_bd[df_bd['_clean_id'] != ""].copy()
    df_partner_clean = df_partner[df_partner['_clean_id'] != ""].copy()

    # Realizar merge para identificar coincidencias
    merged = df_bd_clean.merge(df_partner_clean, on='_clean_id', how='outer',
                                indicator=True, suffixes=('_bd', '_partner'))

    coincidentes = merged[merged['_merge'] == 'both']
    solo_bd = merged[merged['_merge'] == 'left_only']
    solo_partner = merged[merged['_merge'] == 'right_only']

    # Eliminar columnas auxiliares
    for df_temp in [coincidentes, solo_bd, solo_partner]:
        if '_merge' in df_temp.columns:
            df_temp.drop(columns=['_merge'], inplace=True)
        if '_clean_id' in df_temp.columns:
            df_temp.drop(columns=['_clean_id'], inplace=True)

    return coincidentes, solo_bd, solo_partner

# -------------------------------------------------------------------
# Función principal de la sección de auditoría
# -------------------------------------------------------------------
def mostrar_auditoria():
    """Página de auditoría de facturación: comparación con fichero del partner."""
    controller = CookieController(key="cookies")

    st.markdown(
        """
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
        """,
        unsafe_allow_html=True
    )

    # Sidebar con opción de menú más moderno
    with st.sidebar:
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
                        margin: 0 auto 10px auto;
                        text-align: center;
                    }
                    .user-info {
                        text-align: center;
                        font-size: 16px;
                        color: #333;
                        margin-bottom: 10px;
                    }
                    .welcome-msg {
                        text-align: center;
                        font-weight: bold;
                        font-size: 18px;
                        margin-top: 0;
                    }
                </style>

                <div class="user-circle">👤</div>
                <div class="user-info">Rol: Administrador</div>
                <div class="welcome-msg">¡Bienvenido, <strong>{username}</strong>!</div>
                <hr>
                """.replace("{username}", st.session_state['username']), unsafe_allow_html=True)

    st.markdown("""
        <style>
        .block-container { padding-top: 1rem; }
        </style>
    """, unsafe_allow_html=True)

    # Submenú horizontal
    sub_seccion = st.radio(
        "Selecciona una vista",
        ["Cargar fichero", "Informe comparativo"],
        horizontal=True,
        label_visibility="collapsed"
    )

    # Cargar datos de la BD (cacheados)
    df_bd = cargar_contratos_bd()

    if df_bd.empty:
        st.warning("No se pudieron cargar contratos desde la base de datos.")
        return

    # Mostrar información básica de la BD
    st.sidebar.markdown("### 📊 Datos internos")
    st.sidebar.info(f"Total contratos en BD: **{len(df_bd):,}**")
    if 'billing' in df_bd.columns:
        st.sidebar.info(f"Billing no nulos: **{df_bd['billing'].notna().sum():,}**")
    else:
        st.sidebar.warning("La columna 'billing' no existe en la BD.")

    # -------------------------------------------------------------------
    # Pestaña 1: Cargar fichero del partner
    # -------------------------------------------------------------------
    if sub_seccion == "Cargar fichero":
        st.header("📁 Cargar fichero del partner")
        st.markdown("Sube el archivo Excel o CSV que has recibido del partner. Debe contener una columna con el identificador de alta (normalmente **Servicio Id**).")

        uploaded_file = st.file_uploader(
            "Selecciona archivo",
            type=["xlsx", "xls", "csv"],
            key="auditor_file"
        )

        if uploaded_file is not None:
            try:
                # Leer según extensión
                if uploaded_file.name.endswith('.csv'):
                    df_partner = pd.read_csv(uploaded_file)
                else:
                    df_partner = pd.read_excel(uploaded_file)

                # Normalizar nombres de columnas a minúsculas
                df_partner.columns = [c.lower() for c in df_partner.columns]

                st.success(f"Fichero cargado correctamente: {len(df_partner)} filas.")
                st.dataframe(df_partner.head(10), width='stretch')

                # Seleccionar la columna que contiene el identificador
                # Por defecto, buscar "servicio id" o similar
                opciones = df_partner.columns.tolist()
                indice_default = 0
                for i, col in enumerate(opciones):
                    if 'servicio' in col or 'id' in col or 'billing' in col:
                        indice_default = i
                        break

                columna_id = st.selectbox(
                    "Selecciona la columna que contiene el identificador de alta (Servicio Id):",
                    options=opciones,
                    index=indice_default
                )

                # Guardar en session_state
                st.session_state['df_partner'] = df_partner
                st.session_state['partner_filename'] = uploaded_file.name
                st.session_state['partner_id_col'] = columna_id

                st.info("Ahora ve a la pestaña **Informe comparativo** para ver el análisis.")
            except Exception as e:
                st.error(f"Error al leer el archivo: {e}")

    # -------------------------------------------------------------------
    # Pestaña 2: Informe comparativo
    # -------------------------------------------------------------------
    else:  # sub_seccion == "Informe comparativo"
        st.header("📋 Informe comparativo")

        # Verificar si tenemos datos del partner
        if 'df_partner' not in st.session_state or st.session_state['df_partner'] is None:
            st.warning("Primero debes cargar un fichero del partner en la pestaña 'Cargar fichero'.")
            return

        df_partner = st.session_state['df_partner']
        partner_filename = st.session_state.get('partner_filename', 'fichero_partner')
        partner_id_col = st.session_state.get('partner_id_col', None)

        if partner_id_col is None:
            st.warning("No se ha seleccionado la columna identificadora. Ve a 'Cargar fichero' y selecciona una.")
            return

        # Opciones de limpieza
        with st.expander("⚙️ Opciones de comparación", expanded=False):
            modo_limpieza = st.radio(
                "Modo de limpieza de identificadores:",
                options=['Solo espacios (por defecto)', 'Extraer solo dígitos (para IDs numéricos)'],
                index=0,
                help="Si los identificadores tienen formatos distintos (ej. '12345' vs '12345.0'), prueba con 'Extraer solo dígitos'."
            )
            if modo_limpieza == 'Extraer solo dígitos (para IDs numéricos)':
                modo = 'digits'
            else:
                modo = 'strip'

            # Mostrar diagnóstico de valores
            if st.checkbox("🔍 Mostrar diagnóstico de valores (primeros 10 de cada columna)"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write("**BD - billing (primeros 10):**")
                    valores_bd = df_bd['billing'].dropna().astype(str).str.strip().head(10).tolist()
                    st.write(valores_bd)
                with col2:
                    st.write(f"**Partner - {partner_id_col} (primeros 10):**")
                    valores_partner = df_partner[partner_id_col].dropna().astype(str).str.strip().head(10).tolist()
                    st.write(valores_partner)

                if modo == 'digits':
                    st.write("**Versión limpia (solo dígitos):**")
                    col1, col2 = st.columns(2)
                    with col1:
                        limpios_bd = [re.sub(r'\D', '', v) for v in valores_bd]
                        st.write(limpios_bd)
                    with col2:
                        limpios_partner = [re.sub(r'\D', '', v) for v in valores_partner]
                        st.write(limpios_partner)

        # Realizar la comparación
        with st.spinner("Comparando datos..."):
            coincidentes, solo_bd, solo_partner = procesar_comparacion(
                df_bd, df_partner,
                col_id_bd='billing',
                col_id_partner=partner_id_col,
                modo_limpieza=modo
            )

        # -------------------------------------------------------------------
        # Métricas resumen
        # -------------------------------------------------------------------
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Contratos en BD", len(df_bd))
        with col2:
            st.metric("Registros partner", len(df_partner))
        with col3:
            st.metric("Coincidentes", len(coincidentes))
        with col4:
            st.metric("Solo en BD", len(solo_bd))
        st.caption(f"Solo en partner: {len(solo_partner)}")

        # -------------------------------------------------------------------
        # Separar coincidentes según estado
        # -------------------------------------------------------------------
        estados_validos = ['FINALIZADO']  # Solo se considera válido para facturación
        if not coincidentes.empty and 'estado' in coincidentes.columns:
            coincidentes_validos = coincidentes[coincidentes['estado'].isin(estados_validos)]
            coincidentes_problematicos = coincidentes[~coincidentes['estado'].isin(estados_validos)]
        else:
            coincidentes_validos = coincidentes
            coincidentes_problematicos = pd.DataFrame()

        # Mostrar alerta si hay problemáticos
        if not coincidentes_problematicos.empty:
            st.error(f"⚠️ **Atención:** Se han encontrado **{len(coincidentes_problematicos)}** contratos coincidentes con estado distinto de FINALIZADO. Revisa si se está cobrando indebidamente.")

        # -------------------------------------------------------------------
        # Pestañas para cada categoría
        # -------------------------------------------------------------------
        if len(coincidentes) > 0 or len(solo_bd) > 0 or len(solo_partner) > 0:
            # Creamos pestañas: Coincidentes totales, Problemáticos, Solo BD, Solo Partner
            tab_titles = [
                f"✅ Coincidentes totales ({len(coincidentes)})",
                f"⚠️ Coincidentes no finalizados ({len(coincidentes_problematicos)})",
                f"🔵 Solo en BD ({len(solo_bd)})",
                f"🟠 Solo en partner ({len(solo_partner)})"
            ]
            tabs = st.tabs(tab_titles)

            # Función auxiliar para mostrar tabla con AgGrid
            def mostrar_tabla_con_aggrid(df, key_suffix):
                if df.empty:
                    st.info("No hay registros en esta categoría.")
                    return
                # Seleccionar columnas para mostrar
                columnas_importantes = ['billing', 'num_contrato', 'cliente', 'estado',
                                        'fecha_inicio_contrato', 'comercial', partner_id_col]
                cols_mostrar = [c for c in columnas_importantes if c in df.columns]
                # Añadir algunas columnas adicionales si hay espacio
                otras_cols = [c for c in df.columns if c not in cols_mostrar][:5]
                cols_mostrar += otras_cols
                df_display = df[cols_mostrar].copy()

                gb = GridOptionsBuilder.from_dataframe(df_display)
                gb.configure_default_column(
                    filter=True,
                    floatingFilter=True,
                    sortable=True,
                    resizable=True,
                    minWidth=100,
                    flex=1
                )
                gb.configure_pagination(paginationAutoPageSize=True)
                gridOptions = gb.build()

                AgGrid(
                    df_display,
                    gridOptions=gridOptions,
                    enable_enterprise_modules=True,
                    update_mode=GridUpdateMode.NO_UPDATE,
                    height=400,
                    theme='alpine-dark',
                    key=f"grid_{key_suffix}"
                )

            with tabs[0]:
                mostrar_tabla_con_aggrid(coincidentes, "coincidentes_total")
            with tabs[1]:
                if not coincidentes_problematicos.empty:
                    mostrar_tabla_con_aggrid(coincidentes_problematicos, "coincidentes_problematicos")
                    # Resumen de estados problemáticos
                    st.markdown("#### Distribución de estados problemáticos")
                    estado_counts = coincidentes_problematicos['estado'].value_counts().reset_index()
                    estado_counts.columns = ['Estado', 'Cantidad']
                    st.dataframe(estado_counts, width='stretch', hide_index=True)
                else:
                    st.success("¡No hay coincidentes con estados problemáticos!")
            with tabs[2]:
                mostrar_tabla_con_aggrid(solo_bd, "solo_bd")
            with tabs[3]:
                mostrar_tabla_con_aggrid(solo_partner, "solo_partner")

            # -------------------------------------------------------------------
            # Botones de descarga
            # -------------------------------------------------------------------
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                # Descargar informe completo Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_bd.to_excel(writer, sheet_name='Contratos_BD', index=False)
                    df_partner.to_excel(writer, sheet_name='Fichero_Partner', index=False)
                    coincidentes.to_excel(writer, sheet_name='Coincidentes', index=False)
                    if not coincidentes_problematicos.empty:
                        coincidentes_problematicos.to_excel(writer, sheet_name='Coincidentes_Problematicos', index=False)
                    solo_bd.to_excel(writer, sheet_name='Solo_BD', index=False)
                    solo_partner.to_excel(writer, sheet_name='Solo_Partner', index=False)
                output.seek(0)

                st.download_button(
                    label="📥 Descargar informe completo (Excel)",
                    data=output,
                    file_name=f"auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_d2:
                # Descargar solo discrepancias (solo BD y solo partner)
                output_disc = io.BytesIO()
                with pd.ExcelWriter(output_disc, engine='xlsxwriter') as writer:
                    solo_bd.to_excel(writer, sheet_name='Solo_BD', index=False)
                    solo_partner.to_excel(writer, sheet_name='Solo_Partner', index=False)
                output_disc.seek(0)

                st.download_button(
                    label="📥 Descargar solo discrepancias",
                    data=output_disc,
                    file_name=f"discrepancias_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_d3:
                if st.button("🔄 Refrescar datos de BD", use_container_width=True):
                    st.cache_data.clear()
                    st.rerun()

        else:
            st.info("No hay datos para mostrar tras la comparación.")

        # -------------------------------------------------------------------
        # Análisis adicional de estados (opcional, ya se ve en pestaña)
        # -------------------------------------------------------------------
        if not coincidentes.empty and 'estado' in coincidentes.columns:
            with st.expander("🔍 Ver distribución completa de estados en coincidentes"):
                estado_counts = coincidentes['estado'].value_counts().reset_index()
                estado_counts.columns = ['Estado', 'Cantidad']
                st.dataframe(estado_counts, width='stretch', hide_index=True)

        # Registrar en trazabilidad
        log_trazabilidad(
            st.session_state.get("username", "auditor"),
            "Auditoría de facturación",
            f"Comparación con fichero {partner_filename}. Coincidentes={len(coincidentes)}, Problemáticos={len(coincidentes_problematicos)}, Solo BD={len(solo_bd)}, Solo Partner={len(solo_partner)}"
        )

# -------------------------------------------------------------------
# Para pruebas independientes (descomentar si se ejecuta solo)
# -------------------------------------------------------------------
# if __name__ == "__main__":
#     st.set_page_config(page_title="Auditoría de facturación", layout="wide")
#     mostrar_auditoria()