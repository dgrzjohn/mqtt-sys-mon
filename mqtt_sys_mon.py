#!/usr/bin/env python3
"""
Lightweight System Monitor to MQTT for Home Assistant Auto-Discovery.
Supports CPU, RAM, Disk, and CPU Temperature across Linux and Windows.
Compatible with both paho-mqtt v1.x and v2.x.
"""

import os
import sys
import time
import json
import socket
import logging
import platform
import argparse

# Configurable Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("mqtt_sys_mon")

# Try to import dependencies
try:
    import psutil
except ImportError:
    logger.critical("Dependency 'psutil' is missing. Please install it using your package manager or pip.")
    sys.exit(1)

try:
    import paho.mqtt.client as mqtt
except ImportError:
    logger.critical("Dependency 'paho-mqtt' is missing. Please install it using your package manager or pip.")
    sys.exit(1)


def get_default_config():
    """Generates default configuration dict."""
    hostname = socket.gethostname()
    # Normalize hostname for MQTT client ID and safe characters
    safe_hostname = "".join(c for c in hostname if c.isalnum() or c in "-_").lower()
    
    # Check default disk partition depending on OS
    default_disk = "C:\\" if platform.system() == "Windows" else "/"

    return {
        "mqtt": {
            "host": "localhost",
            "port": 1883,
            "username": "",
            "password": "",
            "client_id": f"sys_mon_{safe_hostname}",
            "keepalive": 60,
            "discovery_prefix": "homeassistant"
        },
        "sensor": {
            "hostname": hostname,
            "interval": 30,
            "temperature_sensor_key": "auto",
            "temperature_unit": "C",
            "ram_metrics": "used_percent",
            "disks": [default_disk]
        }
    }


def load_config(config_path):
    """Loads configuration from JSON file or returns defaults."""
    config = get_default_config()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = json.load(f)
            
            # Deep merge user config with defaults
            if "mqtt" in user_config:
                config["mqtt"].update(user_config["mqtt"])
            if "sensor" in user_config:
                config["sensor"].update(user_config["sensor"])
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}. Using defaults.")
    else:
        logger.warning(f"Configuration file not found at {config_path}. Using defaults.")
        
    return config


