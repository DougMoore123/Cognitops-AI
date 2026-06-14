"""
CognitOps AI - Severity Scorer
Applies deterministic rules over sensor_readings thresholds to validate
or escalate the LLM-assigned severity.

Thresholds derived from equipment_assets.csv criticality + sensor_readings.csv anomaly patterns.
"""
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal, Optional
from azure.monitor.opentelemetry import configure_azure_monitor

APPINSIGHTS_CONN = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "")
if APPINSIGHTS_CONN:
    configure_azure_monitor(connection_string=APPINSIGHTS_CONN)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cognitops.severity")

app = FastAPI(title="CognitOps Severity Scorer", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SeverityLevel = Literal["Low", "Medium", "High", "Critical"]

# Sensor thresholds from analysis of sensor_readings.csv
# anomaly_flag = Yes patterns: temp > 80°C, vibration > 6.0 mm/s, pressure < 90 PSI
THRESHOLDS = {
    "temperature_c":   {"High": 75.0, "Critical": 85.0},
    "vibration_mm_s":  {"High": 5.5,  "Critical": 7.0},
    "pressure_psi":    {"Low_High": 100.0, "Low_Critical": 70.0},   # below these = elevated risk
    "current_amp":     {"High": 70.0, "Critical": 80.0},
}

# Equipment criticality multiplier
CRITICALITY_ESCALATION = {
    "Critical": {"Low": "Medium", "Medium": "High", "High": "Critical"},
    "High":     {"Low": "Medium", "Medium": "High"},
}


class ScoringRequest(BaseModel):
    llm_severity: SeverityLevel
    confidence_level: Literal["Low", "Medium", "High"]
    sensor_snapshot: Optional[dict] = None
    asset_criticality: Optional[Literal["Low", "Medium", "High", "Critical"]] = None
    anomaly_flag: Optional[str] = None


class ScoringResponse(BaseModel):
    final_severity: SeverityLevel
    escalation_required: bool
    override_applied: bool
    override_reason: Optional[str] = None


def sensor_derived_severity(sensor: dict) -> tuple[SeverityLevel, str]:
    """Compute severity purely from sensor thresholds."""
    reasons = []
    max_sev: SeverityLevel = "Low"

    temp = sensor.get("temperature_c", 0)
    if temp >= THRESHOLDS["temperature_c"]["Critical"]:
        max_sev = "Critical"
        reasons.append(f"Temperature {temp}°C exceeds critical threshold {THRESHOLDS['temperature_c']['Critical']}°C")
    elif temp >= THRESHOLDS["temperature_c"]["High"]:
        if _sev_rank(max_sev) < _sev_rank("High"):
            max_sev = "High"
        reasons.append(f"Temperature {temp}°C exceeds high threshold")

    vib = sensor.get("vibration_mm_s", 0)
    if vib >= THRESHOLDS["vibration_mm_s"]["Critical"]:
        max_sev = "Critical"
        reasons.append(f"Vibration {vib} mm/s exceeds critical threshold")
    elif vib >= THRESHOLDS["vibration_mm_s"]["High"]:
        if _sev_rank(max_sev) < _sev_rank("High"):
            max_sev = "High"
        reasons.append(f"Vibration {vib} mm/s exceeds high threshold")

    psi = sensor.get("pressure_psi", 999)
    if psi < THRESHOLDS["pressure_psi"]["Low_Critical"]:
        max_sev = "Critical"
        reasons.append(f"Pressure {psi} PSI critically low")
    elif psi < THRESHOLDS["pressure_psi"]["Low_High"]:
        if _sev_rank(max_sev) < _sev_rank("High"):
            max_sev = "High"
        reasons.append(f"Pressure {psi} PSI below safe threshold")

    current = sensor.get("current_amp", 0)
    if current >= THRESHOLDS["current_amp"]["Critical"]:
        max_sev = "Critical"
        reasons.append(f"Current {current}A exceeds critical threshold")
    elif current >= THRESHOLDS["current_amp"]["High"]:
        if _sev_rank(max_sev) < _sev_rank("High"):
            max_sev = "High"
        reasons.append(f"Current {current}A elevated")

    return max_sev, "; ".join(reasons) if reasons else ""


def _sev_rank(s: str) -> int:
    return {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}[s]


def _max_sev(a: SeverityLevel, b: SeverityLevel) -> SeverityLevel:
    return a if _sev_rank(a) >= _sev_rank(b) else b


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "severity-scorer"}


@app.post("/score", response_model=ScoringResponse)
async def score(req: ScoringRequest):
    """
    Validates the LLM-assigned severity against:
    1. Sensor readings threshold rules
    2. Asset criticality multiplier
    3. Low confidence penalty

    Always escalates if final severity >= High AND confidence <= Medium.
    """
    final_sev = req.llm_severity
    override  = False
    reason    = None

    # 1. Sensor override
    if req.sensor_snapshot:
        sensor_sev, sensor_reason = sensor_derived_severity(req.sensor_snapshot)
        if _sev_rank(sensor_sev) > _sev_rank(final_sev):
            final_sev = sensor_sev
            override  = True
            reason    = f"Sensor override: {sensor_reason}"
            logger.info(f"Sensor override applied: {req.llm_severity} → {final_sev}")

    # 2. Anomaly flag
    if req.anomaly_flag == "Yes" and _sev_rank(final_sev) < _sev_rank("High"):
        final_sev = "High"
        override  = True
        reason    = (reason or "") + " | Sensor anomaly flag active"

    # 3. Asset criticality escalation
    if req.asset_criticality and req.asset_criticality in CRITICALITY_ESCALATION:
        escalation_map = CRITICALITY_ESCALATION[req.asset_criticality]
        if final_sev in escalation_map:
            new_sev   = escalation_map[final_sev]
            final_sev = _max_sev(final_sev, new_sev)
            override  = True
            reason    = (reason or "") + f" | {req.asset_criticality} asset criticality escalation"

    # 4. Low confidence penalty: bump Medium → High
    if req.confidence_level == "Low" and _sev_rank(final_sev) < _sev_rank("High"):
        final_sev = _max_sev(final_sev, "High")
        override  = True
        reason    = (reason or "") + " | Low confidence escalation"

    # Escalation decision
    escalate = (
        _sev_rank(final_sev) >= _sev_rank("High") and
        req.confidence_level in ("Low", "Medium")
    ) or _sev_rank(final_sev) == _sev_rank("Critical")

    return ScoringResponse(
        final_severity=final_sev,
        escalation_required=escalate,
        override_applied=override,
        override_reason=reason,
    )
