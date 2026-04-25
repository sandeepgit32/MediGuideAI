"""Patient Input Schema.

Defines the structure of patient data submitted for medical consultation.
This schema captures essential patient demographics, reported symptoms, symptom duration,
and medical history required for accurate triage assessment.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class PatientInput(BaseModel):
    """Patient consultation input data.
    
    Contains demographic information, symptom details, and medical history
    required to perform medical triage assessment and generate personalized recommendations.
    """
    age: int = Field(..., ge=0, le=120, description="Patient age in years (0-120)")
    gender: Optional[str] = Field(None, description="Patient gender (optional)")
    symptoms: List[str] = Field(..., min_length=1, description="List of symptom phrases reported by the patient (e.g., ['fever', 'cough'])")
    duration: str = Field(..., description="How long symptoms have been present (e.g., '3 days', '2 weeks')")
    existing_conditions: Optional[List[str]] = Field(None, description="Pre-existing medical conditions relevant to triage (e.g., ['diabetes', 'hypertension'])")
    language: Optional[str] = Field(None, description="ISO language code of patient's preferred language (e.g., 'en', 'bn', 'hi', 'es')")
