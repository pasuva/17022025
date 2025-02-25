import streamlit as st
from modules import login, admin, supervisor, comercial, comercial_jefe

# Iniciar sesión si no está iniciada
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
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
    else:
        st.error("Rol no reconocido")