"""
Combined Posture, Hydration, and Presence Monitoring Script.
This script integrates continuous real-time posture and hydration monitoring with periodic presence detection.
All alerts (posture, hydration, sitting duration) are logged to a single log file and announced via a voice alert FIFO.
"""

# === Import required modules ===

import cv2
import numpy as np
import requests
import base64
import time
import os
import json
import threading
import subprocess
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# === Global state and synchronization ===

log_lock = threading.Lock()
frame_lock = threading.Lock()
stop_event = threading.Event()

# Global shared frame for presence detection
last_frame = None

# === Voice alert function (using FIFO) ===

def send_voice_alert(text):
    """Send a voice alert using espeak directly to avoid FIFO complexity."""
    try:
        # Use espeak directly instead of FIFO for simplicity
        subprocess.Popen(['espeak', '-s', '150', '-v', 'en', text], 
                        stdout=subprocess.DEVNULL, 
                        stderr=subprocess.DEVNULL)
        print(f"Voice alert sent: {text}")
    except Exception as e:
        print(f"Error sending voice alert: {e}")

# === Presence detection class (DetectStatus) and related methods ===

class PersonStatus(Enum):
    """Human posture status enumeration."""
    SITTING = "person sitting"
    STANDING = "person standing"
    AWAY = "person away from seat"

