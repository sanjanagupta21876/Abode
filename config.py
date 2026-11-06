import os


def get_environment_value(name, default=None):
    value = os.environ.get(name)
    if value is not None:
        return value
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as key:
                value, _ = winreg.QueryValueEx(key, name)
                return value
        except (FileNotFoundError, OSError):
            pass
    return default


class Config:
    SECRET_KEY = get_environment_value('SECRET_KEY', 'shmm-super-secret-key-2024')
    # SQLite database file (no MySQL needed!)
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'smart_hostel.db')
    DEBUG = True
    SMTP_HOST = get_environment_value('SMTP_HOST')
    SMTP_PORT = int(get_environment_value('SMTP_PORT', '587'))
    SMTP_USERNAME = get_environment_value('SMTP_USERNAME')
    SMTP_PASSWORD = get_environment_value('SMTP_PASSWORD')
    SMTP_FROM = get_environment_value('SMTP_FROM')
    SMTP_USE_TLS = get_environment_value('SMTP_USE_TLS', 'true').lower() == 'true'

    # Outpass / Leave Pass geofence
    HOSTEL_LAT = float(get_environment_value('HOSTEL_LAT', '28.7974521'))
    HOSTEL_LNG = float(get_environment_value('HOSTEL_LNG', '77.5389165'))
    GEOFENCE_RADIUS_METRES = float(get_environment_value('GEOFENCE_RADIUS_METRES', '100'))
    OUTPASS_GRACE_MINUTES = int(get_environment_value('OUTPASS_GRACE_MINUTES', '30'))