def sanitize_name(name):
    """Sanitizes a string to be used in MQTT topic names (alphanumeric and underscores only)."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name).lower().strip("_")


def get_cpu_temp(sensor_key="auto"):
    """Fetches CPU temperature safely across platforms where supported."""
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        
        # If user specified a key, try to use it
        if sensor_key != "auto" and sensor_key in temps:
            entries = temps[sensor_key]
            if entries:
                print(entries[0].current)
                return entries[0].current
        
        # Otherwise search for common CPU temp keys
        for key in ["cpu_thermal", "coretemp", "acpitz"]:
            if key in temps and temps[key]:
                return temps[key][0].current
                
        # Fallback to the first available temperature sensor
        for key, entries in temps.items():
            if entries:
                return entries[0].current
    except Exception as e:
        logger.debug(f"Failed to read CPU temperature: {e}")
    return None


class SystemMonitor:
    def __init__(self, config):
        self.config = config
        self.mqtt_cfg = config["mqtt"]
        self.sensor_cfg = config["sensor"]
        self.hostname = self.sensor_cfg["hostname"]
        self.safe_hostname = sanitize_name(self.hostname)
        self.client = None
        self.connected = False
        
        # Cache list of valid disks to monitor
        self.disks = []
        for disk in self.sensor_cfg.get("disks", []):
            if os.path.exists(disk):
                self.disks.append(disk)
            else:
                logger.warning(f"Disk path '{disk}' does not exist and will not be monitored.")

        # Topics
        self.state_topic = f"{self.mqtt_cfg['discovery_prefix']}/sensor/{self.safe_hostname}/state"
        self.availability_topic = f"{self.mqtt_cfg['discovery_prefix']}/sensor/{self.safe_hostname}/status"

    def setup_mqtt(self):
        """Initializes MQTT client supporting both paho-mqtt v1 and v2 API."""
        try:
            # Paho MQTT v2.x requires setting the API version explicitly
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id=self.mqtt_cfg["client_id"])
        except AttributeError:
            # Fallback for Paho MQTT v1.x
            self.client = mqtt.Client(client_id=self.mqtt_cfg["client_id"])

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        
        # Set credentials if provided
        username = self.mqtt_cfg.get("username")
        password = self.mqtt_cfg.get("password")
        if username:
            self.client.username_pw_set(username, password)
            
        self.client.will_set(self.availability_topic, "offline", qos=1, retain=True)

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT Broker.")
            self.connected = True
            # Publish online status
            self.client.publish(self.availability_topic, "online", qos=1, retain=True)
            # Publish Home Assistant Discovery Configs
            self.publish_discovery_configs()
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.connected = False

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"Disconnected from MQTT Broker with code {rc}. Attempting reconnect...")
        self.connected = False

    def publish_discovery_configs(self):
        """Publishes Home Assistant MQTT Auto-Discovery configuration payloads."""
        prefix = self.mqtt_cfg["discovery_prefix"]
        
        # Device details shared across all sensors on this node
        device = {
            "identifiers": [f"sys_mon_{self.safe_hostname}"],
            "name": f"{self.hostname} System Monitor",
            "model": f"{platform.system()} {platform.release()}",
            "manufacturer": "Python System Monitor",
            "sw_version": "1.0"
        }

        # Core Sensors list
        sensors = [
            {
                "id": "cpu_usage",
                "name": "CPU Usage",
                "unit": "%",
                "icon": "mdi:cpu-64-bit",
                "val_tpl": "{{ value_json.cpu_usage }}"
            }
        ]

        ram_cfg = self.sensor_cfg.get("ram_metrics", "used_percent").lower().strip()
        
        if ram_cfg in ("used_percent", "both"):
            sensors.append({
                "id": "ram_usage_percent",
                "name": "RAM Usage Percent",
                "unit": "%",
                "icon": "mdi:memory",
                "val_tpl": "{{ value_json.ram_usage_percent }}"
            })
        
        if ram_cfg == "both":
            sensors.append({
                "id": "ram_used_gb",
                "name": "RAM Used",
                "unit": "GB",
                "icon": "mdi:memory",
                "val_tpl": "{{ value_json.ram_used_gb }}"
            })
            
        if ram_cfg in ("free_total", "both"):
            sensors.extend([
                {
                    "id": "ram_free_gb",
                    "name": "RAM Free",
                    "unit": "GB",
                    "icon": "mdi:memory",
                    "val_tpl": "{{ value_json.ram_free_gb }}"
                },
                {
                    "id": "ram_total_gb",
                    "name": "RAM Total",
                    "unit": "GB",
                    "icon": "mdi:memory",
                    "val_tpl": "{{ value_json.ram_total_gb }}"
                }
            ])

        # Add temperature sensor if supported
        if get_cpu_temp(self.sensor_cfg["temperature_sensor_key"]) is not None:
            temp_unit = self.sensor_cfg.get("temperature_unit", "C").upper().strip()
            unit_symbol = "°F" if temp_unit == "F" else "°C"
            sensors.append({
                "id": "cpu_temp",
                "name": "CPU Temperature",
                "unit": unit_symbol,
                "unit_of_measurement": unit_symbol,
                "device_class": "temperature",
                "icon": "mdi:thermometer",
                "val_tpl": "{{ value_json.cpu_temp }}"
            })

        # Add disks config
        for disk in self.disks:
            disk_safe = sanitize_name(disk)
            sensors.extend([
                {
                    "id": f"disk_usage_{disk_safe}",
                    "name": f"Disk Usage ({disk})",
                    "unit": "%",
                    "icon": "mdi:harddisk",
                    "val_tpl": f"{{{{ value_json.disk_usage_{disk_safe} }}}}"
                },
                {
                    "id": f"disk_free_{disk_safe}",
                    "name": f"Disk Free ({disk})",
                    "unit": "GB",
                    "icon": "mdi:harddisk",
                    "val_tpl": f"{{{{ value_json.disk_free_{disk_safe} }}}}"
                }
            ])

        for s in sensors:
            disc_topic = f"{prefix}/sensor/{self.safe_hostname}/{s['id']}/config"
            
            payload = {
                "name": s["name"],
                "state_topic": self.state_topic,
                "availability_topic": self.availability_topic,
                "value_template": s["val_tpl"],
                "unique_id": f"sys_mon_{self.safe_hostname}_{s['id']}",
                "device": device,
                "state_class": "measurement"
            }
            if "unit" in s:
                payload["unit_of_measurement"] = s["unit"]
            if "icon" in s:
                payload["icon"] = s["icon"]
            if "device_class" in s:
                payload["device_class"] = s["device_class"]

            # Publish configuration
            logger.info(f"Publishing discovery config for: {s['name']}")
            self.client.publish(disc_topic, json.dumps(payload), qos=1, retain=True)

    def collect_metrics(self):
        """Collects current system metrics into a dictionary."""
        metrics = {}
        
        # CPU
        # Interval is None so it calculates usage since the last call.
        metrics["cpu_usage"] = psutil.cpu_percent(interval=None)

        # RAM
        ram_cfg = self.sensor_cfg.get("ram_metrics", "used_percent").lower().strip()
        vm = psutil.virtual_memory()
        
        if ram_cfg in ("used_percent", "both"):
            metrics["ram_usage_percent"] = vm.percent
            
        if ram_cfg == "both":
            metrics["ram_used_gb"] = round(vm.used / (1024**3), 2)
            
        if ram_cfg in ("free_total", "both"):
            metrics["ram_free_gb"] = round(vm.available / (1024**3), 2)
            metrics["ram_total_gb"] = round(vm.total / (1024**3), 2)

        # Temperature (if available)
        temp = get_cpu_temp(self.sensor_cfg["temperature_sensor_key"])
        if temp is not None:
            temp_unit = self.sensor_cfg.get("temperature_unit", "C").upper().strip()
            if temp_unit == "F":
                temp = (temp * 9 / 5) + 32
            metrics["cpu_temp"] = round(temp, 1)

        # Disks
        for disk in self.disks:
            disk_safe = sanitize_name(disk)
            try:
                du = psutil.disk_usage(disk)
                metrics[f"disk_usage_{disk_safe}"] = du.percent
                metrics[f"disk_free_{disk_safe}"] = round(du.free / (1024**3), 2)
            except Exception as e:
                logger.error(f"Error reading disk usage for {disk}: {e}")

        return metrics

    def run(self):
        """Main loop that runs and publishes metrics periodically."""
        self.setup_mqtt()
        
        # Connect loop
        try:
            self.client.connect(
                self.mqtt_cfg["host"], 
                self.mqtt_cfg["port"], 
                self.mqtt_cfg["keepalive"]
            )
        except Exception as e:
            logger.error(f"Could not connect to MQTT Broker initially: {e}")

        # Start paho-mqtt network loop in background
        self.client.loop_start()

        # Prime CPU percent measurement (first call always returns 0.0)
        psutil.cpu_percent(interval=None)
        
        interval = self.sensor_cfg.get("interval", 60)
        logger.info(f"Started monitoring loop. Reporting stats every {interval} seconds.")

        try:
            while True:
                if self.connected:
                    try:
                        metrics = self.collect_metrics()
                        logger.debug(f"Publishing state: {metrics}")
                        self.client.publish(self.state_topic, json.dumps(metrics), qos=0)
                    except Exception as e:
                        logger.error(f"Failed to collect or publish metrics: {e}")
                else:
                    logger.warning("Waiting for MQTT connection to publish state...")
                
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Exiting script gracefully.")
        finally:
            # Set offline status and clean up
            if self.connected:
                self.client.publish(self.availability_topic, "offline", qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="System monitor MQTT script")
    parser.add_argument(
        "--config", 
        type=str, 
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"),
        help="Path to config.json file"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    
    # Start monitoring
    monitor = SystemMonitor(config)
    monitor.run()
