import asyncio
import logging
import time
import torch
import psutil
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

# Record server start time
START_TIME = time.time()

def get_system_stats() -> dict:
    """Retrieve current system metrics (CPU, RAM, Uptime, GPU)."""
    uptime = int(time.time() - START_TIME)
    
    # GPU info
    gpu_available = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if gpu_available else None

    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "uptime_seconds": uptime,
        "gpu_available": gpu_available,
        "gpu_name": gpu_name,
    }

async def system_monitoring_task():
    """Background loop that periodically broadcasts system metrics."""
    logger.info("System monitoring service started")
    while True:
        try:
            stats = get_system_stats()
            await event_bus.emit("server_status", stats)
        except Exception as e:
            logger.error(f"Error in system monitoring loop: {e}")
        await asyncio.sleep(5)

_monitor_task = None

def start_system_monitor():
    """Start the background monitoring task in the active event loop."""
    global _monitor_task
    if _monitor_task is None:
        _monitor_task = asyncio.create_task(system_monitoring_task())
