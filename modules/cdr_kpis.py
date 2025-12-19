# cdr_kpis.py
from datetime import datetime

import pandas as pd
import gspread
import os
import json
import streamlit as st
from google.oauth2.service_account import Credentials
# Añadir al principio del archivo, después de los imports existentes:
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib import colors
from reportlab.lib.units import inch
import tempfile

# ==================== CONFIGURACIÓN DEPARTAMENTAL ====================
# Diccionario de mapeo: Extensión -> Departamento
MAPEO_DEPARTAMENTOS = {
    '1001': 'Administración',
    '1002': 'Comercial',
    '1003': 'Soporte Técnico',
    # Añade aquí todas las extensiones que conozcas
}


def asignar_departamento(numero):
    """Asigna un departamento a un número de extensión o externo."""
    # Busca en el mapeo
    if str(numero) in MAPEO_DEPARTAMENTOS:
        return MAPEO_DEPARTAMENTOS[str(numero)]
    # Heurística para números externos (ajústala)
    elif str(numero).isdigit() and len(str(numero)) >= 9:
        return 'Externo (Teléfono)'
    elif str(numero).startswith('s') or str(numero) == 's':  # Como en tu ejemplo
        return 'Servicio/IVR'
    else:
        return 'Desconocido/Externo'


def clasificar_interaccion(fila):
    """Clasifica el tipo de interacción entre departamentos."""
    origen = fila['dept_origen']
    destino = fila['dept_destino']

    if origen == destino and origen in ['Administración', 'Comercial', 'Soporte Técnico']:
        return 'Interna (mismo dept)'
    elif origen in ['Administración', 'Comercial', 'Soporte Técnico'] and destino in ['Administración', 'Comercial',
                                                                                      'Soporte Técnico']:
        return 'Colaboración (dept a dept)'
    elif origen in ['Administración', 'Comercial', 'Soporte Técnico'] and destino == 'Externo (Teléfono)':
        return 'Llamada Saliente'
    elif origen == 'Externo (Teléfono)' and destino in ['Administración', 'Comercial', 'Soporte Técnico']:
        return 'Llamada Entrante'
    else:
        return 'Otra'

