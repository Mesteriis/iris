from fastapi import APIRouter, status

from src.apps.hypothesis_engine.api.contracts import HypothesisEvaluationJobAcceptedRead
from src.apps.hypothesis_engine.api.deps import HypothesisJobDispatcherDep
from src.apps.hypothesis_engine.api.presenters import hypothesis_evaluation_job_accepted_read

router = APIRouter(tags=["hypothesis:jobs"])


@router.post(
    "/jobs/evaluate",
    response_model=HypothesisEvaluationJobAcceptedRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue hypothesis evaluation job",
)
async def run_hypothesis_evaluation_job(
    dispatcher: HypothesisJobDispatcherDep,
) -> HypothesisEvaluationJobAcceptedRead:
    dispatch_result = await dispatcher.dispatch_evaluation()
    return hypothesis_evaluation_job_accepted_read(dispatch_result=dispatch_result)
