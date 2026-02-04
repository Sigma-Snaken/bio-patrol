"""
MQTT client for receiving physiological sensor data.
"""
import json
import paho.mqtt.client as mqtt
import logging
import os
import asyncio
import sqlite3
from datetime import datetime
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BioSensorMQTTClient")

class BioSensorMQTTClient:
    def __init__(self, broker="localhost", port=1803, topic="/my/default/channel", db_path=None):
        self.broker = broker
        self.port = port
        self.topic = topic
        if db_path is None:
            # From src/backend/services/bio_sensor_mqtt.py → up 4 levels to project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            data_dir = os.path.join(project_root, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "sensor_data.db")
        else:
            self.db_path = db_path

        self.client = mqtt.Client(protocol=mqtt.MQTTv31)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.latest_data = None
        self._init_database()
    
    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_scan_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                bed_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                status INTEGER,
                bpm INTEGER,
                rpm INTEGER,
                data_json TEXT,
                is_valid BOOLEAN DEFAULT FALSE,
                details TEXT NULL
            )
        ''')
        conn.commit()
        conn.close()
    
    def _on_connect(self, client, userdata, flags, rc):
        # logger.info(f"Connected with result code {rc}")
        result, mid = client.subscribe(self.topic)
        logger.info(f"Subscribed to {self.topic}, result={result}, mid={mid}")
    
    def _on_message(self, client, userdata, msg):
        # logger.info(f"Received message: {msg.topic} {msg.payload.decode()}")
        self.latest_data = json.loads(msg.payload.decode())
    
    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
    
    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def _save_scan_data(self, task_id, data, retry_count, is_valid=False):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO sensor_scan_data 
            (task_id, bed_id, timestamp, retry_count, status, bpm, rpm, data_json, is_valid, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id,
            data.get('bed_id'),
            timestamp,
            retry_count,
            data.get('status'),
            data.get('bpm'),
            data.get('rpm'),
            json.dumps(data),
            is_valid,
            data.get('details'),
        ))
        conn.commit()
        conn.close()

    async def get_valid_scan_data(self, task_id=None, target_bed=None):
        if task_id is None:
            task_id = str(uuid.uuid4())

        # Read configurable magic numbers from runtime settings
        try:
            from settings.config import get_runtime_settings
            cfg = get_runtime_settings()
        except Exception:
            cfg = {}

        WAIT_TIME = cfg.get("bio_scan_wait_time", 10)
        RETRY_COUNT = cfg.get("bio_scan_retry_count", 19)
        INT_WAIT_TIME = cfg.get("bio_scan_initial_wait", 120)
        VALID_STATUS = cfg.get("bio_scan_valid_status", 4)
        valid_data = None

        await asyncio.sleep(INT_WAIT_TIME)
        for retry_count in range(RETRY_COUNT):
            if self.latest_data and 'records' in self.latest_data:
                for data in self.latest_data['records']:
                    print("scan_data: ", data, "\n")
                    is_valid = data['status'] == VALID_STATUS and data['bpm'] > 0 and data['rpm'] > 0
                    data['details'] = '量測正常' if is_valid else '無有效量測數值'
                    data['bed_id'] = target_bed
                    self._save_scan_data(task_id, data, retry_count, is_valid)

                    if is_valid and valid_data is None:
                        valid_data = data

                if valid_data is not None:
                    return {"task_id": task_id, "data": valid_data}

            # the last retry should not wait for extra interval
            if(retry_count + 1 < RETRY_COUNT):
                await asyncio.sleep(WAIT_TIME)

        return {"task_id": task_id, "data": None}


