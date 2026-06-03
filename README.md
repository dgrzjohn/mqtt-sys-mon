# Multi-Host MQTT System Monitor for Home Assistant

A lightweight, cross-platform Python script that runs on multiple host types (Proxmox host, Debian VM, Raspberry Pi, Windows VM, Arch Linux desktop, Windows desktop) to collect and publish system metrics (CPU, RAM, Disks, and CPU Temperature) to an MQTT broker. 

Features Home Assistant **MQTT Auto-Discovery**, meaning no manual configuration is required in Home Assistant—the sensors will be discovered and grouped under a single device automatically!

---

## 1. Quick Start

### Step 1: Copy Code & Create Config
1. Create a directory named `mqtt-sys-mon` on your target host.
2. Copy `mqtt_sys_mon.py` and `config.json.example` into that directory.
3. Rename `config.json.example` to `config.json`.

### Step 2: Configure
Edit `config.json` to suit your host. Below is a breakdown of the configuration keys:

```json
{
  "mqtt": {
    "host": "YOUR_MQTT_BROKER_IP",          // IP address of your MQTT Broker (Home Assistant MQTT addon or Mosquitto)
    "port": 1883,                    // Port (default 1883)
    "username": "mqtt_user",         // MQTT username
    "password": "mqtt_password",     // MQTT password
    "client_id": "sys_mon_myhost",   // Unique client ID (leave blank to auto-generate based on hostname)
    "keepalive": 60,
    "discovery_prefix": "homeassistant" // Default HA discovery prefix
  },
  "sensor": {
    "hostname": "Proxmox-Host",      // Display name of the device in Home Assistant (leave blank to auto-detect hostname)
    "interval": 30,                  // Polling rate in seconds (default 30)
    "temperature_sensor_key": "auto",// Use "auto" or set specific psutil sensor key (e.g. "coretemp")
    "temperature_unit": "C",         // Temperature unit: "C" (default) or "F" for Fahrenheit conversion
    "ram_metrics": "used_percent",   // RAM metrics: "used_percent" (default), "free_total", or "both"
    "disks": [
      "/"                            // List of disk mount points/drive letters to monitor (e.g. ["/"] for Linux, ["C:\\"] for Windows)
    ]
  }
}
```

---

## 2. Installation Guides by Platform

### A. Linux Hosts (Proxmox Host, Debian VM, Raspberry Pi, Arch Linux)

You have two options to install dependencies on Linux:

#### Option 1: System-Wide Installation (Default & Recommended)
Installing dependencies directly via the system package manager is the recommended method for dedicated nodes. 
- **Why it's preferred**: It avoids managing virtual environments for simple utility scripts and bypasses Python's PEP 668 restrictions designed to prevent standard `pip` commands from corrupting system-managed Python packages. You can learn more about this in [PEP 668 – Marking Python Environments as Externally Managed](https://peps.python.org/pep-0668/).
- **Commands**:
  - **Debian / Ubuntu / Raspberry Pi OS**:
    ```bash
    sudo apt-get update
    sudo apt-get install python3-psutil python3-paho-mqtt
    ```
  - **Arch Linux**:
    ```bash
    sudo pacman -S python-psutil python-paho-mqtt
    ```

#### Option 2: Virtual Environment (.venv) Isolation
If you prefer not to install packages globally or are on a distribution where the system packages are not available:
- **Why it's used**: It isolates dependencies in a local `venv/` directory, avoiding any interactions with the host's system-managed Python packages.
- **Commands**:
  ```bash
  python3 -m venv venv
  ./venv/bin/pip install psutil paho-mqtt
  ```
  *Note: When executing the script, you must run it using the Python interpreter within the virtual environment: `./venv/bin/python3 mqtt_sys_mon.py`.*

#### Run as a Background Service (Systemd)
To ensure the script runs continuously and starts on boot:
1. Copy the systemd template file [mqtt-sys-mon.service.example](mqtt-sys-mon.service.example) to `/etc/systemd/system/mqtt-sys-mon.service`:
   ```bash
   sudo cp mqtt-sys-mon.service.example /etc/systemd/system/mqtt-sys-mon.service
   ```
2. Edit `/etc/systemd/system/mqtt-sys-mon.service` to configure the correct directory paths and choose either **Option A** (Virtual Environment path) or **Option B** (System-Wide Python path) inside the `ExecStart` parameter:
   ```bash
   sudo nano /etc/systemd/system/mqtt-sys-mon.service
   ```
3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable mqtt-sys-mon.service
   sudo systemctl start mqtt-sys-mon.service
   ```
4. Check status:
   ```bash
   sudo systemctl status mqtt-sys-mon.service
   ```

---

### C. Windows Hosts (Windows VM, Windows Desktop)
1. Open PowerShell or Command Prompt.
2. Install dependencies via pip:
   ```cmd
   pip install psutil paho-mqtt
   ```

#### Run as a Background Task (Task Scheduler)
To run the script silently in the background on system startup:
1. Open **Task Scheduler**.
2. Click **Create Basic Task...** (Name it `MQTT System Monitor`).
3. Set Trigger to **When the computer starts**.
4. Set Action to **Start a Program**.
5. Set Program/script to `pythonw.exe` (this runs python without opening a command window. Typically located in `C:\Users\<username>\AppData\Local\Programs\Python\Python3x\pythonw.exe` or `C:\Windows\pythonw.exe`).
6. Set **Add arguments** to the path of your script, e.g.:
   `C:\path\to\mqtt-sys-mon\mqtt_sys_mon.py`
7. Set **Start in** to the directory containing the script:
   `C:\path\to\mqtt-sys-mon`
8. In the task properties, under the General tab, select **Run whether user is logged on or not** and check **Run with highest privileges** (required if you want to access administrative system telemetry, though not strictly required for basic RAM/CPU/disk stats).

---

## 3. Dry-Run Verification
Before configuring system services, you can verify that python can load dependencies, parse configuration, and gather telemetry correctly by running the verification test script:

```bash
python3 dry_run_test.py
```
This script runs a mock MQTT broker internally and prints out the exact JSON payloads and Home Assistant Discovery configurations that would be sent over the network.