class DetectStatus:
    def __init__(self):
        # Status tracking
        self.current_status = PersonStatus.SITTING
        self.status_history = deque(maxlen=720)  # store 24 hours of data (one point per 2 minutes)
        self.sitting_start_time = None
        self.standing_away_start_time = None
        self.last_alert_time = None

        # Configuration parameters
        self.SITTING_ALERT_MINUTES = 30  # alert after sitting for 30 minutes
        self.STANDING_AWAY_RESET_MINUTES = 4  # reset sitting timer if away >4 minutes

        # Directories and log file
        self.image_dir = "detection_images_health_assistant"
        os.makedirs(self.image_dir, exist_ok=True)
        self.log_file = "detection_log_health_assistant.txt"
        self.reset_log_file()

        # Initialize the real-time plot
        self.setup_plot()

    def reset_log_file(self):
        """Clear the log file at startup."""
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("")
            print(f"Log file reset: {self.log_file}")
        except Exception as e:
            print(f"Error resetting log file: {e}")

    def warm_up_model(self):
        """Capture a test image and run it through the pipeline to warm up models."""
        print("Warming up models...")
        try:
            print("Taking a test photo...")
            cap = cv2.VideoCapture(0)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            if not cap.isOpened():
                print("Error: Could not open camera for warm-up")
                return False
            print("Camera warming up...")
            time.sleep(2)
            for _ in range(30):
                cap.read()
            print("Capturing test image...")
            ret, frame = cap.read()
            cap.release()
            if not ret:
                print("Error: Could not capture image for warm-up")
                return False

            capture_time = datetime.now()
            timestamp_str = capture_time.strftime("%Y%m%d_%H%M%S")
            test_filename = os.path.join(self.image_dir, f"warmup_{timestamp_str}.jpg")
            cv2.imwrite(test_filename, frame)
            print(f"Test image saved: {test_filename}")

            print("Testing AI pipeline on warm-up image...")
            ai_response = self.analyze_with_two_calls(test_filename)
            if ai_response:
                parsed_status = self.parse_status(ai_response)
                if parsed_status:
                    timestamp_log = capture_time.strftime("%Y-%m-%d %H:%M:%S")
                    self.log_status(timestamp_log, parsed_status)
                    print(f"SUCCESS: Models warmed up successfully - detected: {parsed_status.value}")
                    print(f"Warm-up image kept: {test_filename}")
                    return True
            print("FAILED: Model warm-up failed (no valid response or parse)")
            return False
        except Exception as e:
            print(f"FAILED: Model warm-up encountered an error: {e}")
            return False

    def analyze_with_two_calls(self, image_path):
        """Analyze an image via Moondream (description) then Ollama (classification)."""
        description = self._query_moondream(image_path, "Describe what you see in this image.")
        if not description:
            return None
        # Prepare classification prompt for Ollama
        query = (f"Based on this description: \"{description}\"\n\n"
                 "Answer with ONLY the number:\n\n"
                 "1 = person sitting\n"
                 "2 = person standing\n"
                 "3 = person away from seat\n\n"
                 "Answer:")
        classification_result = self._query_ollama_text_only(query)
        return classification_result

    def _query_moondream(self, image_path, prompt):
        """Ask the Moondream model to describe the image (streamed response)."""
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        print(f"\nAsking Moondream: {prompt}")
        print("\nMoondream: ", end="", flush=True)
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "moondream:latest",
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": True
                },
                timeout=300,
                stream=True
            )
            if response.status_code == 200:
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get('response', '')
                            print(token, end="", flush=True)
                            full_response += token
                        except json.JSONDecodeError as e:
                            print(f"\n[JSON Error] {e}")
                            continue
                print("\n")
                if full_response.strip():
                    return full_response
                else:
                    print("[WARNING] Empty response from Moondream")
                    return None
            else:
                print(f"\nError: Moondream returned status code {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("\n[TIMEOUT] Moondream took too long to respond.")
            return None
        except Exception as e:
            print(f"\n[ERROR] Moondream request failed: {e}")
            return None

    def _query_ollama_text_only(self, prompt):
        """Ask the Ollama model (text-only) to classify posture from description."""
        print(f"\nAsking Ollama: {prompt}")
        print("\nOllama: ", end="", flush=True)
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "phi3:mini",
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.1,
                        "repeat_penalty": 1.1
                    }
                },
                timeout=60,
                stream=True
            )
            if response.status_code == 200:
                full_response = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            token = chunk.get('response', '')
                            print(token, end="", flush=True)
                            full_response += token
                        except json.JSONDecodeError as e:
                            print(f"\n[JSON Error] {e}")
                            continue
                print("\n")
                if full_response.strip():
                    return full_response
                else:
                    print("[WARNING] Empty response from Ollama")
                    return None
            else:
                print(f"\nError: Ollama returned status code {response.status_code}")
                return None
        except requests.exceptions.Timeout:
            print("\n[TIMEOUT] Ollama did not respond in time.")
            return None
        except Exception as e:
            print(f"\n[ERROR] Ollama request failed: {e}")
            return None

    def parse_status(self, ai_response):
        """Parse the AI response to determine person status (sitting/standing/away)."""
        if not ai_response:
            return None
        response_lower = ai_response.lower().strip()
        # Exact matches for numeric answers
        if response_lower == "1":
            return PersonStatus.SITTING
        elif response_lower == "2":
            return PersonStatus.STANDING
        elif response_lower == "3":
            return PersonStatus.AWAY
        # Matches for enumerated answers
        if "1. person sitting" in response_lower or "1 person sitting" in response_lower:
            return PersonStatus.SITTING
        elif "2. person standing" in response_lower or "2 person standing" in response_lower:
            return PersonStatus.STANDING
        elif "3. person away from seat" in response_lower or "3 person away from seat" in response_lower:
            return PersonStatus.AWAY
        # Fallback keyword search
        if "sitting" in response_lower:
            return PersonStatus.SITTING
        elif "standing" in response_lower:
            return PersonStatus.STANDING
        elif "away" in response_lower:
            return PersonStatus.AWAY
        else:
            print(f"Cannot parse status from AI response: {ai_response}")
            return None

    def update_status_logic(self, new_status):
        """Update internal status and handle 30-minute sitting alert logic."""
        current_time = datetime.now()
        alert_triggered = False
        if new_status == PersonStatus.SITTING:
            if self.current_status in [PersonStatus.STANDING, PersonStatus.AWAY]:
                # Came back to sitting from a break
                if self.standing_away_start_time:
                    away_duration = current_time - self.standing_away_start_time
                    if away_duration.total_seconds() / 60 <= self.STANDING_AWAY_RESET_MINUTES:
                        print(f"Standing/away time {away_duration.total_seconds()/60:.1f} minutes (<= {self.STANDING_AWAY_RESET_MINUTES} min), not resetting sitting timer")
                    else:
                        print(f"Standing/away time {away_duration.total_seconds()/60:.1f} minutes (> {self.STANDING_AWAY_RESET_MINUTES} min), resetting sitting timer")
                        self.sitting_start_time = current_time
                else:
                    self.sitting_start_time = current_time
            elif self.current_status == PersonStatus.SITTING:
                # Continuously sitting, check if we've reached the alert threshold
                if self.sitting_start_time:
                    sitting_duration = current_time - self.sitting_start_time
                    if sitting_duration.total_seconds() / 60 >= self.SITTING_ALERT_MINUTES:
                        if not self.last_alert_time or (current_time - self.last_alert_time).total_seconds() >= 60:
                            # Trigger sitting-too-long alert
                            self.play_alert()
                            self.last_alert_time = current_time
                            alert_triggered = True
            else:
                # First time setting sitting timer
                self.sitting_start_time = current_time
        elif new_status in [PersonStatus.STANDING, PersonStatus.AWAY]:
            if self.current_status == PersonStatus.SITTING:
                self.standing_away_start_time = current_time
                print("Starting standing/away timer")
        # Update current status and record history
        self.current_status = new_status
        self.status_history.append({
            'timestamp': current_time,
            'status': new_status,
            'alert': alert_triggered
        })
        return alert_triggered

    def play_alert(self):
        """Trigger a voice alert for prolonged sitting via the FIFO."""
        alert_message = "You have been sitting for more than 30 minutes, please get up and move around"
        print(f"\nALERT: {alert_message}!")
        send_voice_alert(alert_message)

    def setup_plot(self):
        """Initialize an interactive timeline plot for posture status."""
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(12, 6))
        self.ax.set_title('Human Posture Detection Timeline', fontsize=14)
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Status')
        status_labels = ['Sitting', 'Standing', 'Away']
        self.ax.set_yticks([0, 1, 2])
        self.ax.set_yticklabels(status_labels)
        self.ax.set_ylim(-0.5, 2.5)

    def update_plot(self):
        """Update the timeline plot with new status data."""
        if not self.status_history:
            return
        timestamps = [item['timestamp'] for item in self.status_history]
        status_values = []
        alert_flags = []
        for item in self.status_history:
            if item['status'] == PersonStatus.SITTING:
                status_values.append(0)
            elif item['status'] == PersonStatus.STANDING:
                status_values.append(1)
            else:  # AWAY
                status_values.append(2)
            alert_flags.append(item['alert'])
        self.ax.clear()
        colors = ['green', 'blue', 'red']
        for i, (ts, status_val) in enumerate(zip(timestamps, status_values)):
            color = colors[status_val]
            self.ax.scatter(ts, status_val, c=color, s=50, alpha=0.7)
            if alert_flags[i]:
                # Mark points where an alert was triggered
                self.ax.scatter(ts, status_val, c='yellow', s=100, marker='*', alpha=0.8)
        # Re-label axes and format time axis
        self.ax.set_title('Human Posture Detection Timeline', fontsize=14)
        self.ax.set_xlabel('Time')
        self.ax.set_ylabel('Status')
        self.ax.set_yticks([0, 1, 2])
        self.ax.set_yticklabels(['Sitting', 'Standing', 'Away'])
        self.ax.set_ylim(-0.5, 2.5)
        if len(timestamps) > 1:
            time_range = timestamps[-1] - timestamps[0]
            if time_range.total_seconds() > 3600:
                self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            else:
                self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%M:%S'))
        plt.tight_layout()
        plt.draw()
        plt.pause(0.1)

    def log_status(self, timestamp_str, status, alert=False):
        """Append a status (and alert flag) entry to the log file."""
        try:
            log_lock.acquire()
            with open(self.log_file, 'a', encoding='utf-8') as f:
                if alert:
                    log_entry = f"{timestamp_str} - {status.value} - ALERT\n"
                else:
                    log_entry = f"{timestamp_str} - {status.value}\n"
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing to log file: {e}")
        finally:
            log_lock.release()

