# FishDex AI Server Dashboard

The FishDex AI Server includes a built-in real-time monitoring and control dashboard. This allows developers and operators to monitor the status of the local AI Server, view live logs, track processing jobs, and manually retry failed jobs.

The dashboard connects to the AI Server via HTTP (for polling statistics and listing jobs) and WebSockets (for live streaming logs and job progress updates).

---

## Architecture Diagram

```
             ┌────────────────────┐
             │    Flutter App     │
             │ Camera + User UI   │
             └─────────┬──────────┘
                       │
                       │ uploads video / creates job
                       v
             ┌────────────────────┐
             │     Appwrite       │
             │ Database + Storage │
             └─────────┬──────────┘
                       │
                       │ AI Server polls / processes jobs
                       v
      ┌────────────────────────────────────┐
      │        Windows AI Server           │
      │ FastAPI + YOLOv8 OBB + ResNet50    │
      │                                    │
      │ - Downloads & processes jobs       │
      │ - Broadcaster (EventBus singleton) │
      └──────────────┬─────────────────────┘
                     │
                     │ WebSocket / HTTP API
                     v
      ┌────────────────────────────────────┐
      │      FishDex Server Dashboard      │
      │    http://127.0.0.1:8000/          │
      │                                    │
      │ - Uptime, CPU, RAM metrics         │
      │ - Loaded models status             │
      │ - Table of last 50 jobs            │
      │ - Streaming log output panel       │
      │ - Job retry trigger                │
      └────────────────────────────────────┘
```

---

## Local Configuration

All dashboard settings are configured via environment variables in the `.env` file of the `ai-server`.

| Variable | Description | Default |
|----------|-------------|---------|
| `FISHDEX_SKIP_AUTH` | Disable authentication (ideal for local development) | `false` |
| `FISHDEX_DASHBOARD_SECRET` | Secret key password required to log in to the dashboard | `change-me` |
| `FISHDEX_DEVICE` | Compute device (`cpu` or `cuda`) | `cpu` |

---

## Running the Dashboard

1. Start the server from the `ai-server` directory:
   ```bash
   .\venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
   ```

2. Open your web browser and navigate to:
   ```text
   http://127.0.0.1:8000/
   ```

3. If `FISHDEX_SKIP_AUTH` is `false`, a password prompt will appear. Enter your `FISHDEX_DASHBOARD_SECRET` (defaults to `change-me`).

---

## Features

### 1. System Health & Performance
* Real-time charts showing CPU and Memory RAM usage.
* Computes server uptime dynamically.
* Displays PyTorch CUDA GPU availability and device name.

### 2. Model Registry Info
* Identifies if the OBB Detector (`fish_detector_v1.onnx`) is loaded.
* Identifies if the Classifier is loaded and the path to its file.

### 3. Live Logs terminal
* Captured from standard Python logging output handlers.
* Automatically colorized by severity level (`INFO` = green, `WARNING` = yellow, `ERROR` = red).
* Automatically auto-scrolls to the bottom.

### 4. Interactive Jobs List
* Displays the 50 most recent jobs registered in the Appwrite database.
* Shows details including Job ID, User ID, current Status, classified Species, confidence level, and creation timestamp.
* Offers a **Reintentar** (Retry) button next to any failed job. Tapping it will invoke the AI Server pipeline process for that job immediately.
