import streamlit as st
import sqlite3
import bcrypt
import os
from datetime import datetime
from modules.cookie_instance import controller  # <-- Importa la instancia central

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../data/usuarios.db")
VERSION_FILE = os.path.join(BASE_DIR, "version.txt")

cookie_name = "my_app"

if "login_ok" not in st.session_state:
    st.session_state["login_ok"] = False

def get_latest_version():
    try:
        with open(VERSION_FILE, "r") as f:
            versions = f.readlines()
            if versions:
                return versions[-1].strip()
    except FileNotFoundError:
        return "Desconocida"
    return "Desconocida"

def verify_user(nombre, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password, role FROM usuarios WHERE username = ?", (nombre,))
    result = cursor.fetchone()
    conn.close()

    if result:
        hashed_pw, rol = result
        if bcrypt.checkpw(password.encode(), hashed_pw.encode()):
            return rol
    return None

def log_trazabilidad(usuario, accion, detalles):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))
    conn.commit()
    conn.close()

def login():
    # Verificar si el usuario ya está autenticado usando cookies
    if "login_ok" not in st.session_state:
        st.session_state["login_ok"] = False

    # Recuperar las cookies usando los nombres adecuados
    cookie_username = controller.get(f'{cookie_name}_username')
    cookie_role = controller.get(f'{cookie_name}_role')

    # Si existen ambas cookies, iniciamos sesión automáticamente
    if (cookie_username and cookie_role and
        cookie_username.strip() != "" and cookie_role.strip() != ""):
        st.session_state["login_ok"] = True
        st.session_state["username"] = cookie_username
        st.session_state["role"] = cookie_role
        st.success(f"¡Bienvenido de nuevo, {st.session_state['username']}!")
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

        st.title("🔐 Inicio de sesión")

        version_actual = get_latest_version()

        if "last_seen_version" not in st.session_state or st.session_state["last_seen_version"] != version_actual:
            st.info(f"🚀 Nueva versión disponible: **{version_actual}**")
            #st.session_state["last_seen_version"] = version_actual

        nombre = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Iniciar sesión"):
            rol = verify_user(nombre, password)
            if rol:
                st.session_state["login_ok"] = True
                st.session_state["username"] = nombre
                st.session_state["role"] = rol
                st.success(f"Bienvenido, {nombre} ({rol})")

                # Guardar las credenciales en cookies con path explícito
                controller.set(f'{cookie_name}_username', nombre, max_age=24 * 60 * 60, path='/')
                controller.set(f'{cookie_name}_role', rol, max_age=24 * 60 * 60, path='/')

                detalles = f"Usuario '{nombre}' inició sesión en el sistema."
                log_trazabilidad(nombre, "Inicio sesión", detalles)
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
