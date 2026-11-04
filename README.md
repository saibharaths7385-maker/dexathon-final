# dexathon-final

# SKYNEX – AI-Powered UAV Health Monitoring & Digital Twin Platform

### Team PROTONOVA
**Smart India Hackathon (SIH) 2026**  
**Problem Code:** SIH26054

---

## Overview

SKYNEX is an AI-assisted Prognostics and Health Management (PHM) platform developed for UAV propulsion systems. The system combines real-time telemetry monitoring, digital twin simulation, fault diagnosis, health assessment, Remaining Useful Life (RUL) estimation, and mission-aware decision support.

The objective of SKYNEX is to help UAV operators identify developing faults before critical failure, improve mission safety, reduce unplanned maintenance, and support informed operational decisions.

---

## Problem Statement

UAV propulsion systems are vulnerable to faults such as engine degradation, compressor fouling, fuel system issues, and sensor anomalies. Traditional monitoring approaches rely mainly on threshold-based alarms, which often identify problems only after performance has already degraded.

SKYNEX addresses this challenge by continuously analyzing telemetry data, comparing actual system behavior with a digital twin model, detecting abnormal conditions, assessing system health, and providing actionable recommendations to operators.

---

## Key Features

- Real-Time UAV Telemetry Monitoring
- Digital Twin Based Health Assessment
- Residual-Based Fault Detection
- Fault Classification Engine
- Health Score Computation
- Remaining Useful Life (RUL) Estimation
- Mission Recommendation System
- Fleet Health Monitoring
- Interactive Judge Demonstration Mode
- Web-Based Mission Control Dashboard

---

## Supported Fault Scenarios

The current prototype supports the following fault conditions:

### Healthy Engine
Nominal engine operation with all parameters within expected limits.

### Engine Degradation
Simulates progressive mechanical wear leading to performance degradation.

### Compressor Fouling
Represents efficiency loss caused by contamination and airflow restrictions.

### Fuel Leak
Simulates abnormal fuel consumption and fuel system performance degradation.

### Sensor Bias
Represents sensor drift and measurement inaccuracies while the physical system remains unchanged.

---

## System Architecture

> Insert architecture image below after uploading it into the repository.

![SKYNEX Architecture](docs/SKYNEX_System_Architecture.png.png)

### Laptop 1 Simulator Telemetry (Synthetic Demo Data)

The FastAPI backend connects as a read-only WebSocket client to Laptop 1 using
`LAPTOP1_TELEMETRY_WS_URL` and sends the Protocol 1 hello handshake. Set this
environment variable on Laptop 2 to Laptop 1's current IPv4 address; there is
no default or hardcoded simulator address.
`GET /api/v2/laptop1` returns the receiver diagnostics, latest normalized
frame, and unchanged `raw_latest_frame`. The Live Mission page polls
`GET /api/v2/telemetry/source`, which returns the selected live or offline
provider. A WebSocket upgrade alone remains `connecting`; the receiver reports
`connected` only after accepting a valid Protocol 1 telemetry frame.

The live boundary normalizes only valid source values and records every exact
source path in `latest_frame.normalization.fields`. Examples include
`airspeed_ms` to `airspeed_mps`, `engine_rpm` or `motor_rpm` to `rpm`, and
`fuel_pct` to `fuel_percent`. The dashboard uses the recorded path to keep
engine and motor labels distinct. Generic temperature is never presented as
EGT or CHT.

Laptop 1 frames are kept separate from the existing engine Digital Twin
pipeline. No propulsion-to-engine-sensor mapping or Laptop 1 remote controls
are enabled by this bridge. When running the frontend against Laptop 2, set
`VITE_API_BASE_URL` to that Laptop 2 backend's base URL. Local frontend
development defaults to `http://127.0.0.1:8000`; production builds use the
configured deployment URL.

