"""
Script to verify Prefect connection and flow registration.
This is now optional since flows are created automatically on-demand.
"""

import requests
from app.core.config import PREFECT_API_URL


def verify_prefect_connection():
    """
    Verify that we can connect to Prefect Orion.
    """
    print("Verifying Prefect connection...")

    try:
        response = requests.get(f"{PREFECT_API_URL}/health")

        if response.status_code == 200:
            print(f"✓ Successfully connected to Prefect at {PREFECT_API_URL}")
            return True
        else:
            print(f"✗ Prefect returned status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"✗ Failed to connect to Prefect: {e}")
        return False


if __name__ == "__main__":
    verify_prefect_connection()
