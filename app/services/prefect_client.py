import requests
from typing import Optional, Dict, Any
from app.core.config import PREFECT_API_URL


class PrefectClient:
    def __init__(self, api_url: str):
        self.api_url = api_url

    def trigger_flow(self, deployment_name: str, source_id: str):
        """
        Trigger a Prefect flow run for a specific deployment.
        """
        response = requests.post(
            f"{self.api_url}/deployments/name/telegram-scraper/{deployment_name}/create_flow_run",
            json={"parameters": {"source_id": source_id}},
        )
        response.raise_for_status()
        return response.json()

    def create_deployment(
        self,
        source_id: str,
        source_name: str,
        cron_schedule: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new Prefect deployment for a source.

        Args:
            source_id: UUID of the source
            source_name: Name of the source (used in deployment name)
            cron_schedule: Cron expression for scheduling (e.g., "0 */6 * * *")

        Returns:
            Created deployment details
        """
        deployment_name = f"source-{source_id}"

        # First, get the flow ID for telegram_scraper_flow
        flow_id = self._get_or_create_flow()

        # Prepare deployment payload
        deployment_data = {
            "name": deployment_name,
            "flow_id": flow_id,
            "description": f"Scraper deployment for source: {source_name}",
            "parameters": {"source_id": str(source_id)},
            "tags": ["telegram-scraper", f"source-{source_id}"],
            "work_queue_name": "default",
            # Critical: Tell Prefect where to find the flow code
            "entrypoint": "app/prefect_flows/telegram_flow.py:telegram_scraper_flow",
            "path": "/app",  # Working directory in Docker container
            "storage_document_id": None,  # Use local filesystem
        }

        # Add schedule if provided
        if cron_schedule:
            deployment_data["schedule"] = {"cron": cron_schedule, "timezone": "UTC"}
            deployment_data["is_schedule_active"] = True
        else:
            deployment_data["is_schedule_active"] = False

        # Create deployment
        response = requests.post(
            f"{self.api_url}/deployments/",
            json=deployment_data,
        )
        response.raise_for_status()
        return response.json()

    def update_deployment(
        self,
        source_id: str,
        source_name: str,
        cron_schedule: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing Prefect deployment for a source.
        """
        deployment_name = f"source-{source_id}"

        try:
            # Get existing deployment
            deployment = self._get_deployment(deployment_name)
            deployment_id = deployment["id"]

            # Prepare update payload
            update_data = {
                "description": f"Scraper deployment for source: {source_name}",
                "parameters": {"source_id": str(source_id)},
                # Ensure entrypoint is set
                "entrypoint": "app/prefect_flows/telegram_flow.py:telegram_scraper_flow",
                "path": "/app",
            }

            # Update schedule if provided
            if cron_schedule:
                update_data["schedule"] = {"cron": cron_schedule, "timezone": "UTC"}
                update_data["is_schedule_active"] = True
            else:
                # Clear schedule
                update_data["schedule"] = None
                update_data["is_schedule_active"] = False

            # Update deployment
            response = requests.patch(
                f"{self.api_url}/deployments/{deployment_id}",
                json=update_data,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Deployment doesn't exist, create it
                return self.create_deployment(source_id, source_name, cron_schedule)
            raise

    def delete_deployment(self, source_id: str) -> bool:
        """
        Delete a Prefect deployment for a source.
        """
        deployment_name = f"source-{source_id}"

        try:
            # Get existing deployment
            deployment = self._get_deployment(deployment_name)
            deployment_id = deployment["id"]

            # Delete deployment
            response = requests.delete(
                f"{self.api_url}/deployments/{deployment_id}",
            )
            response.raise_for_status()
            return True

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Deployment doesn't exist, that's fine
                return True
            raise

    def _get_deployment(self, deployment_name: str) -> Dict[str, Any]:
        """
        Get deployment details by name.
        """
        response = requests.get(
            f"{self.api_url}/deployments/name/telegram-scraper/{deployment_name}",
        )
        response.raise_for_status()
        return response.json()

    def _get_or_create_flow(self) -> str:
        """
        Get the flow ID for telegram_scraper_flow, or create it if it doesn't exist.
        """
        flow_name = "telegram_scraper_flow"

        # Search for existing flow
        try:
            response = requests.post(
                f"{self.api_url}/flows/filter",
                json={"flows": {"name": {"any_": [flow_name]}}},
            )

            if response.status_code == 200:
                flows = response.json()
                if flows:
                    print(f"Found existing flow: {flow_name}")
                    return flows[0]["id"]
        except Exception as e:
            print(f"Error searching for flow: {e}")

        # If flow doesn't exist, create it
        print(f"Creating new flow: {flow_name}")
        try:
            flow_data = {
                "name": flow_name,
                "tags": ["telegram-scraper"],
            }

            response = requests.post(
                f"{self.api_url}/flows/",
                json=flow_data,
            )
            response.raise_for_status()
            flow = response.json()
            print(f"✓ Created flow with ID: {flow['id']}")
            return flow["id"]

        except Exception as e:
            print(f"✗ Failed to create flow: {e}")
            raise Exception(
                f"Could not create flow '{flow_name}' in Prefect. "
                f"Make sure Prefect Orion is running and accessible at {self.api_url}"
            )


prefect_client = PrefectClient(api_url=PREFECT_API_URL)
