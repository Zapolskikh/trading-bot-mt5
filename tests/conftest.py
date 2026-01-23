import os
import pytest
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def mt5_credentials():
    """Extract MT5 credentials from environment variables.

    Required environment variables:
    - MT5_LOGIN: Account login (numeric)
    - MT5_PASSWORD: Account password
    - MT5_SERVER: Server name (e.g., "FTMO-Demo")
    """
    login = os.getenv("MT5_LOGIN", "")
    if login:
        login = int(login)

    return {
        "login": login,
        "password": os.getenv("MT5_PASSWORD", ""),
        "server": os.getenv("MT5_SERVER", ""),
    }


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test requiring MT5 terminal")
