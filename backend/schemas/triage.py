"""Triage Assessment Output Schema.

Defines the structure of medical triage assessment results. A triage assessment
classifies a patient's condition severity, identifies likely medical conditions,
recommends appropriate next steps, and specifies urgency level for seeking care.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TriageOutput(BaseModel):
    """Result of medical triage assessment for a patient consultation.
    
    Contains severity classification, possible diagnoses, recommended clinical action,
    and urgency timeframe for seeking medical attention.
    """
    severity: Literal["low", "medium", "high"] = Field(..., description="Severity level of the patient's condition: 'low' for self-manageable, 'medium' for professional care needed within 24h, 'high' for urgent/emergency care")
    possible_conditions: List[str] = Field(..., min_length=1, description="List of possible medical conditions matching the patient's symptoms (most likely first)")
    recommended_action: str = Field(..., description="Clinical recommendation for the patient (e.g., 'Seek immediate medical help', 'Monitor at home', 'See doctor within 24 hours')")
    urgency: str = Field(..., description="Timeframe for seeking medical attention (e.g., 'immediate', 'within 24 hours', 'self-monitor')")
    notes: Optional[str] = Field(None, description="Additional clinical notes or context about the assessment")
