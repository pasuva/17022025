import uuid, os, base64, bcrypt, sqlitecloud
import streamlit as st
from datetime import datetime
from streamlit_cookies_controller import CookieController  # Se importa de forma local

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# URL de conexión a SQLite Cloud
DB_URL = "sqlitecloud://ceafu04onz.g6.sqlite.cloud:8860/usuarios.db?apikey=Qo9m18B9ONpfEGYngUKm99QB5bgzUTGtK7iAcThmwvY"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, "version.txt")

cookie_name = "my_app"

if "login_ok" not in st.session_state:
    st.session_state["login_ok"] = False


def get_latest_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            versions = f.readlines()
            if versions:
                return versions[-1].strip()
    except FileNotFoundError:
        return "Desconocida"
    return "Desconocida"


def verify_user(nombre, password):
    # Conexión a SQLite Cloud
    conn = sqlitecloud.connect(DB_URL)
    cursor = conn.execute("SELECT password, role FROM usuarios WHERE username = ?", (nombre,))
    result = cursor.fetchone()
    conn.close()

    if result:
        hashed_pw, rol = result
        if bcrypt.checkpw(password.encode(), hashed_pw.encode()):
            return rol
    return None

def log_trazabilidad(usuario, accion, detalles):
    # Conexión a SQLite Cloud
    conn = sqlitecloud.connect(DB_URL)
    cursor = conn.execute(""" 
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_latest_version():
    try:
        conn = sqlitecloud.connect(DB_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM versiones ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            #print("[DEBUG] Última versión encontrada:", row[0])
            return row[0]
        else:
            #print("[DEBUG] No se encontraron versiones.")
            return "desconocido"
    except Exception as e:
        print("[ERROR] al obtener la última versión:", e)
        return "desconocido"

def login():
    # Se instancia localmente el controlador de cookies para que cada navegador administre sus propias cookies.
    controller = CookieController(key="cookies")

    # Verificar si el usuario ya está autenticado usando cookies
    if "login_ok" not in st.session_state:
        st.session_state["login_ok"] = False

    # Recuperar las cookies usando los nombres adecuados
    cookie_session_id = controller.get(f'{cookie_name}_session_id')
    cookie_username = controller.get(f'{cookie_name}_username')
    cookie_role = controller.get(f'{cookie_name}_role')

    # Si existen las cookies y son válidas, iniciamos sesión automáticamente
    if cookie_session_id and cookie_username and cookie_role:
        st.session_state["login_ok"] = True
        st.session_state["username"] = cookie_username
        st.session_state["role"] = cookie_role
        st.session_state["session_id"] = cookie_session_id  # Guardamos el session_id
        st.success(f"¡Bienvenido de nuevo, {st.session_state['username']}!")
        # Forzamos la recarga para que se ejecute el dashboard en app.py
        st.rerun()
        return

    if not st.session_state["login_ok"]:
        st.markdown(""" 
            <style> 
                .user-circle { 
                    width: 100px; 
                    height: 100px; 
                    border-radius: 50%; 
                    background-color: #6c757d; 
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
            """, unsafe_allow_html=True)

        # Genera un session_id único para esta sesión
        session_id = str(uuid.uuid4())
        st.session_state["session_id"] = session_id

        st.markdown(
            """
            <h1 style="text-align: center; font-size: 50px; color: #2C5A2E;">
                <img src="data:image/png;base64,{}" style="vertical-align: middle; width: 40px; height: 40px; margin-right: 10px;" />
                VERDE SUITE
            </h1>
            """.format(base64.b64encode(open('img/Adobe_Express_file.png', 'rb').read()).decode()),
            unsafe_allow_html=True
        )

        # Crear columnas vacías a izquierda y derecha para centrar el contenido
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            st.success("🔐 Por favor, inicia sesión con tu usuario y tu contraseña.")

            nombre = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")

            if st.button("Iniciar sesión"):
                rol = verify_user(nombre, password)
                if rol:
                    st.session_state["login_ok"] = True
                    st.session_state["username"] = nombre
                    st.session_state["role"] = rol
                    st.session_state["session_id"] = session_id  # Guardamos el session_id

                    st.success(f"Bienvenido, {nombre} ({rol})")

                    # Guardar cookies
                    if st.session_state.get("login_ok"):
                        controller.set(f'{cookie_name}_session_id', session_id, max_age=24 * 60 * 60, path='/',
                                       same_site='Lax', secure=True)
                        controller.set(f'{cookie_name}_username', nombre, max_age=24 * 60 * 60, path='/',
                                       same_site='Lax', secure=True)
                        controller.set(f'{cookie_name}_role', rol, max_age=24 * 60 * 60, path='/', same_site='Lax',
                                       secure=True)

                    detalles = f"Usuario '{nombre}' inició sesión en el sistema."
                    log_trazabilidad(nombre, "Inicio sesión", detalles)
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

            # 🔽 Mostrar versión centrada abajo
            version_actual = get_latest_version()
            st.markdown(
                f"<div style='text-align: center; margin-top: 50px;'>🔍 <strong>Versión actual:</strong> {version_actual}</div>",
                unsafe_allow_html=True
            )

