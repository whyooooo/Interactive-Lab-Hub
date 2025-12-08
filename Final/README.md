# Pill Checker

Integrated smart pillbox that combines touch sensing, camera capture, and Ollama-based vision analysis to verify every dose before it is taken. The repository satisfies all final deliverable requirements listed below and documents every iteration from smoke tests to the exhibition-friendly demo.

---

## Final Project Deliverables

### 1. Project Plan (Big idea • timeline • parts • fallback)
- **Document**: [Final_Proposal.md](./Final_Proposal.md)
- **Summary**: Prevent medication errors by verifying pill colors/counts before ingestion.
- **Timeline**: Week-by-week breakdown (ideation → hardware bring-up → AI pipeline → integration → user testing).
- **Parts Needed**: MPR121 breakout, SparkFun Qwiic button, RGB LED (BCM 21/20/26), PCA9685 servo driver, USB/Pi camera, speaker, Raspberry Pi, assorted resistors/wires.
- **Fallback Plan**: If servo lock or AI analysis fails, revert to manual confirmation workflow with logged captures and spoken prompts.

### 2. Functioning Project (Interactive device/system)
Both iterations share the same hardware stack (touch sensor + button + camera + LED + speaker) and were built sequentially so we could validate each interaction layer before moving to public demos.

#### Iteration A – [`smart_pillbox.py`](./smart_pillbox.py) (Full Feature Build)
- Dose scheduling with configurable start/end times and over-consumption lockout.
- Touch sensor + servo hook keep the lid locked until pills are verified.
- Camera capture + Ollama JSON parsing to ensure correct red/blue/green counts.
- Voice prompts plus RGB LED states (idle, processing, success, failure) guide the user.
- Demo video (placeholder): [Full smart_pillbox demo](https://example.com/smart-pillbox-demo).

**Quick Start (Iteration A)**
1. Complete Steps 1–2 in [General Quick Start](#general-quick-start-applies-to-both-iterations).
2. Launch the experience:
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 smart_pillbox.py
   ```
3. Optional validation: `python3 tests/test_button_camera.py` (button + camera), `python3 tests/test_open_outside_window.py` (window guard).

#### Iteration B – [`smart_pillbox_demo.py`](./smart_pillbox_demo.py) (Workshop Build)
- Always-on green idle blink so the pillbox “looks alive” the moment power is applied.
- Removes schedule/quantity gating; auto-speaks counts after every capture.
- Keeps camera + AI + RGB logic identical to the full build for accurate storytelling.
- Designed for exhibitions where attendees open the lid, watch the LED, and immediately hear per-color summaries.
- Demo video (placeholder): [Workshop demo](https://example.com/smart-pillbox-demo-lite).

**Quick Start (Iteration B)**
1. Complete Steps 1–2 in [General Quick Start](#general-quick-start-applies-to-both-iterations).
2. Run the simplified workflow:
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 smart_pillbox_demo.py
   ```
3. For LED-only verification without AI, run `python3 tests/test_green_idle_led.py`.

#### General Quick Start (applies to both iterations)
1. **Install dependencies (original commands, preserved as requested)**  
   ```bash
   # System dependencies
   sudo apt-get update
   sudo apt-get install -y python3-pip espeak
   pip install opencv-python
   pip install sparkfun-qwiic-button
   pip install requests
   pip install gpiozero
   # Python libraries
   pip3 install opencv-python requests adafruit-circuitpython-mpr121 adafruit-circuitpython-servokit

   # Ollama (if not installed)
   curl -fsSL https://ollama.com/install.sh | sh
   ollama pull moondream:latest
   ollama pull phi3:mini
   ```

2. **Configure** – edit [`pillbox_config.json`](./pillbox_config.json) to match your schedule, camera, and AI settings:
   ```json
   {
     "doses": [
       {
         "start_time": "08:00",
         "end_time": "08:30",
         "drugs": [
           {"name": "Drug A", "count": 1},
           {"name": "Drug B", "count": 2}
         ]
       }
     ],
     "camera": {
       "index": 0,
       "width": 1280,
       "height": 720,
       "fps": 30,
       "warmup_seconds": 2.0,
       "warmup_frames": 30
     },
     "vision": {
       "enabled": true,
       "model": "moondream:latest",
       "endpoint": "http://localhost:11434/api/generate",
       "temperature": 0.1,
       "timeout": 120,
       "save_json": true,
       "max_pills": 8
     }
   }
   ```

3. **Run the full experience**  
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 smart_pillbox.py
   ```

4. **Run the simplified demo (workshop mode)**  
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 smart_pillbox_demo.py
   ```

5. **Button → camera smoke test**  
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 test_button_camera.py
   ```
   - Press the Qwiic button to save a 720p photo in [`pillbox_images/`](./pillbox_images).
   - If `vision.enabled` is true, a JSON analysis is saved alongside the JPEG.

6. **RGB LED diagnostics (GPIO 21/20/26 → physical 40/38/37)**  
   ```bash
   cd /home/pi/Interactive-Lab-Hub/Final
   python3 test_rgb_light.py                 # common-cathode, solid green
   python3 test_rgb_light.py --common-anode  # for common-anode LEDs
   python3 test_tgb.py                       # amber blink
   python3 test_rgbtest.py                   # tune RGB ratios / blink patterns
   ```

### 3. Documentation of Design Process
| Phase | Description | Output |
| --- | --- | --- |
| Functional tests | Started with isolated hardware/AI tests (button, camera, touch, LED). | [`tests/test_button_camera.py`](./tests/test_button_camera.py), [`tests/test_open_outside_window.py`](./tests/test_open_outside_window.py), [`tests/test_green_idle_led.py`](./tests/test_green_idle_led.py) |
| Minimal integration | Chained sensors + LED + voice for the simplest “open lid → capture” loop. | Early internal scripts, camera warm-up notes (Lab 5 style). |
| Full smart pillbox | Added scheduling, over-dose guard, servo hooks, and Ollama parsing. | [`smart_pillbox.py`](./smart_pillbox.py) (final full-feature version). Demo video recorded from this build. |
| Exhibition demo | Simplified for workshop constraints: constant green blink, auto speech summaries, no manual inputs required. | [`smart_pillbox_demo.py`](./smart_pillbox_demo.py), LED state tweaks, RGB-only pill counting. |

Additional references: [IMPLEMENTATION_OUTLINE.md](./IMPLEMENTATION_OUTLINE.md) (step-by-step build guide) and [Final_Proposal.md](./Final_Proposal.md) (updated plan after each checkpoint).

### 4. Code & Asset Archive (amnesia-proof)
- **Runtime**: [`smart_pillbox.py`](./smart_pillbox.py), [`smart_pillbox_demo.py`](./smart_pillbox_demo.py)
- **Configuration**: [`pillbox_config.json`](./pillbox_config.json)
- **Captured data**: [`pillbox_images/`](./pillbox_images) (JPG + AI JSON + raw responses)
- **Hardware tests**: [`tests/`](./tests) directory (button, touch window, LED)
- **Documentation**: [Final_Proposal.md](./Final_Proposal.md), [IMPLEMENTATION_OUTLINE.md](./IMPLEMENTATION_OUTLINE.md), this README
- **Dependencies**: [`requirements.txt`](./requirements.txt)

Together these files allow a clean-room rebuild of the project if needed.

---

## Technical Notes

### Architecture
- **Hardware**: MPR121 capacitive touch, SparkFun Qwiic button, RGB LED (BCM 21/20/26), PCA9685 servo (optional), USB/Pi camera, speaker.
- **Software stack**: Python 3, `gpiozero`, `opencv-python`, `requests`, `pyttsx3`, local Ollama server.
- **LED states**: idle = green blink, processing = amber blink, success = solid green, failure = red fast blink.

### Interaction Flow
1. Dose window opens → amber LED + reminder voice prompt.
2. Lid opens (touch sensor) → green blink + voice instructions.
3. User presses Qwiic button → camera capture + AI analysis.
4. If colors/counts match prescription → solid green, unlock, “dose complete” prompt.
5. If mismatch/out-of-window → red LED and warning voice prompt.

### Troubleshooting
1. **Ollama connection failure** – ensure `ollama serve` is running locally.
2. **Camera unavailable** – confirm USB permissions and that `cv2.VideoCapture` can open the selected index.
3. **Dark captures** – increase `warmup_seconds`/`warmup_frames` or improve ambient lighting.
4. **MPR121 unresponsive** – check I²C wiring/address (`0x5A` default) and run `i2cdetect -y 1`.
5. **Servo not moving** – verify PCA9685 power, channel mapping, and duty cycle limits.

---

Course project – provided for instructional use. For questions, open an issue or refer to the contact info in [Final_Proposal.md](./Final_Proposal.md).




