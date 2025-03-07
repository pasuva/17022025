import streamlit as st
from modules import login, admin, supervisor, comercial, comercial_jefe, comercial_rafa
from streamlit_cookies_controller import CookieController

cookie_name = "my_app"
controller = CookieController(key="cookies")

# Inicializar el estado de sesión si no existe
if "login_ok" not in st.session_state:
    st.session_state["login_ok"] = False

# Si no está logueado, mostramos el login
if not st.session_state["login_ok"]:
    login.login()
else:
    rol = st.session_state.get("role", "")

    if rol == "admin":
        admin.admin_dashboard()
    elif rol == "supervisor":
        supervisor.supervisor_dashboard()
    elif rol == "comercial":
        comercial.comercial_dashboard()
    elif rol == "comercial_jefe":
        comercial_jefe.mapa_dashboard()
    elif rol == "comercial_rafa":
        comercial_rafa.comercial_dashboard()
    else:
        st.error("Rol no reconocido")
