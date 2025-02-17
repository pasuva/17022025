import streamlit as st
import sqlite3
import bcrypt
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "../data/usuarios.db")


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


def login():
    """ Pantalla de inicio de sesión """
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
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")


if __name__ == "__main__":
    login()