On Laptop 1, confirm its current IPv4 address and that the simulator listens
on TCP port 8000 at `/ws/3d-simulator`, bound to an interface reachable by
Laptop 2. Allow inbound TCP port 8000 through Windows Firewall on Laptop 1's
active network profile, restricted to Laptop 2's current IP where possible.
On Laptop 2, configure and start the backend from the repository root:

```powershell
$env:LAPTOP1_TELEMETRY_WS_URL = "ws://<LAPTOP1_CURRENT_IPV4>:8000/ws/3d-simulator"
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

In another Laptop 2 terminal, set the frontend API base before starting Vite:

```powershell
Set-Location frontend
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
npm run dev
```

---

## System Workflow

```text
Telemetry Acquisition
          ↓
Data Processing
          ↓
EKF State Estimation
          ↓
Digital Twin Simulation
          ↓
Residual Generation
          ↓
Fault Detection
          ↓
Health Assessment
          ↓
RUL Estimation
          ↓
Mission Recommendation
```

---

## How SKYNEX Works

### 1. Telemetry Acquisition
The system continuously receives telemetry data such as:

- RPM
- EGT
- CHT
- Fuel Flow
- Vibration
- Pressure
- Environmental Parameters

### 2. Digital Twin Simulation
A physics-based digital twin estimates the expected engine behavior under current operating conditions.

### 3. Residual Analysis
The system compares actual telemetry against expected digital twin outputs and calculates residuals.

### 4. Fault Detection
Abnormal residual patterns are analyzed to identify potential faults.

### 5. Health Assessment
A health index is generated to represent the overall condition of the propulsion system.

### 6. Remaining Useful Life (RUL)
The platform estimates the remaining operational life before maintenance intervention becomes necessary.

### 7. Mission Decision Support
SKYNEX provides operational recommendations to assist UAV operators during missions.

---

## Dashboard Capabilities

The Mission Control Dashboard includes:

### Command Center
- System Overview
- Health Monitoring
- Mission Status

### Telemetry Monitoring
- Live Sensor Visualization
- Trend Analysis
- Performance Tracking

### Digital Twin
- Actual vs Expected Comparison
- Residual Monitoring
- Twin-Based Diagnostics

### Diagnosis Module
- Fault Classification
- Health Assessment
- Condition Awareness

### Fleet Monitoring
- Multi-UAV Overview
- Fleet Health Status
- Asset Visibility

### Analytics
- Historical Trends
- Performance Analysis
- Maintenance Insights

### Replay System
- Historical Mission Playback
- Event Investigation
- Fault Review

---

## Technology Stack

### Frontend
- React
- Vite
- JavaScript
- Plotly

### Backend
- FastAPI
- Python

### Analytics & PHM
- Digital Twin Modeling
- Extended Kalman Filter (EKF)
- Residual Analysis
- Health Assessment Logic
- RUL Estimation

### Deployment
- Render
- Vercel

---

## Repository Structure

```text
SKYNEX/
│
├── backend/
│   ├── api/
│   ├── twin/
│   └── services/
│
├── frontend/
│   ├── src/
│   ├── components/
│   ├── pages/
│   └── layouts/
│
├── docs/
│   └── architecture.png
│
└── README.md
```

---

## Current Prototype Scope

The current implementation demonstrates:

- Live telemetry simulation
- Digital twin workflow
- Fault scenario simulation
- Health score tracking
- Mission recommendations
- Fleet monitoring concepts
- Interactive dashboard interfaces

The platform is intended as a prototype demonstration for Smart India Hackathon evaluation and technology validation.

---

## Team PROTONOVA

- P Sai Bharath
- Nitya
- Sowmya
- Shravanth
- Abhiram
- Sai Bharath S

---

## Vision

To develop an intelligent UAV health management platform capable of supporting predictive maintenance, improving mission reliability, and enabling safer UAV operations through real-time diagnostics and digital twin technology.

---

**SKYNEX – AI-Powered UAV Health Monitoring & Digital Twin Platform**
