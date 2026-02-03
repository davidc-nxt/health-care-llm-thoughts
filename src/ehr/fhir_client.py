"""FHIR R4/R5 Client for EHR Integration"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from fhir.resources.bundle import Bundle
from fhir.resources.condition import Condition
from fhir.resources.medication import Medication
from fhir.resources.medicationrequest import MedicationRequest
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient

from src.config import get_settings
from src.security.audit_logger import log_action


@dataclass
class PatientSummary:
    """Summarized patient information from FHIR resources."""

    patient_id: str
    name: str
    birth_date: Optional[date]
    gender: Optional[str]
    conditions: list[dict]
    medications: list[dict]
    observations: list[dict]
    raw_resources: dict  # Store raw FHIR resources for reference


class FHIRClient:
    """
    FHIR R4/R5 client for Epic/Cerner integration.

    Supports:
    - Patient resource retrieval
    - Condition (diagnoses) lookup
    - MedicationRequest (prescriptions)
    - Observation (lab results, vitals)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        """
        Initialize FHIR client.

        Args:
            base_url: FHIR server base URL
            access_token: OAuth2 access token
        """
        settings = get_settings()
        self._base_url = base_url or settings.epic_fhir_base_url
        self._access_token = access_token
        self._http_client = None

    def _get_client(self):
        """Get or create HTTP client."""
        if self._http_client is None:
            import httpx

            headers = {"Accept": "application/fhir+json"}
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"

            self._http_client = httpx.Client(
                base_url=self._base_url.rstrip("/"),
                headers=headers,
                timeout=30.0,
            )
        return self._http_client

    def set_access_token(self, token: str):
        """Update access token (after OAuth flow)."""
        self._access_token = token
        self._http_client = None  # Reset client to use new token

    def get_patient(
        self, patient_id: str, user_id: Optional[str] = None
    ) -> Optional[Patient]:
        """
        Retrieve patient resource by ID.

        Args:
            patient_id: FHIR Patient ID
            user_id: User ID for audit logging

        Returns:
            Patient resource or None
        """
        log_action(
            action="FHIR_GET_PATIENT",
            user_id=user_id,
            resource_type="Patient",
            resource_id=patient_id,
            phi_accessed=True,
        )

        try:
            client = self._get_client()
            response = client.get(f"/Patient/{patient_id}")
            response.raise_for_status()
            return Patient.model_validate(response.json())
        except Exception as e:
            print(f"Error fetching patient: {e}")
            return None

    def get_conditions(
        self, patient_id: str, user_id: Optional[str] = None
    ) -> list[Condition]:
        """
        Retrieve active conditions for a patient.

        Args:
            patient_id: FHIR Patient ID
            user_id: User ID for audit logging

        Returns:
            List of Condition resources
        """
        log_action(
            action="FHIR_GET_CONDITIONS",
            user_id=user_id,
            resource_type="Condition",
            resource_id=patient_id,
            phi_accessed=True,
        )

        try:
            client = self._get_client()
            response = client.get(
                "/Condition",
                params={
                    "patient": patient_id,
                    "clinical-status": "active",
                },
            )
            response.raise_for_status()
            bundle = Bundle.model_validate(response.json())
            return [
                Condition.model_validate(entry.resource.model_dump())
                for entry in (bundle.entry or [])
                if entry.resource
            ]
        except Exception as e:
            print(f"Error fetching conditions: {e}")
            return []

    def get_medications(
        self, patient_id: str, user_id: Optional[str] = None
    ) -> list[MedicationRequest]:
        """
        Retrieve active medication requests for a patient.

        Args:
            patient_id: FHIR Patient ID
            user_id: User ID for audit logging

        Returns:
            List of MedicationRequest resources
        """
        log_action(
            action="FHIR_GET_MEDICATIONS",
            user_id=user_id,
            resource_type="MedicationRequest",
            resource_id=patient_id,
            phi_accessed=True,
        )

        try:
            client = self._get_client()
            response = client.get(
                "/MedicationRequest",
                params={
                    "patient": patient_id,
                    "status": "active",
                },
            )
            response.raise_for_status()
            bundle = Bundle.model_validate(response.json())
            return [
                MedicationRequest.model_validate(entry.resource.model_dump())
                for entry in (bundle.entry or [])
                if entry.resource
            ]
        except Exception as e:
            print(f"Error fetching medications: {e}")
            return []

    def get_observations(
        self,
        patient_id: str,
        category: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[Observation]:
        """
        Retrieve observations (labs, vitals) for a patient.

        Args:
            patient_id: FHIR Patient ID
            category: Filter by category (vital-signs, laboratory, etc.)
            user_id: User ID for audit logging

        Returns:
            List of Observation resources
        """
        log_action(
            action="FHIR_GET_OBSERVATIONS",
            user_id=user_id,
            resource_type="Observation",
            resource_id=patient_id,
            request_details={"category": category},
            phi_accessed=True,
        )

        try:
            client = self._get_client()
            params = {"patient": patient_id, "_count": "50", "_sort": "-date"}
            if category:
                params["category"] = category

            response = client.get("/Observation", params=params)
            response.raise_for_status()
            bundle = Bundle.model_validate(response.json())
            return [
                Observation.model_validate(entry.resource.model_dump())
                for entry in (bundle.entry or [])
                if entry.resource
            ]
        except Exception as e:
            print(f"Error fetching observations: {e}")
            return []

    def get_patient_summary(
        self, patient_id: str, user_id: Optional[str] = None
    ) -> Optional[PatientSummary]:
        """
        Get comprehensive patient summary with conditions, meds, and labs.

        Args:
            patient_id: FHIR Patient ID
            user_id: User ID for audit logging

        Returns:
            PatientSummary or None
        """
        patient = self.get_patient(patient_id, user_id)
        if not patient:
            return None

        conditions = self.get_conditions(patient_id, user_id)
        medications = self.get_medications(patient_id, user_id)
        observations = self.get_observations(patient_id, user_id=user_id)

        # Extract patient name
        name = "Unknown"
        if patient.name:
            name_obj = patient.name[0]
            given = " ".join(name_obj.given or [])
            family = name_obj.family or ""
            name = f"{given} {family}".strip()

        # Parse conditions
        condition_list = []
        for cond in conditions:
            if cond.code and cond.code.coding:
                condition_list.append(
                    {
                        "code": cond.code.coding[0].code,
                        "display": cond.code.coding[0].display,
                        "onset": str(cond.onsetDateTime) if cond.onsetDateTime else None,
                    }
                )

        # Parse medications
        med_list = []
        for med in medications:
            if med.medicationCodeableConcept and med.medicationCodeableConcept.coding:
                med_list.append(
                    {
                        "code": med.medicationCodeableConcept.coding[0].code,
                        "display": med.medicationCodeableConcept.coding[0].display,
                        "status": med.status,
                    }
                )

        # Parse observations
        obs_list = []
        for obs in observations[:20]:  # Limit to recent 20
            if obs.code and obs.code.coding:
                value = None
                if obs.valueQuantity:
                    value = f"{obs.valueQuantity.value} {obs.valueQuantity.unit or ''}"
                elif obs.valueString:
                    value = obs.valueString

                obs_list.append(
                    {
                        "code": obs.code.coding[0].code,
                        "display": obs.code.coding[0].display,
                        "value": value,
                        "date": str(obs.effectiveDateTime) if obs.effectiveDateTime else None,
                    }
                )

        return PatientSummary(
            patient_id=patient_id,
            name=name,
            birth_date=patient.birthDate,
            gender=patient.gender,
            conditions=condition_list,
            medications=med_list,
            observations=obs_list,
            raw_resources={
                "patient": patient.model_dump(),
                "conditions": [c.model_dump() for c in conditions],
                "medications": [m.model_dump() for m in medications],
                "observations": [o.model_dump() for o in observations],
            },
        )

    def create_bundle(self, resources: list[Any]) -> Bundle:
        """
        Create a FHIR Bundle from resources.

        Args:
            resources: List of FHIR resources

        Returns:
            Bundle resource
        """
        from fhir.resources.bundle import BundleEntry

        entries = []
        for resource in resources:
            entry = BundleEntry(resource=resource)
            entries.append(entry)

        return Bundle(type="collection", entry=entries)