def cargar_y_procesar_cdr():
    """
    Función principal que carga los datos del CDR desde Google Sheets,
    los procesa y calcula los KPIs.

    Returns:
        tuple: (DataFrame de datos procesados, diccionario de KPIs)
               o (None, None) en caso de error.
    """
    try:
        # --- Detectar entorno y elegir archivo de credenciales ---
        # (Usamos la misma lógica que en cargar_contratos_google)
        posibles_rutas = [
            "modules/carga-contratos-verde-c5068516c7cf.json",  # Render: secret file
            "/etc/secrets/carga-contratos-verde-c5068516c7cf.json",  # Otra ruta posible en Render
            os.path.join(os.path.dirname(__file__), "carga-contratos-verde-c5068516c7cf.json"),  # Local
        ]

        ruta_credenciales = None
        for r in posibles_rutas:
            if os.path.exists(r):
                ruta_credenciales = r
                break

        if not ruta_credenciales and "GOOGLE_APPLICATION_CREDENTIALS_JSON" in os.environ:
            # Si no hay archivo pero sí variable de entorno
            creds_dict = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = Credentials.from_service_account_info(creds_dict, scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ])
        elif ruta_credenciales:
            print(f"🔑 Usando credenciales desde: {ruta_credenciales}")
            creds = Credentials.from_service_account_file(
                ruta_credenciales,
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]
            )
        else:
            raise ValueError("❌ No se encontraron credenciales de Google Service Account.")

        # Crear cliente
        client = gspread.authorize(creds)

        # --- Abrir la hoja de Google Sheets del CDR ---
        # NOTA: Debes ajustar el nombre de la hoja y la pestaña según tu caso
        sheet = client.open("CDR VERDE PBX").worksheet("CDR VERDE PBX")
        data = sheet.get_all_records()

        if not data:
            print("⚠️ Hoja cargada pero sin registros. Revisa si la primera fila tiene encabezados correctos.")
            return pd.DataFrame(), {}

        df = pd.DataFrame(data)

        # --- Procesamiento específico del CDR ---
        # 1. Normalizar nombres de columnas (como en tu función de contratos)
        df.columns = df.columns.map(lambda x: str(x).strip().upper() if x is not None else "")

        # 2. Mapeo de columnas a nombres más manejables (opcional, pero recomendable)
        # Aquí debes definir el mapeo según las columnas de tu CDR.
        # Ejemplo basado en la muestra que mostraste:
        column_mapping = {
            'CALLDATE': 'calldate',
            'CLID': 'clid',
            'SRC': 'src',
            'DST': 'dst',
            'DCONTEXT': 'dcontext',
            'CHANNEL': 'channel',
            'DSTCHANNEL': 'dstchannel',
            'LASTAPP': 'lastapp',
            'LASTDATA': 'lastdata',
            'DURATION': 'duration',
            'BILLSEC': 'billsec',
            'DISPOSITION': 'disposition',
            'AMAFLAGS': 'amaflags',
            'ACCOUNTCODE': 'accountcode',
            'UNIQUEID': 'uniqueid',
            'USERFIELD': 'userfield',
            'DID': 'did',
            'CNUM': 'cnum',
            'CNAM': 'cnam',
            'OUTBOUND_CNUM': 'outbound_cnum',
            'OUTBOUND_CNAM': 'outbound_cnam',
            'DST_CNAM': 'dst_cnam',
            'RECORDINGFILE': 'recordingfile',
            'LINKEDID': 'linkedid',
            'PEERACCOUNT': 'peeraccount',
            'SEQUENCE': 'sequence'
        }

        # Renombrar las columnas según el mapeo (solo las que existan)
        df.rename(columns={col: column_mapping[col] for col in column_mapping if col in df.columns}, inplace=True)

        # 3. Convertir tipos de datos
        if 'calldate' in df.columns:
            df['calldate'] = pd.to_datetime(df['calldate'], dayfirst=True, errors='coerce')

        # Convertir columnas numéricas
        numeric_cols = ['duration', 'billsec']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # 4. Calcular KPIs
        kpis = calcular_kpis_cdr(df)

        return df, kpis

    except Exception as e:
        print(f"❌ Error en cargar_y_procesar_cdr: {e}")
        return None, None


# ==================== FUNCIONES DE CÁLCULO DE KPIS ====================
def calcular_kpis_cdr(df):
    """
    Calcula los KPIs a partir del DataFrame del CDR.

    Args:
        df (pd.DataFrame): DataFrame procesado del CDR.

    Returns:
        dict: Diccionario con los KPIs calculados.
    """
    if df.empty:
        return {}

    kpis = {
        'total_llamadas': len(df),
        'llamadas_contestadas': len(df[df['disposition'] == 'ANSWERED']) if 'disposition' in df.columns else 0,
        'llamadas_no_contestadas': len(
            df[df['disposition'].isin(['NO ANSWER', 'BUSY', 'FAILED'])]) if 'disposition' in df.columns else 0,
        'duracion_total_segundos': df['duration'].sum() if 'duration' in df.columns else 0,
        'duracion_promedio_segundos': df['duration'].mean() if 'duration' in df.columns else 0,
        'facturacion_total_segundos': df['billsec'].sum() if 'billsec' in df.columns else 0,
        'extensiones_unicas': df['src'].nunique() if 'src' in df.columns else 0,
    }

    # Si hay columna de fecha, agregar KPIs por tiempo
    if 'calldate' in df.columns and not df['calldate'].isnull().all():
        df['fecha'] = df['calldate'].dt.date
        llamadas_por_dia = df.groupby('fecha').size().to_dict()
        kpis['llamadas_por_dia'] = llamadas_por_dia

    return kpis


