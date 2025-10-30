from fastapi import APIRouter
from app.services.prefect_client import prefect_client

router = APIRouter()


@router.post("/trigger/{flow_name}")
def trigger_flow(flow_name: str, source_id: str):
    """
    Trigger a Prefect flow by name with the given source_id parameter.
    """
    result = prefect_client.trigger_flow(flow_name, source_id)
    return {"message": f"Flow {flow_name} triggered", "result": result}
