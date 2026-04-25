"""Safety Assessment Output Schema.

Defines the structure of safety evaluation results returned by the safety agent.
These results ensure that triage recommendations are clinically appropriate and
do not suggest harmful or dangerous actions.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class SafetyOutput(BaseModel):
    """Safety assessment result for a triage recommendation.
    
    Indicates whether the recommended action is safe, identifies any risk factors,
    and provides conservative override messages if needed.
    """
    is_safe: bool = Field(..., description="True if the recommendation is clinically safe; False if safety concerns detected")
    risk_flags: List[str] = Field(default=[], description="List of identified safety issues or risk factors (e.g., 'contradictory_symptoms', 'dangerous_delay')")
    override_message: Optional[str] = Field(None, description="Conservative alternative recommendation if safety issues detected; None if recommendation is safe")