def calcular_kpis_cdr_ampliada(df):
    """
    Calcula un conjunto ampliado de KPIs a partir del DataFrame del CDR.

    Args:
        df (pd.DataFrame): DataFrame procesado del CDR.

    Returns:
        dict: Diccionario con KPIs básicos y ampliados, y DataFrames para visualización.
    """
    if df.empty:
        return {}

    # 1. Comienza con los KPIs básicos que ya tenías
    kpis = calcular_kpis_cdr(df)

    # 2. KPIs de EFICIENCIA OPERATIVA
    # Tasa de respuesta y abandono
    if 'disposition' in df.columns:
        total = len(df)
        contestadas = len(df[df['disposition'] == 'ANSWERED'])
        no_contestadas = len(df[df['disposition'].isin(['NO ANSWER', 'BUSY'])])
        fallidas = len(df[df['disposition'] == 'FAILED'])

        kpis['tasa_respuesta'] = (contestadas / total * 100) if total > 0 else 0
        kpis['tasa_abandono'] = (no_contestadas / total * 100) if total > 0 else 0
        kpis['llamadas_fallidas'] = fallidas

    # 3. KPIs de DISTRIBUCIÓN TEMPORAL (Patrones de uso)
    if 'calldate' in df.columns:
        df['hora'] = df['calldate'].dt.hour
        df['dia_semana'] = df['calldate'].dt.day_name()
        df['es_fin_semana'] = df['calldate'].dt.weekday >= 5  # 5=Sábado, 6=Domingo

        # Llamadas por franja horaria (para identificar picos)
        llamadas_por_hora = df.groupby('hora').size()
        kpis['llamadas_por_hora_dict'] = llamadas_por_hora.to_dict()
        kpis['hora_pico'] = llamadas_por_hora.idxmax() if not llamadas_por_hora.empty else None
        kpis['llamadas_hora_pico'] = llamadas_por_hora.max() if not llamadas_por_hora.empty else 0

        # Llamadas por día de la semana
        dias_orden = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        llamadas_por_dia = df['dia_semana'].value_counts()
        llamadas_por_dia = llamadas_por_dia.reindex(dias_orden, fill_value=0)
        kpis['llamadas_por_dia_dict'] = llamadas_por_dia.to_dict()
        kpis['dia_mas_activo'] = llamadas_por_dia.idxmax() if not llamadas_por_dia.empty else None

        # Distribución fin de semana vs. laborable
        kpis['llamadas_fin_semana'] = df['es_fin_semana'].sum()
        kpis['llamadas_laborables'] = len(df) - kpis['llamadas_fin_semana']

    # 4. KPIs de ANÁLISIS DE ORIGEN Y DESTINO
    if 'src' in df.columns:
        # Top extensiones que más llaman
        top_origen = df['src'].value_counts().head(10)
        kpis['top_origen_dict'] = top_origen.to_dict()
        kpis['extension_mas_activa'] = top_origen.index[0] if not top_origen.empty else None
        kpis['llamadas_extension_top'] = top_origen.iloc[0] if not top_origen.empty else 0

    if 'dst' in df.columns:
        # Top destinos más llamados
        top_destino = df['dst'].value_counts().head(10)
        kpis['top_destino_dict'] = top_destino.to_dict()
        kpis['destino_mas_frecuente'] = top_destino.index[0] if not top_destino.empty else None

        # Identificar si la llamada fue interna (ambos extremos son extensiones) o externa
        def es_extension(x):
            try:
                return str(x).isdigit() and 1000 <= int(x) <= 9999  # Ejemplo: extensiones de 4 dígitos
            except:
                return False

        # Contar llamadas internas (src y dst son extensiones)
        df['es_interna'] = df.apply(lambda fila: es_extension(fila.get('src')) and es_extension(fila.get('dst')),
                                    axis=1)
        kpis['llamadas_internas'] = df['es_interna'].sum()
        kpis['llamadas_externas'] = len(df) - kpis['llamadas_internas']

    # 5. KPIs de FACTURACIÓN Y COSTE (si aplica)
    if 'billsec' in df.columns:
        # Tiempo total facturable (en minutos, para mayor claridad)
        kpis['minutos_facturables'] = df['billsec'].sum() / 60.0

        # Relación entre duración real y tiempo facturado (para eficiencia)
        if 'duration' in df.columns:
            # Evitar división por cero: usar sólo llamadas con duración > 0
            df_con_duracion = df[df['duration'] > 0]
            if not df_con_duracion.empty:
                kpis['ratio_facturacion_vs_duracion'] = (
                        df_con_duracion['billsec'].sum() / df_con_duracion['duration'].sum())

    # 6. KPIs POR DEPARTAMENTO
    df['dept_origen'] = df['src'].apply(asignar_departamento)
    df['dept_destino'] = df['dst'].apply(asignar_departamento)

    # Resumen de actividad por departamento (como origen de la llamada)
    actividad_por_depto = df['dept_origen'].value_counts()
    kpis['actividad_por_depto_dict'] = actividad_por_depto.to_dict()

    # Duración total y promedio por departamento (origen)
    if 'duration' in df.columns:
        duracion_por_depto = df.groupby('dept_origen')['duration'].agg(['sum', 'mean', 'count'])
        kpis['duracion_por_depto_df'] = duracion_por_depto.reset_index().rename(
            columns={'sum': 'duracion_total_seg', 'mean': 'duracion_promedio_seg', 'count': 'llamadas'}
        )

    # Tasa de respuesta por departamento (si el origen es un departamento interno)
    if 'disposition' in df.columns:
        for dept in ['Administración', 'Comercial', 'Soporte Técnico']:
            df_dept = df[df['dept_origen'] == dept]
            if not df_dept.empty:
                total_dept = len(df_dept)
                contestadas_dept = len(df_dept[df_dept['disposition'] == 'ANSWERED'])
                kpis[f'tasa_respuesta_{dept.lower().replace(" ", "_")}'] = (
                            contestadas_dept / total_dept * 100) if total_dept > 0 else 0

    # 7. ANÁLISIS DE INTERACCIÓN ENTRE DEPARTAMENTOS
    if 'dept_origen' in df.columns and 'dept_destino' in df.columns:
        df['tipo_interaccion'] = df.apply(clasificar_interaccion, axis=1)

        # Resumen de tipos de interacción
        kpis['interacciones_por_tipo_dict'] = df['tipo_interaccion'].value_counts().to_dict()

        # Matriz de colaboración entre departamentos (para un heatmap)
        colaboracion = df[
            (df['dept_origen'].isin(['Administración', 'Comercial', 'Soporte Técnico'])) &
            (df['dept_destino'].isin(['Administración', 'Comercial', 'Soporte Técnico']))
            ]
        if not colaboracion.empty:
            matriz_colab = pd.crosstab(colaboracion['dept_origen'], colaboracion['dept_destino'])
            kpis['matriz_colaboracion_df'] = matriz_colab

    # 8. DATA FRAMES para visualizaciones específicas
    kpis['df_resumen_disposition'] = df['disposition'].value_counts().reset_index().rename(
        columns={'index': 'Estado', 'disposition': 'Cantidad'}) if 'disposition' in df.columns else None

    return kpis


