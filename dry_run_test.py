#!/usr/bin/env python3
"""
Dry-run test script to verify mqtt_sys_mon.py behaves correctly.
Collects and prints metrics, and displays what HA Discovery payloads would look like.
"""

import os
import sys
import json
import logging
from unittest.mock import MagicMock

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Import the monitor module
try:
    import mqtt_sys_mon
except ImportError:
    # If not in path, add parent dir
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mqtt_sys_mon

def run_dry_test():
    logging.info("Starting dry-run verification...")
    
    # Mode 1: Default configuration (Celsius, used_percent RAM)
    logging.info("=== TESTING MODE 1: Defaults (Celsius, used_percent RAM) ===")
    config1 = mqtt_sys_mon.get_default_config()
    config1["sensor"]["hostname"] = "TestHost"
    config1["sensor"]["disks"] = ["/"] if os.path.exists("/") else ["C:\\"]
    
    monitor1 = mqtt_sys_mon.SystemMonitor(config1)
    
    # Verify metrics collection
    logging.info("--- Metrics Collection Test ---")
    try:
        metrics = monitor1.collect_metrics()
        logging.info(f"Successfully collected metrics:\n{json.dumps(metrics, indent=2)}")
        assert "ram_usage_percent" in metrics, "Missing ram_usage_percent in default mode"
        assert "ram_free_gb" not in metrics, "Unexpected ram_free_gb in default mode"
    except Exception as e:
        logging.error(f"Failed to collect metrics in Mode 1: {e}")
        return False
        
    # Verify discovery configurations
    logging.info("--- Home Assistant Discovery Payload Test ---")
    mock_client = MagicMock()
    monitor1.client = mock_client
    published_topics = []
    
    def mock_publish(topic, payload, qos=0, retain=False):
        try:
            parsed_payload = json.loads(payload)
            published_topics.append((topic, parsed_payload))
        except Exception:
            published_topics.append((topic, payload))
            
    mock_client.publish = mock_publish
    
    try:
        monitor1.publish_discovery_configs()
        logging.info(f"Generated {len(published_topics)} discovery payloads:")
        for topic, payload in published_topics:
            logging.info(f"Topic: {topic}")
            if isinstance(payload, dict):
                logging.info(f"Payload (abbrev): {json.dumps(payload, indent=2)[:300]}...")
            else:
                logging.info(f"Payload: {payload}")
    except Exception as e:
        logging.error(f"Failed to generate discovery configs in Mode 1: {e}")
        return False

    # Mode 2: Fahrenheit temperature and free_total RAM
    logging.info("=== TESTING MODE 2: Fahrenheit, free_total RAM ===")
    config2 = mqtt_sys_mon.get_default_config()
    config2["sensor"]["hostname"] = "TestHost"
    config2["sensor"]["disks"] = ["/"] if os.path.exists("/") else ["C:\\"]
    config2["sensor"]["temperature_unit"] = "F"
    config2["sensor"]["ram_metrics"] = "free_total"
    
    monitor2 = mqtt_sys_mon.SystemMonitor(config2)
    logging.info("--- Metrics Collection Test ---")
    try:
        metrics = monitor2.collect_metrics()
        logging.info(f"Successfully collected metrics:\n{json.dumps(metrics, indent=2)}")
        assert "ram_free_gb" in metrics, "Missing ram_free_gb in free_total mode"
        assert "ram_total_gb" in metrics, "Missing ram_total_gb in free_total mode"
        assert "ram_usage_percent" not in metrics, "Unexpected ram_usage_percent in free_total mode"
    except Exception as e:
        logging.error(f"Failed to collect metrics in Mode 2: {e}")
        return False

    # Verify discovery configurations for Mode 2
    logging.info("--- Home Assistant Discovery Payload Test ---")
    published_topics.clear()
    monitor2.client = mock_client
    try:
        monitor2.publish_discovery_configs()
        logging.info(f"Generated {len(published_topics)} discovery payloads:")
        for topic, payload in published_topics:
            if "cpu_temp" in topic:
                assert payload.get("unit_of_measurement") == "°F", f"Expected temperature unit °F, got {payload.get('unit_of_measurement')}"
            logging.info(f"Topic: {topic}")
            if isinstance(payload, dict):
                logging.info(f"Payload (abbrev): {json.dumps(payload, indent=2)[:300]}...")
    except Exception as e:
        logging.error(f"Failed to generate discovery configs in Mode 2: {e}")
        return False

    # Mode 3: both RAM metrics
    logging.info("=== TESTING MODE 3: both RAM metrics ===")
    config3 = mqtt_sys_mon.get_default_config()
    config3["sensor"]["hostname"] = "TestHost"
    config3["sensor"]["disks"] = ["/"] if os.path.exists("/") else ["C:\\"]
    config3["sensor"]["ram_metrics"] = "both"
    
    monitor3 = mqtt_sys_mon.SystemMonitor(config3)
    logging.info("--- Metrics Collection Test ---")
    try:
        metrics = monitor3.collect_metrics()
        logging.info(f"Successfully collected metrics:\n{json.dumps(metrics, indent=2)}")
        assert "ram_usage_percent" in metrics, "Missing ram_usage_percent in both mode"
        assert "ram_used_gb" in metrics, "Missing ram_used_gb in both mode"
        assert "ram_free_gb" in metrics, "Missing ram_free_gb in both mode"
        assert "ram_total_gb" in metrics, "Missing ram_total_gb in both mode"
    except Exception as e:
        logging.error(f"Failed to collect metrics in Mode 3: {e}")
        return False

    logging.info("Dry-run test completed successfully!")
    return True

if __name__ == "__main__":
    success = run_dry_test()
    sys.exit(0 if success else 1)