# === Continuous monitoring thread for posture and hydration ===

def continuous_monitoring(cap, interpreter_posture, interpreter_cup, detector):
    """Thread function: continuously process webcam frames for posture and cup."""
    global last_frame
    # Get TFLite model input/output details
    posture_input_details = interpreter_posture.get_input_details()
    posture_output_details = interpreter_posture.get_output_details()
    cup_input_details = interpreter_cup.get_input_details()
    cup_output_details = interpreter_cup.get_output_details()

    # State tracking for alerts
    bent_start_time = None
    bent_alerted = False
    no_cup_start_time = None
    no_cup_alerted = False
    cup_on_table_start_time = None
    cup_on_table_alerted = False
    
    # Cup status buffer system - 5 second buffer before state change
    candidate_cup_state = None
    candidate_state_start_time = None
    confirmed_cup_state = None
    
    # Cup status output tracking
    last_cup_status_output = 0

    # Input shapes and types
    input_shape_posture = posture_input_details[0]['shape'][1:3]  # (height, width)
    input_shape_cup = cup_input_details[0]['shape'][1:3]
    input_type_posture = posture_input_details[0]['dtype']
    input_type_cup = cup_input_details[0]['dtype']

    print("Continuous monitoring thread started, initializing camera...")
    frame_count = 0
    
    try:
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                print("Warning: Camera frame not read successfully")
                time.sleep(0.1)
                continue
            
            frame_count += 1
            
            # Check frame quality for first few frames
            if frame_count <= 10:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = gray.mean()
                print(f"Frame {frame_count} captured, brightness: {brightness:.2f}")
                
                # If frame is too dark, skip it
                if brightness < 5:
                    print(f"Frame {frame_count} too dark, skipping...")
                    continue

            # Share the latest frame for presence detection
            frame_lock.acquire()
            last_frame = frame.copy()
            frame_lock.release()
            
            if frame_count == 1:
                print("First valid frame shared with main thread")

            # Skip posture/cup analysis if user is away (no person present)
            current_status = detector.current_status
            if current_status == PersonStatus.AWAY:
                # Reset any timers when user is away
                bent_start_time = None
                bent_alerted = False
                no_cup_start_time = None
                no_cup_alerted = False
                cup_on_table_start_time = None
                cup_on_table_alerted = False
                # Reset cup buffer system when user is away
                candidate_cup_state = None
                candidate_state_start_time = None
                confirmed_cup_state = None
                time.sleep(0.1)
                continue

            # Prepare frame for posture model
            frame_resized_posture = cv2.resize(frame, (input_shape_posture[1], input_shape_posture[0]))
            if frame_resized_posture.ndim == 2 and posture_input_details[0]['shape'][3] == 1:
                input_data_posture = frame_resized_posture[:, :, np.newaxis]
            else:
                input_data_posture = frame_resized_posture
            if input_type_posture == np.float32:
                input_data_posture = input_data_posture.astype(np.float32) / 255.0
            else:
                input_data_posture = input_data_posture.astype(input_type_posture)
            input_data_posture = np.expand_dims(input_data_posture, axis=0)
            interpreter_posture.set_tensor(posture_input_details[0]['index'], input_data_posture)
            interpreter_posture.invoke()
            output_data_posture = interpreter_posture.get_tensor(posture_output_details[0]['index'])
            # Determine posture class (0 or 1)
            if output_data_posture.size == 1:
                posture_class = int(round(float(output_data_posture)))
            else:
                posture_class = int(np.argmax(output_data_posture))

            # Prepare frame for cup model
            frame_resized_cup = cv2.resize(frame, (input_shape_cup[1], input_shape_cup[0]))
            if frame_resized_cup.ndim == 2 and cup_input_details[0]['shape'][3] == 1:
                input_data_cup = frame_resized_cup[:, :, np.newaxis]
            else:
                input_data_cup = frame_resized_cup
            if input_type_cup == np.float32:
                input_data_cup = input_data_cup.astype(np.float32) / 255.0
            else:
                input_data_cup = input_data_cup.astype(input_type_cup)
            input_data_cup = np.expand_dims(input_data_cup, axis=0)
            interpreter_cup.set_tensor(cup_input_details[0]['index'], input_data_cup)
            interpreter_cup.invoke()
            output_data_cup = interpreter_cup.get_tensor(cup_output_details[0]['index'])
            # Determine cup class (0, 1, or 2)
            if output_data_cup.size == 1:
                cup_class = int(round(float(output_data_cup)))
            else:
                cup_class = int(np.argmax(output_data_cup))

            current_time = time.time()
            
            # Cup status buffer system - only change state after 5 seconds of consistency
            if candidate_cup_state != cup_class:
                # New candidate state detected
                candidate_cup_state = cup_class
                candidate_state_start_time = current_time
            elif candidate_state_start_time and (current_time - candidate_state_start_time) >= 5:
                # Candidate state has been consistent for 5 seconds
                if confirmed_cup_state != candidate_cup_state:
                    # State is actually changing - reset alert timers only now
                    previous_confirmed_state = confirmed_cup_state
                    confirmed_cup_state = candidate_cup_state
                    print(f"[CUP BUFFER] State changed from {previous_confirmed_state} to {confirmed_cup_state} after 5s buffer")
                    
                    # Reset alert timers only when state actually changes
                    if confirmed_cup_state != 2:  # not "no cup"
                        no_cup_start_time = None
                        no_cup_alerted = False
                    if confirmed_cup_state != 1:  # not "cup on table"
                        cup_on_table_start_time = None
                        cup_on_table_alerted = False
                    
                    # Start new timers for the new confirmed state
                    if confirmed_cup_state == 2 and no_cup_start_time is None:
                        no_cup_start_time = current_time
                    elif confirmed_cup_state == 1 and cup_on_table_start_time is None:
                        cup_on_table_start_time = current_time
            
            # Use confirmed state for display and alerts (fallback to candidate for initial state)
            active_cup_state = confirmed_cup_state if confirmed_cup_state is not None else candidate_cup_state
            
            # Output cup status every 5 seconds
            if current_time - last_cup_status_output >= 5:
                cup_status_text = ""
                alert_info = ""
                
                if active_cup_state == 0:
                    cup_status_text = "[CUP] Cup in hand (in use)"
                elif active_cup_state == 1:
                    cup_status_text = "[CUP] Cup on table (idle)"
                    if cup_on_table_start_time:
                        elapsed = int(current_time - cup_on_table_start_time)
                        remaining = max(0, 1200 - elapsed)  # 20 minutes = 1200 seconds
                        alert_info = f" | Idle {elapsed}s | {remaining}s until alert"
                elif active_cup_state == 2:
                    cup_status_text = "[NO CUP] No cup detected"
                    if no_cup_start_time:
                        elapsed = int(current_time - no_cup_start_time)
                        remaining = max(0, 600 - elapsed)  # 10 minutes = 600 seconds
                        alert_info = f" | No cup {elapsed}s | {remaining}s until alert"
                else:
                    cup_status_text = f"[UNKNOWN] Unknown cup state (class: {active_cup_state})"
                
                # Add buffer info if state is not yet confirmed
                buffer_info = ""
                if confirmed_cup_state != candidate_cup_state and candidate_state_start_time:
                    buffer_elapsed = current_time - candidate_state_start_time
                    buffer_remaining = max(0, 5 - buffer_elapsed)
                    buffer_info = f" | Buffer: {buffer_remaining:.1f}s to confirm"
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {cup_status_text}{alert_info}{buffer_info}")
                last_cup_status_output = current_time

            # Posture alert: bent over for more than 5 seconds
            if posture_class == 1:  # bent posture detected
                if bent_start_time is None:
                    bent_start_time = current_time
                    bent_alerted = False
                if not bent_alerted and (current_time - bent_start_time) >= 5:
                    message = "Please straighten your back, maintain an upright posture"
                    print(f"\nALERT: Bent posture detected for >5 seconds. {message}")
                    send_voice_alert(message)
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        log_lock.acquire()
                        with open(detector.log_file, 'a', encoding='utf-8') as f:
                            f.write(f"{timestamp_str} - Posture Alert: bent over for >5 seconds\n")
                    except Exception as e:
                        print(f"Error writing posture alert to log: {e}")
                    finally:
                        log_lock.release()
                    bent_alerted = True
            else:
                # Reset bent posture tracking if upright
                bent_start_time = None
                bent_alerted = False

            # Hydration alert: no cup for more than 10 minutes (only use confirmed state)
            if confirmed_cup_state == 2 and no_cup_start_time:  # no cup confirmed
                if not no_cup_alerted and (current_time - no_cup_start_time) >= 600:
                    message = "Please grab a cup of water, you have been without hydration for over 10 minutes"
                    print(f"\nALERT: No cup detected for >10 minutes. {message}")
                    send_voice_alert(message)
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        log_lock.acquire()
                        with open(detector.log_file, 'a', encoding='utf-8') as f:
                            f.write(f"{timestamp_str} - Hydration Alert: no cup for >10 minutes\n")
                        # Once alerted, avoid repeating until state changes
                    except Exception as e:
                        print(f"Error writing hydration alert to log: {e}")
                    finally:
                        log_lock.release()
                    no_cup_alerted = True

            # Hydration alert: cup on table untouched for more than 20 minutes (only use confirmed state)
            if confirmed_cup_state == 1 and cup_on_table_start_time:  # cup on table confirmed
                if not cup_on_table_alerted and (current_time - cup_on_table_start_time) >= 1200:
                    message = "Please take a drink, your water has been sitting untouched for over 20 minutes"
                    print(f"\nALERT: Cup untouched for >20 minutes. {message}")
                    send_voice_alert(message)
                    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        log_lock.acquire()
                        with open(detector.log_file, 'a', encoding='utf-8') as f:
                            f.write(f"{timestamp_str} - Hydration Alert: cup idle for >20 minutes\n")
                        # Once alerted, avoid repeating until state changes
                    except Exception as e:
                        print(f"Error writing hydration alert to log: {e}")
                    finally:
                        log_lock.release()
                    cup_on_table_alerted = True

            # Small delay to throttle the loop
            time.sleep(0.1)
    finally:
        cap.release()
        print("Continuous monitoring thread ending, camera released.")