# ==================== FUNCIÓN DE VISUALIZACIÓN EN STREAMLIT ====================
def mostrar_cdrs():
    """FUNCIÓN PRINCIPAL: Muestra toda la sección de CDRs en Streamlit."""

    # Función auxiliar para hacer serializable el diccionario de KPIs
    def fix_keys_for_json(obj):
        """
        Convierte las claves de un diccionario a string para que sea serializable en JSON.
        """
        if isinstance(obj, dict):
            new_dict = {}
            for key, value in obj.items():
                # Convertir la clave a string si no es de un tipo básico
                if not isinstance(key, (str, int, float, bool, type(None))):
                    key = str(key)
                new_dict[key] = fix_keys_for_json(value)
            return new_dict
        elif isinstance(obj, list):
            return [fix_keys_for_json(item) for item in obj]
        else:
            return obj

    st.info("ℹ️ Aquí puedes generar informes basados en los datos disponibles.")

    # Botón para cargar y procesar
    if st.button("Cargar y analizar CDR"):
        with st.spinner("Cargando datos desde Google Sheets..."):
            df_cdr, _ = cargar_y_procesar_cdr()  # Obtén el DataFrame
            # Calcula los KPIs ampliados
            kpis = calcular_kpis_cdr_ampliada(df_cdr)

        if df_cdr is not None and not df_cdr.empty:
            st.success(f"✅ Datos cargados correctamente. Total de llamadas: {len(df_cdr)}")

            # SECCIÓN DE EXPORTACIÓN - NUEVA
            col1, col2, col3 = st.columns(3)

            with col1:
                # Botón para generar y descargar PDF
                if st.button("📄 Generar Informe PDF", use_container_width=True):
                    with st.spinner("Generando PDF..."):
                        # Usamos el nombre de archivo temporal
                        pdf_path = generar_pdf_kpis(kpis, df_cdr, "informe_cdr.pdf")

                        # Leer el archivo PDF generado
                        with open(pdf_path, 'rb') as pdf_file:
                            pdf_bytes = pdf_file.read()

                        # Botón para descargar el PDF
                        st.download_button(
                            label="⬇️ Descargar PDF",
                            data=pdf_bytes,
                            file_name=f"informe_cdr_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )

            # Crear pestañas para organizar la información (AHORA CON 5 PESTAÑAS)
            tab1, tab2, tab3, tab4, tab5 = st.tabs(
                ["📈 Resumen General", "🕒 Patrones", "📞 Origen y Destino", "🏢 Análisis por Departamento", "📋 Detalles"])

            with tab1:  # Pestaña 1: Resumen General
                st.subheader("KPIs Principales")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Llamadas Totales", kpis.get('total_llamadas', 0))
                    st.metric("Tasa de Respuesta", f"{kpis.get('tasa_respuesta', 0):.1f}%")
                    st.metric("Duración Promedio", f"{kpis.get('duracion_promedio_segundos', 0):.1f} s")
                with col2:
                    st.metric("Extensiones Únicas", kpis.get('extensiones_unicas', 0))
                    st.metric("Llamadas Internas", kpis.get('llamadas_internas', 0))
                    st.metric("Minutos Facturables", f"{kpis.get('minutos_facturables', 0):.1f}")

                # Gráfico de llamadas por día (KPI básico)
                if 'llamadas_por_dia' in kpis:
                    st.subheader("Llamadas por Día")
                    df_por_dia = pd.DataFrame(list(kpis['llamadas_por_dia'].items()), columns=['Fecha', 'Llamadas'])
                    st.bar_chart(df_por_dia.set_index('Fecha'))

            with tab2:  # Pestaña 2: Patrones Temporales
                st.subheader("Distribución por Franja Horaria")
                if 'llamadas_por_hora_dict' in kpis:
                    df_hora = pd.DataFrame(list(kpis['llamadas_por_hora_dict'].items()), columns=['Hora', 'Llamadas'])
                    st.bar_chart(df_hora.set_index('Hora'))
                    st.caption(
                        f"**Hora pico:** {kpis.get('hora_pico')}:00 h ({kpis.get('llamadas_hora_pico')} llamadas)")

                st.subheader("Distribución por Día de la Semana")
                if 'llamadas_por_dia_dict' in kpis:
                    df_dia_semana = pd.DataFrame(list(kpis['llamadas_por_dia_dict'].items()),
                                                 columns=['Día', 'Llamadas'])
                    st.bar_chart(df_dia_semana.set_index('Día'))

            with tab3:  # Pestaña 3: Origen y Destino
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Top 5 Extensiones de Origen")
                    if 'top_origen_dict' in kpis:
                        df_origen = pd.DataFrame(list(kpis['top_origen_dict'].items()),
                                                 columns=['Extensión', 'Llamadas']).head(5)
                        st.dataframe(df_origen, use_container_width=True)

                with col2:
                    st.subheader("Top 5 Destinos")
                    if 'top_destino_dict' in kpis:
                        df_destino = pd.DataFrame(list(kpis['top_destino_dict'].items()),
                                                  columns=['Destino', 'Llamadas']).head(5)
                        st.dataframe(df_destino, use_container_width=True)

                # Métricas de distribución
                st.subheader("Distribución Interna/Externa")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Llamadas Internas", kpis.get('llamadas_internas', 0))
                with col2:
                    st.metric("Llamadas Externas", kpis.get('llamadas_externas', 0))
                with col3:
                    total = kpis.get('llamadas_internas', 0) + kpis.get('llamadas_externas', 0)
                    porcentaje_internas = (kpis.get('llamadas_internas', 0) / total * 100) if total > 0 else 0
                    st.metric("% Internas", f"{porcentaje_internas:.1f}%")

            with tab4:  # Pestaña 4: Análisis por Departamento (NUEVA)
                st.subheader("Actividad por Departamento (Como Origen)")

                if 'actividad_por_depto_dict' in kpis:
                    df_dept = pd.DataFrame(list(kpis['actividad_por_depto_dict'].items()),
                                           columns=['Departamento', 'Llamadas'])
                    # Filtrar solo departamentos internos para el gráfico
                    dept_internos = ['Administración', 'Comercial', 'Soporte Técnico']
                    df_dept_filtrado = df_dept[df_dept['Departamento'].isin(dept_internos)]

                    if not df_dept_filtrado.empty:
                        st.bar_chart(df_dept_filtrado.set_index('Departamento'))

                # Métricas comparativas por departamento
                st.subheader("Comparativa de Rendimiento")
                if 'duracion_por_depto_df' in kpis:
                    df_duracion = kpis['duracion_por_depto_df']
                    df_duracion_internos = df_duracion[
                        df_duracion['dept_origen'].isin(['Administración', 'Comercial', 'Soporte Técnico'])]

                    cols = st.columns(len(df_duracion_internos))
                    for idx, (_, fila) in enumerate(df_duracion_internos.iterrows()):
                        with cols[idx]:
                            st.metric(
                                label=f"{fila['dept_origen']}",
                                value=f"{fila['llamadas']} llamadas",
                                delta=f"Prom: {fila['duracion_promedio_seg']:.0f}s"
                            )

                # Matriz de colaboración entre departamentos
                st.subheader("Interacción entre Departamentos")
                if 'matriz_colaboracion_df' in kpis:
                    st.write("¿Cómo colaboran los equipos entre sí? (Origen → Destino)")
                    matriz = kpis['matriz_colaboracion_df']
                    st.dataframe(matriz.style.background_gradient(cmap='Blues'), use_container_width=True)

                # Tipos de interacción
                st.subheader("Distribución por Tipo de Llamada")
                if 'interacciones_por_tipo_dict' in kpis:
                    df_tipo = pd.DataFrame(list(kpis['interacciones_por_tipo_dict'].items()),
                                           columns=['Tipo de Interacción', 'Cantidad'])
                    st.bar_chart(df_tipo.set_index('Tipo de Interacción'))

            with tab5:  # Pestaña 5: Detalles y Datos Crudos
                st.subheader("Estado de las Llamadas")
                if kpis.get('df_resumen_disposition') is not None:
                    st.dataframe(kpis['df_resumen_disposition'], use_container_width=True)

                st.subheader("Muestra de los Datos Crudos")
                st.dataframe(df_cdr.head(20), use_container_width=True)
        else:
            st.error("No se pudieron cargar los datos o no hay registros.")


def generar_pdf_kpis(kpis, df=None, nombre_archivo="informe_cdr.pdf"):
    """
    Genera un archivo PDF con los KPIs y opcionalmente una muestra de los datos.

    Args:
        kpis (dict): Diccionario con los KPIs calculados.
        df (pd.DataFrame, optional): DataFrame con los datos del CDR.
        nombre_archivo (str): Nombre del archivo PDF a generar.

    Returns:
        str: Ruta al archivo PDF generado.
    """
    # Crear un archivo temporal para el PDF
    temp_dir = tempfile.gettempdir()
    pdf_path = os.path.join(temp_dir, nombre_archivo)

    # Crear el documento
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []

    # Estilos
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=TA_CENTER
    )
    estilo_subtitulo = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=12,
        alignment=TA_LEFT
    )
    estilo_texto = styles['Normal']

    # Título del informe
    elements.append(Paragraph("Informe de KPIs - CDR", estilo_titulo))
    elements.append(Spacer(1, 0.25 * inch))

    # 1. KPIs Principales
    elements.append(Paragraph("1. KPIs Principales", estilo_subtitulo))

    # Definir los datos de la tabla de KPIs principales
    datos_kpis = [
        ["KPI", "Valor"],
        ["Total de llamadas", str(kpis.get('total_llamadas', 0))],
        ["Llamadas contestadas", str(kpis.get('llamadas_contestadas', 0))],
        ["Tasa de respuesta", f"{kpis.get('tasa_respuesta', 0):.1f}%"],
        ["Duración total (seg)", f"{kpis.get('duracion_total_segundos', 0):.0f}"],
        ["Duración promedio (seg)", f"{kpis.get('duracion_promedio_segundos', 0):.1f}"],
        ["Minutos facturables", f"{kpis.get('minutos_facturables', 0):.1f}"],
        ["Llamadas internas", str(kpis.get('llamadas_internas', 0))],
        ["Llamadas externas", str(kpis.get('llamadas_externas', 0))],
    ]

    tabla_kpis = Table(datos_kpis, colWidths=[3 * inch, 2 * inch])
    tabla_kpis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(tabla_kpis)
    elements.append(Spacer(1, 0.25 * inch))

    # 2. KPIs por Departamento (si existen)
    if 'actividad_por_depto_dict' in kpis:
        elements.append(Paragraph("2. Actividad por Departamento", estilo_subtitulo))

        datos_dept = [["Departamento", "Llamadas"]]
        for dept, llamadas in kpis['actividad_por_depto_dict'].items():
            # Mostrar solo departamentos internos y los principales
            if dept in ['Administración', 'Comercial', 'Soporte Técnico'] or llamadas > 0:
                datos_dept.append([dept, str(llamadas)])

        if len(datos_dept) > 1:
            tabla_dept = Table(datos_dept, colWidths=[3 * inch, 2 * inch])
            tabla_dept.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(tabla_dept)
            elements.append(Spacer(1, 0.25 * inch))

    # 3. Top Extensiones y Destinos
    if 'top_origen_dict' in kpis and 'top_destino_dict' in kpis:
        elements.append(Paragraph("3. Top Extensiones y Destinos", estilo_subtitulo))

        # Tomar los 5 primeros de cada uno
        top_origen = list(kpis['top_origen_dict'].items())[:5]
        top_destino = list(kpis['top_destino_dict'].items())[:5]

        # Combinar en una tabla de dos columnas
        datos_top = [["Top Extensiones (Origen)", "Top Destinos"]]
        max_len = max(len(top_origen), len(top_destino))
        for i in range(max_len):
            origen = top_origen[i] if i < len(top_origen) else ('', '')
            destino = top_destino[i] if i < len(top_destino) else ('', '')
            datos_top.append([f"{origen[0]} ({origen[1]})", f"{destino[0]} ({destino[1]})"])

        tabla_top = Table(datos_top, colWidths=[2.5 * inch, 2.5 * inch])
        tabla_top.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgreen),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(tabla_top)
        elements.append(Spacer(1, 0.25 * inch))

    # 4. Distribución Temporal (si existe)
    if 'llamadas_por_hora_dict' in kpis:
        elements.append(Paragraph("4. Distribución por Franja Horaria", estilo_subtitulo))

        datos_hora = [["Hora", "Llamadas"]]
        for hora, llamadas in sorted(kpis['llamadas_por_hora_dict'].items()):
            datos_hora.append([f"{hora}:00", str(llamadas)])

        tabla_hora = Table(datos_hora, colWidths=[1 * inch, 1 * inch])
        tabla_hora.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(tabla_hora)
        elements.append(Spacer(1, 0.25 * inch))

    # 5. Muestra de datos (si se proporciona DataFrame)
    if df is not None and not df.empty:
        elements.append(Paragraph("5. Muestra de Datos (primeras 10 filas)", estilo_subtitulo))

        # Tomar las primeras 10 filas y columnas seleccionadas
        columnas_interes = ['calldate', 'src', 'dst', 'duration', 'disposition']
        columnas_disponibles = [col for col in columnas_interes if col in df.columns]

        if columnas_disponibles:
            df_muestra = df[columnas_disponibles].head(10)

            # Preparar datos para la tabla
            datos_muestra = [columnas_disponibles]  # Encabezados
            for _, fila in df_muestra.iterrows():
                datos_muestra.append([str(fila[col]) for col in columnas_disponibles])

            # Ajustar ancho de columnas
            num_cols = len(columnas_disponibles)
            ancho_col = 5 * inch / num_cols if num_cols > 0 else 1 * inch

            tabla_muestra = Table(datos_muestra, colWidths=[ancho_col] * num_cols)
            tabla_muestra.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            elements.append(tabla_muestra)

    # Construir el PDF
    doc.build(elements)

    return pdf_path