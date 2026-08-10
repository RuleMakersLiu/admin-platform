"""各阶段 prompt 模板包。"""

from typing import Dict

from app.prompts.stages.requirement import REQUIREMENT_PROMPT
from app.prompts.stages.page_design import PAGE_DESIGN_PROMPT
from app.prompts.stages.prototype import PROTOTYPE_PROMPT
from app.prompts.stages.prototype_spec import PROTOTYPE_SPEC_PROMPT
from app.prompts.stages.delivery import DELIVERY_PROMPT
from app.prompts.stages.ui_preview import UI_PREVIEW_PROMPT
from app.prompts.stages.backend_dev import BACKEND_DEV_PROMPT
from app.prompts.stages.frontend_dev import FRONTEND_DEV_PROMPT
from app.prompts.stages.code_review import CODE_REVIEW_PROMPT
from app.prompts.stages.testing import TESTING_PROMPT
from app.prompts.stages.commit import COMMIT_PROMPT
from app.prompts.stages.deploy import DEPLOY_PROMPT
from app.prompts.stages.report import REPORT_PROMPT

DEFAULT_STAGE_PROMPTS: Dict[str, str] = {
    "requirement": REQUIREMENT_PROMPT,
    "page_design": PAGE_DESIGN_PROMPT,
    "prototype": PROTOTYPE_PROMPT,
    "prototype_spec": PROTOTYPE_SPEC_PROMPT,
    "delivery": DELIVERY_PROMPT,
    "ui_preview": UI_PREVIEW_PROMPT,
    "backend_dev": BACKEND_DEV_PROMPT,
    "frontend_dev": FRONTEND_DEV_PROMPT,
    "code_review": CODE_REVIEW_PROMPT,
    "testing": TESTING_PROMPT,
    "commit": COMMIT_PROMPT,
    "deploy": DEPLOY_PROMPT,
    "report": REPORT_PROMPT,
}
