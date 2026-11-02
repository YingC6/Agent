"""行程可执行性校验(对外的稳定入口)。

规则实现已下沉到 domain.validators.execution,这里保持原有名称与签名。
"""

from __future__ import annotations

from ..domain.validators.execution import PlanValidationResult, validate_plan_execution

__all__ = ["PlanValidationResult", "validate_plan_execution"]