# === Helper to restart Ollama (AI services) ===

def restart_ollama_service():
    """Restart the local Ollama service to ensure models are loaded fresh."""
    print("Restarting Ollama service asynchronously...")
    def restart_async():
        try:
            subprocess.run(['sudo', 'pkill', '-f', 'ollama'], capture_output=True, text=True)
            print("Stopped existing Ollama processes")
            time.sleep(3)
            subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Started Ollama service")
            time.sleep(5)
            print("Pulling required models...")
            subprocess.run(['ollama', 'pull', 'moondream:latest'], capture_output=True, text=True)
            print("Pulled moondream:latest")
            subprocess.run(['ollama', 'pull', 'phi3:mini'], capture_output=True, text=True)
            print("Pulled phi3:mini")
            # Verify the service is running
            for attempt in range(3):
                try:
                    resp = requests.get("http://localhost:11434/api/tags", timeout=5)
                    if resp.status_code == 200:
                        print("SUCCESS: Ollama service is running")
                        return True
                except Exception:
                    if attempt < 2:
                        print(f"Attempt {attempt+1} failed, retrying...")
                        time.sleep(2)
                    else:
                        print("FAILED: Could not confirm Ollama service startup")
                        return False
        except Exception as e:
            print(f"Error restarting Ollama: {e}")
            return False
    th = threading.Thread(target=restart_async, daemon=True)
    th.start()
    time.sleep(2)
    print("Ollama restart initiated in background.")
    return True

