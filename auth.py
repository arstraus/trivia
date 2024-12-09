import hashlib
import hmac
import streamlit as st

def check_password(password: str, stored_hash: str, salt: str) -> bool:
    """Verify a stored password against a given password"""
    return hmac.compare_digest(
        hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000),
        bytes.fromhex(stored_hash)
    )

def init_auth_state():
    """Initialize authentication state"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = None

def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user against stored credentials"""
    try:
        user_credentials = st.secrets.auth.credentials[username]
        stored_hash = user_credentials['password_hash']
        salt = user_credentials['salt']
        return check_password(password, stored_hash, salt)
    except (KeyError, AttributeError):
        return False

def login_page():
    """Display the login page"""
    st.title("🔐 Login")
    
    # Center the login form
    col1, col2, col3 = st.columns([1,2,1])
    
    with col2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Login"):
            if authenticate_user(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Invalid username or password")

def logout():
    """Log out the user"""
    st.session_state.authenticated = False
    st.session_state.username = None
    st.rerun()

def show_logout_button():
    """Show the logout button in the sidebar"""
    with st.sidebar:
        st.write(f"👤 Logged in as: {st.session_state.username}")
        if st.button("Logout"):
            logout()