import streamlit as st
import sqlite3
import bcrypt
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../data/usuarios.db")  # Base de datos de usuarios


def verify_user(nombre, password):
    """ Verifica si un usuario existe y su contraseña es correcta """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password, role FROM usuarios WHERE username = ?", (nombre,))
    result = cursor.fetchone()
    conn.close()

    if result:
        hashed_pw, rol = result
        if bcrypt.checkpw(password.encode(), hashed_pw.encode()):
            return rol  # Retornamos el rol si la autenticación es correcta
    return None


def log_trazabilidad(usuario, accion, detalles):
    """ Inserta un registro en la tabla de trazabilidad """
    conn = sqlite3.connect(DB_PATH)  # Usamos la misma base de datos de usuarios
    cursor = conn.cursor()

    # Obtener la fecha y hora actual
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO trazabilidad (usuario_id, accion, detalles, fecha)
        VALUES (?, ?, ?, ?)
    """, (usuario, accion, detalles, fecha))

    conn.commit()
    conn.close()


def login():
    """ Pantalla de inicio de sesión """
    # Mostrar el ícono de usuario centrado y más grande en la barra lateral
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

    nombre = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Iniciar sesión"):
        rol = verify_user(nombre, password)
        if rol:
            st.session_state["logged_in"] = True
            st.session_state["username"] = nombre
            st.session_state["role"] = rol
            st.success(f"Bienvenido, {nombre} ({rol})")

            # Registrar trazabilidad del inicio de sesión
            detalles = f"Usuario '{nombre}' inició sesión en el sistema."
            log_trazabilidad(nombre, "Inicio sesión", detalles)

            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")


if __name__ == "__main__":
    login()