# === Main program logic ===

def main():
    print("Combined Posture and Presence Monitoring Script")
    print("=" * 50)
    # 1. Restart AI service (Ollama) for Moondream and classification models
    restart_ollama_service()
    # 2. Initialize detection system (presence monitoring)
    print("Initializing detection system...")
    detector = DetectStatus()
    # 3. Allow AI services time to be ready
    print("Waiting for AI services to be ready...")
    time.sleep(8)
    # 4. Warm up the AI pipeline with a test run
    print("Performing warm-up test...")
    if not detector.warm_up_model():
        print("Warm-up failed. Please ensure camera and AI services are working and try again.")
        return
    # 5. Load TensorFlow Lite models for posture and cup detection
    print("Loading TensorFlow Lite models...")
    try:
        import tensorflow as tf
        interpreter_posture = tf.lite.Interpreter(model_path="model_sit.tflite")
    except ImportError:
        import tflite_runtime.interpreter as tflite
        interpreter_posture = tflite.Interpreter(model_path="model_sit.tflite")
    interpreter_posture.allocate_tensors()
    try:
        import tensorflow as tf  # reuse tf if already imported above
        interpreter_cup = tf.lite.Interpreter(model_path="model_cup.tflite")
    except ImportError:
        import tflite_runtime.interpreter as tflite
        interpreter_cup = tflite.Interpreter(model_path="model_cup.tflite")
    interpreter_cup.allocate_tensors()
    # 6. Start webcam capture for continuous monitoring
    print("Starting webcam feed for continuous monitoring...")
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    if not cap.isOpened():
        print("Error: Could not open camera for continuous monitoring")
        return
    
    # Camera warm-up: discard first few frames as they might be black
    print("Warming up camera...")
    for i in range(10):
        ret, frame = cap.read()
        if ret:
            print(f"Warm-up frame {i+1}")
        time.sleep(0.1)
    
    print("Camera warm-up completed")
    # 7. Launch continuous monitoring thread (posture & cup)
    thread = threading.Thread(target=continuous_monitoring, args=(cap, interpreter_posture, interpreter_cup, detector))
    thread.daemon = True  # Daemon thread will exit when main program exits
    thread.start()
    
    # Wait for the continuous monitoring thread to start capturing frames
    print("Waiting for continuous monitoring to initialize...")
    max_wait_time = 30  # Wait up to 30 seconds
    wait_count = 0
    while last_frame is None and wait_count < max_wait_time:
        time.sleep(1)
        wait_count += 1
        print(f"Waiting for camera initialization... ({wait_count}/{max_wait_time})")
    
    if last_frame is None:
        print("ERROR: Camera failed to initialize after 30 seconds. Exiting.")
        return
    
    print("Continuous monitoring started successfully. Beginning scheduled presence checks...")
    try:
        while True:
            # Every 2 minutes, capture a frame for presence analysis
            frame_lock.acquire()
            if last_frame is None:
                frame_lock.release()
                print("Warning: last_frame is None, waiting...")
                time.sleep(1)
                continue
            capture_time = datetime.now()
            timestamp_str = capture_time.strftime("%Y%m%d_%H%M%S")
            image_path = os.path.join(detector.image_dir, f"detection_{timestamp_str}.jpg")
            # Use the shared frame from continuous monitoring instead of opening camera again
            frame_copy = last_frame.copy()
            frame_lock.release()
            
            # Save the frame for analysis
            cv2.imwrite(image_path, frame_copy)
            print(f"Presence check image saved: {image_path}")
            
            # Analyze the captured image (Moondream description + Ollama classification)
            ai_response = detector.analyze_with_two_calls(image_path)
            if ai_response:
                print(f"AI analysis result: {ai_response}")
                new_status = detector.parse_status(ai_response)
                if new_status:
                    print(f"Parsed status: {new_status.value}")
                    alert_triggered = detector.update_status_logic(new_status)
                    timestamp_log = capture_time.strftime("%Y-%m-%d %H:%M:%S")
                    detector.log_status(timestamp_log, new_status, alert_triggered)
                    detector.update_plot()
                    if alert_triggered:
                        print("ALERT triggered for prolonged sitting (30 min)!")
                else:
                    print("Status parsing failed for presence check")
            else:
                print("AI analysis failed to return result for presence check")
            # Wait for 2 minutes before next presence check
            print("Waiting 2 minutes for next presence check...")
            for i in range(120):
                if stop_event.is_set():
                    break
                time.sleep(1)
            if stop_event.is_set():
                break
    except KeyboardInterrupt:
        print("\nStopping monitoring due to keyboard interrupt.")
    finally:
        # Signal the continuous monitoring thread to stop and clean up
        stop_event.set()
        try:
            thread.join(timeout=5)
        except Exception as e:
            print(f"Error joining continuous thread: {e}")
        plt.close()
        print("Monitoring stopped. Exiting program.")

if __name__ == "__main__":
    main()