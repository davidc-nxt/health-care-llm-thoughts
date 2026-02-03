"""HL7 v2 Message Handler"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hl7apy.core import Message
from hl7apy.parser import parse_message

from src.security.audit_logger import log_action


@dataclass
class HL7PatientInfo:
    """Patient information extracted from HL7 message."""

    patient_id: str
    first_name: Optional[str]
    last_name: Optional[str]
    date_of_birth: Optional[datetime]
    gender: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    mrn: Optional[str]  # Medical Record Number


@dataclass
class HL7AdmitInfo:
    """Admission information from ADT message."""

    event_type: str  # A01, A02, A03, etc.
    patient: HL7PatientInfo
    admit_datetime: Optional[datetime]
    discharge_datetime: Optional[datetime]
    attending_doctor: Optional[str]
    location: Optional[str]
    diagnosis: Optional[str]


class HL7Handler:
    """
    Handler for HL7 v2.x messages.

    Supports:
    - ADT (Admission, Discharge, Transfer) messages
    - ORU (Observation Result) messages
    - Message parsing and creation
    """

    # HL7 message type handlers
    MESSAGE_TYPES = {
        "ADT": "Admission/Discharge/Transfer",
        "ORU": "Observation Result",
        "ORM": "Order Message",
        "SIU": "Scheduling Information",
        "MDM": "Medical Document Management",
    }

    # ADT event types
    ADT_EVENTS = {
        "A01": "Admit/Visit Notification",
        "A02": "Transfer",
        "A03": "Discharge/End Visit",
        "A04": "Register a Patient",
        "A08": "Update Patient Information",
        "A11": "Cancel Admit",
        "A13": "Cancel Discharge",
    }

    def __init__(self):
        """Initialize HL7 handler."""
        self._encoding_chars = "^~\\&"

    def parse_message(
        self, raw_message: str, user_id: Optional[str] = None
    ) -> Optional[Message]:
        """
        Parse raw HL7 message string.

        Args:
            raw_message: Raw HL7 message
            user_id: User ID for audit logging

        Returns:
            Parsed Message object or None
        """
        try:
            # Clean message (normalize line endings)
            cleaned = raw_message.replace("\n", "\r").strip()
            message = parse_message(cleaned)

            # Audit log
            msg_type = self._get_message_type(message)
            log_action(
                action="HL7_PARSE_MESSAGE",
                user_id=user_id,
                resource_type="HL7Message",
                request_details={"message_type": msg_type},
                phi_accessed=True,
            )

            return message
        except Exception as e:
            print(f"HL7 parse error: {e}")
            return None

    def _get_message_type(self, message: Message) -> str:
        """Extract message type from MSH segment."""
        try:
            msh = message.msh
            msg_type = str(msh.msh_9.msh_9_1.value)
            event = str(msh.msh_9.msh_9_2.value) if hasattr(msh.msh_9, "msh_9_2") else ""
            return f"{msg_type}^{event}" if event else msg_type
        except Exception:
            return "UNKNOWN"

    def parse_adt(
        self, raw_message: str, user_id: Optional[str] = None
    ) -> Optional[HL7AdmitInfo]:
        """
        Parse ADT (Admission/Discharge/Transfer) message.

        Args:
            raw_message: Raw HL7 ADT message
            user_id: User ID for audit logging

        Returns:
            HL7AdmitInfo or None
        """
        message = self.parse_message(raw_message, user_id)
        if not message:
            return None

        try:
            # Extract event type from MSH
            event_type = str(message.msh.msh_9.msh_9_2.value)

            # Extract patient info from PID segment
            pid = message.pid
            patient = self._parse_pid(pid)

            # Extract admit info from PV1 segment
            admit_datetime = None
            discharge_datetime = None
            attending_doctor = None
            location = None

            if hasattr(message, "pv1"):
                pv1 = message.pv1
                
                # Admit datetime (PV1-44)
                if hasattr(pv1, "pv1_44") and pv1.pv1_44.value:
                    admit_datetime = self._parse_datetime(str(pv1.pv1_44.value))
                
                # Discharge datetime (PV1-45)
                if hasattr(pv1, "pv1_45") and pv1.pv1_45.value:
                    discharge_datetime = self._parse_datetime(str(pv1.pv1_45.value))
                
                # Attending doctor (PV1-7)
                if hasattr(pv1, "pv1_7") and pv1.pv1_7.value:
                    attending_doctor = str(pv1.pv1_7.value)
                
                # Location (PV1-3)
                if hasattr(pv1, "pv1_3") and pv1.pv1_3.value:
                    location = str(pv1.pv1_3.value)

            # Extract diagnosis from DG1 segment if present
            diagnosis = None
            if hasattr(message, "dg1"):
                dg1 = message.dg1
                if hasattr(dg1, "dg1_3") and dg1.dg1_3.value:
                    diagnosis = str(dg1.dg1_3.value)

            return HL7AdmitInfo(
                event_type=event_type,
                patient=patient,
                admit_datetime=admit_datetime,
                discharge_datetime=discharge_datetime,
                attending_doctor=attending_doctor,
                location=location,
                diagnosis=diagnosis,
            )
        except Exception as e:
            print(f"Error parsing ADT: {e}")
            return None

    def _parse_pid(self, pid) -> HL7PatientInfo:
        """Parse PID (Patient Identification) segment."""
        # Patient ID (PID-3)
        patient_id = ""
        mrn = None
        if hasattr(pid, "pid_3") and pid.pid_3.value:
            patient_id = str(pid.pid_3.value)
            mrn = patient_id  # Often the MRN is in PID-3

        # Patient name (PID-5)
        first_name = None
        last_name = None
        if hasattr(pid, "pid_5") and pid.pid_5.value:
            name_parts = str(pid.pid_5.value).split("^")
            if len(name_parts) >= 1:
                last_name = name_parts[0]
            if len(name_parts) >= 2:
                first_name = name_parts[1]

        # Date of birth (PID-7)
        dob = None
        if hasattr(pid, "pid_7") and pid.pid_7.value:
            dob = self._parse_datetime(str(pid.pid_7.value))

        # Gender (PID-8)
        gender = None
        if hasattr(pid, "pid_8") and pid.pid_8.value:
            gender = str(pid.pid_8.value)

        # Address (PID-11)
        address = None
        if hasattr(pid, "pid_11") and pid.pid_11.value:
            address = str(pid.pid_11.value).replace("^", ", ")

        # Phone (PID-13)
        phone = None
        if hasattr(pid, "pid_13") and pid.pid_13.value:
            phone = str(pid.pid_13.value).split("^")[0]

        return HL7PatientInfo(
            patient_id=patient_id,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            gender=gender,
            address=address,
            phone=phone,
            mrn=mrn,
        )

    def _parse_datetime(self, hl7_datetime: str) -> Optional[datetime]:
        """Parse HL7 datetime format (YYYYMMDDHHMMSS)."""
        try:
            if len(hl7_datetime) >= 8:
                # Try full datetime first
                if len(hl7_datetime) >= 14:
                    return datetime.strptime(hl7_datetime[:14], "%Y%m%d%H%M%S")
                elif len(hl7_datetime) >= 12:
                    return datetime.strptime(hl7_datetime[:12], "%Y%m%d%H%M")
                else:
                    return datetime.strptime(hl7_datetime[:8], "%Y%m%d")
        except ValueError:
            pass
        return None

    def create_ack(
        self, original_message: Message, ack_code: str = "AA"
    ) -> str:
        """
        Create ACK (Acknowledgment) message.

        Args:
            original_message: Original message to acknowledge
            ack_code: AA (Accept), AE (Error), AR (Reject)

        Returns:
            ACK message string
        """
        # Extract original MSH values
        msh = original_message.msh
        sending_app = str(msh.msh_3.value) if hasattr(msh, "msh_3") else ""
        sending_fac = str(msh.msh_4.value) if hasattr(msh, "msh_4") else ""
        recv_app = str(msh.msh_5.value) if hasattr(msh, "msh_5") else ""
        recv_fac = str(msh.msh_6.value) if hasattr(msh, "msh_6") else ""
        msg_control_id = str(msh.msh_10.value) if hasattr(msh, "msh_10") else ""

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Build ACK message
        ack_lines = [
            f"MSH|^~\\&|{recv_app}|{recv_fac}|{sending_app}|{sending_fac}|{timestamp}||ACK|{msg_control_id}|P|2.5",
            f"MSA|{ack_code}|{msg_control_id}",
        ]

        return "\r".join(ack_lines)

    @staticmethod
    def get_event_description(event_code: str) -> str:
        """Get description for ADT event code."""
        return HL7Handler.ADT_EVENTS.get(event_code, f"Unknown Event ({event_code})")
