"""Emergency Escalation Detection Output Schema.

Defines the structure of emergency detection results. The escalation agent uses
this schema to classify whether a patient's symptoms represent a life-threatening
emergency requiring immediate intervention.
"""

from typing import List

from pydantic import BaseModel, Field


class EscalationOutput(BaseModel):
    """Emergency escalation assessment result.
    
    Indicates whether the patient's symptoms constitute a medical emergency
    requiring immediate emergency services, and documents the emergency indicators.
    """
    is_emergency: bool = Field(..., description="True if patient symptoms indicate a life-threatening emergency; False otherwise")
    flags: List[str] = Field(default=[], description="List of emergency indicators detected (e.g., 'severe_bleeding', 'difficulty_breathing', 'loss_of_consciousness', 'chest_pain')")}
