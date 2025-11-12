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
            # Note: Concurrency is managed via work pool or global concurrency limits
            # Per-deployment concurrency can be set via work pool concurrency or
            # by using deployment-level concurrency tags in the flow itself
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

    def create_concurrency_limit(
        self,
        source_id: str,
        limit: int = 1,
    ) -> Dict[str, Any]:
        """
        Create a concurrency limit for a source to prevent overlapping runs.

        Uses Prefect's concurrency limits with a per-source tag to ensure that
        each source can have maximum 1 concurrent run, while different sources
        can run in parallel.

        Args:
            source_id: UUID of the source
            limit: Maximum concurrent runs (default: 1)

        Returns:
            Created concurrency limit details
        """
        tag = f"telegram-scraper-source-{source_id}"

        try:
            # Check if limit already exists
            response = requests.post(
                f"{self.api_url}/concurrency_limits/filter",
                json={"concurrency_limits": {"tag": {"any_": [tag]}}},
            )

            if response.status_code == 200:
                limits = response.json()
                if limits:
                    existing_limit = limits[0]
                    limit_id = existing_limit.get("id")

                    # Check if the existing limit is inactive
                    if not existing_limit.get("active", False):
                        print(
                            f"Concurrency limit exists but is inactive, activating it..."
                        )
                        print(f"Existing limit: {existing_limit}")

                        # Update the existing limit to activate it
                        try:
                            update_data = {
                                "tag": tag,
                                "concurrency_limit": limit,
                                "active": True,
                                "active_slots": [],
                            }

                            print(f"Updating with data: {update_data}")

                            update_response = requests.patch(
                                f"{self.api_url}/concurrency_limits/{limit_id}",
                                json=update_data,
                            )

                            print(
                                f"Update response status: {update_response.status_code}"
                            )
                            print(f"Update response body: {update_response.text}")

                            update_response.raise_for_status()
                            updated_limit = update_response.json()

                            print(
                                f"✓ Activated concurrency limit for source {source_id} (tag: {tag}, limit: {limit}, active: {updated_limit.get('active')})"
                            )
                            return updated_limit
                        except Exception as update_error:
                            print(
                                f"✗ Failed to activate concurrency limit: {update_error}"
                            )
                            import traceback

                            print(f"Traceback: {traceback.format_exc()}")
                            # Fall through to return existing limit

                    print(
                        f"Concurrency limit already exists and is active for source {source_id}"
                    )
                    return existing_limit

        except Exception as e:
            print(f"Error checking existing concurrency limit: {e}")

        # Create new concurrency limit
        try:
            # Step 1: Create the limit (might be inactive by default)
            limit_data = {
                "tag": tag,
                "concurrency_limit": limit,
            }

            print(f"Creating concurrency limit with data: {limit_data}")

            response = requests.post(
                f"{self.api_url}/concurrency_limits/",
                json=limit_data,
            )

            print(f"Create response status: {response.status_code}")
            print(f"Create response body: {response.text}")

            response.raise_for_status()
            result = response.json()
            limit_id = result.get("id")

            # Step 2: Explicitly activate the limit
            if limit_id:
                print(f"Activating concurrency limit {limit_id}...")

                activate_response = requests.patch(
                    f"{self.api_url}/concurrency_limits/{limit_id}",
                    json={"active": True},
                )

                print(f"Activate response status: {activate_response.status_code}")
                print(f"Activate response body: {activate_response.text}")

                if activate_response.status_code in [200, 204]:
                    # Fetch the updated limit to confirm
                    get_response = requests.get(
                        f"{self.api_url}/concurrency_limits/{limit_id}"
                    )
                    if get_response.status_code == 200:
                        result = get_response.json()
                        is_active = result.get("active", False)

                        if is_active:
                            print(
                                f"✓ Created and activated concurrency limit for source {source_id} (tag: {tag}, limit: {limit})"
                            )
                        else:
                            print(
                                f"⚠️ Warning: Limit created but activation failed. Active: {is_active}"
                            )
                            print(f"   Full response: {result}")
                    else:
                        print(
                            f"⚠️ Could not verify limit status (GET failed with {get_response.status_code})"
                        )
                else:
                    print(
                        f"⚠️ Warning: Failed to activate limit (PATCH returned {activate_response.status_code})"
                    )
            else:
                print(f"⚠️ Warning: No limit ID returned from creation")

            return result

        except Exception as e:
            print(f"✗ Failed to create concurrency limit: {e}")
            import traceback

            print(f"Traceback: {traceback.format_exc()}")
            # Don't raise - concurrency limit is nice-to-have, not critical
            return {}

    def delete_concurrency_limit(self, source_id: str) -> bool:
        """
        Delete the concurrency limit for a source.

        Removes the per-source concurrency limit tag from Prefect.

        Args:
            source_id: UUID of the source

        Returns:
            True if deleted or doesn't exist
        """
        tag = f"telegram-scraper-source-{source_id}"

        try:
            # Find the limit by tag
            response = requests.post(
                f"{self.api_url}/concurrency_limits/filter",
                json={"concurrency_limits": {"tag": {"any_": [tag]}}},
            )

            if response.status_code == 200:
                limits = response.json()
                if limits:
                    limit_id = limits[0]["id"]

                    # Delete the limit
                    delete_response = requests.delete(
                        f"{self.api_url}/concurrency_limits/{limit_id}",
                    )
                    delete_response.raise_for_status()
                    print(f"✓ Deleted concurrency limit for source {source_id}")
                    return True

            # Limit doesn't exist, that's fine
            return True

        except Exception as e:
            print(f"Warning: Failed to delete concurrency limit: {e}")
            return True

    def activate_all_concurrency_limits(self) -> int:
        """
        Activate all inactive concurrency limits.

        This is useful on startup to ensure all limits are active,
        especially after a system restart where limits might have been
        deactivated manually or by some other process.

        Returns:
            Number of limits activated
        """
        activated_count = 0

        try:
            # Get all concurrency limits with our tag pattern
            response = requests.post(
                f"{self.api_url}/concurrency_limits/filter",
                json={},  # Get all limits
            )

            if response.status_code != 200:
                print(
                    f"Warning: Failed to fetch concurrency limits: {response.status_code}"
                )
                return 0

            all_limits = response.json()

            # Filter for our telegram-scraper limits
            scraper_limits = [
                limit
                for limit in all_limits
                if limit.get("tag", "").startswith("telegram-scraper-source-")
            ]

            print(f"Found {len(scraper_limits)} telegram scraper concurrency limits")

            # Activate any that are inactive
            for limit in scraper_limits:
                if not limit.get("active", False):
                    limit_id = limit.get("id")
                    tag = limit.get("tag")

                    try:
                        update_data = {
                            "tag": tag,
                            "concurrency_limit": limit.get("concurrency_limit", 1),
                            "active": True,
                        }

                        update_response = requests.patch(
                            f"{self.api_url}/concurrency_limits/{limit_id}",
                            json=update_data,
                        )
                        update_response.raise_for_status()

                        print(f"✓ Activated concurrency limit: {tag}")
                        activated_count += 1

                    except Exception as update_error:
                        print(f"✗ Failed to activate limit {tag}: {update_error}")

            if activated_count > 0:
                print(f"✓ Activated {activated_count} concurrency limit(s)")
            else:
                print("✓ All concurrency limits are already active")

            return activated_count

        except Exception as e:
            print(f"Warning: Error activating concurrency limits: {e}")
            return 0


prefect_client = PrefectClient(api_url=PREFECT_API_URL)
