# Pill Checker – Smart Medication Verification System  
Authors: Yoyo Wang & Wenzhuo Ma 

---

## 1. Big Idea

In this project we design a smart medication box that tries to prevent real-world pill mistake, especially for people who take many drugs every day.

The core idea is: the user can only take the pills **after** our system verifies the **whole current dose** (all pills for this time) using computer vision.

At each scheduled dose time:

- The device uses speaker to tell the user what they should take now, for example:  
  “It is 8:00 AM. Please take 1 tablet of Drug A and 2 tablets of Drug B.”
- User puts all pills for this dose on a white **Verification Pad**.
- A 720p camera takes a photo; AI vision detects each pill type and count.
- If the detected recipe exactly matches the prescription for this time, servo unlocks and user can access pills.
- Otherwise the box stays locked, LED and speaker give warning, and we log the wrong attempt.

Besides pill verification, the system also has basic time control and logging: it knows when you should take medicine, reminds you, records if you miss the window, and warns if you keep opening the lid without actually taking a verified dose.

---

## 2. System Design & Hardware

The whole system is built around **Raspberry Pi 5**, running Python scripts to control sensors, time logic, and AI calls.

Main hardware modules:

- **Core & Camera**  
  - Raspberry Pi 5 with OS and local clock  
  - Pi-compatible 720p camera (top-down view on verification pad)

- **Verification Pad**  
  - Option A: mini load cell + HX711 + small 3×3 cm platform with white surface  
  - Option B: IR break beam with 3D printed pill area and white background  
  The pad mainly detect that there are “some pills” in reasonable range and not big random object.

- **User Feedback**  
  - RGB LED (yellow for ready, green for correct dose, red for error)  
  - Small OLED/LCD screen to show time, dose info, simple text instruction  
  - Speaker for tones and voice messages (TTS or pre-recorded)

- **Lock & Touch**  
  - Servo motor with a simple latch to lock the lid / pill compartment  
  - MPR121 capacitive touch sensor, with:
    - Lid pad: touch area near lid to detect lid open  
    - Grip pad: touch area on side or bottom to detect user picking up device  
    - Optional pill pad near pill area to detect that pill is picked up  

- **Enclosure**  
  - Laser-cut or 3D-printed box to mount Pi, camera, pad, servo and wires in stable position.

We will store the schedule and dose recipe in a configuration file (for example JSON), where each dose has a start time, end time, and a list of `(drug_id, count)`.

---

## 3. Time & Behavior Logic

The device uses Raspberry Pi’s time to handle medication schedule. For each dose we define a time window `[start_time, end_time]` (e.g. 08:00–08:30).

We also clearly distinguish:

- **Picking up the device** (only grip pad touched, no lid pad)  
- **Opening the lid** (lid pad touched, and servo state checked)

Design rules:

1. **Before `start_time`**

   - If user just picks up the box (grip pad), we do nothing serious. Maybe just show next dose time. No alarm, no open counter.  
   - If user tries to open lid (lid pad), we treat as early-open: speaker says something like “It is not time for medication yet, box is locked.” We increase early-open counter and write log.

2. **At `start_time`**

   - LED becomes yellow.  
   - Speaker announces current dose: which drugs and how many pills.  
   - Screen shows the same dose info and tells user: “Please place all pills for this dose on the white pad.”  
   - Dose state changes to `WAITING_FOR_DOSE`. We can also send a soft reminder again if user still not do anything after some minutes.

3. **During the window `[start_time, end_time]`**

   - User can pick up device as much as they want, this is not problem.  
   - Every time lid open (lid pad fired and servo at least partially unlocked), we increase `lid_open_count` for this dose.  
   - If `lid_open_count` becomes too big (for example ≥ 3) and still no verified dose, we trigger a “repeated open warning”: red LED blink and speaker say more serious sentence, like:  
     “Multiple lid openings detected without verified dose. Please follow instruction to complete dose safely.”

4. **At `end_time`**

   - If dose state is still not `TAKEN`, we mark it as `MISSED`.  
   - Device plays reminder: “The medication time window has ended. No correct dose recorded.”  
   - We log `missed_within_time_window`.

After the window finishes (taken or missed), later opens belong to next dose and not change this dose’s counters.

---

## 4. Full Workflow (Dose-Level)

Here I summarize the complete interaction for one scheduled dose.

1. **Dose starts**  
   At `start_time`, LED turns yellow, screen shows:  
   “08:00 Dose – Drug A: 1, Drug B: 2”.  
   Speaker:  
   > “It is 8:00 AM. Please take 1 tablet of Drug A and 2 tablets of Drug B.  
   > Place all pills for this dose on the white verification pad.”

2. **User places pills on pad**  
   User puts all pills for this dose onto the white pad. Load cell / IR confirms there is some object in expected range (not empty and not huge heavy thing). Screen shows “Analyzing dose, please wait”.

3. **Camera & AI vision**  
   The camera takes a 720p picture of the pad. The AI pipeline will try to:

   - detect each pill region,  
   - classify each pill into some label (Drug A / Drug B / Unknown…),  
   - count the number per label and build a **detected recipe**, for example:  
     `{DrugA:1, DrugB:2}`.

   Then we compare detected recipe with **expected recipe** from schedule for this time. Only if they match exactly (both type and count) we consider dose correct.

4. **Correct dose case**

   If recipe matches:

   - LED becomes green.  
   - Speaker plays a soft confirmation tone and sentence like “Dose verified. Please take your medication now.”  
   - Servo fully unlocks, user can access inside.  
   - When user takes pills, pill pad or small internal weight sensor detect removal.  
   - Dose state becomes `TAKEN`.  
   - We log `taken_during_valid_window` with timestamp and recipe information.

5. **Incorrect dose case**

   If recipe does not match (missing pill, extra pill, wrong drug, unknown pill, etc.):

   - LED becomes red and starts flashing.  
   - Speaker plays warning alarm and say something like:  
     “Dose error detected. Expected: 1 Drug A, 2 Drug B. Detected: 1 Drug A, 1 Drug B. Please adjust your pills and try again.”  
   - Servo stays locked, so user cannot access pill compartment.  
   - We log `wrong_dose_attempt` with expected vs detected.  
   - System waits user to clear pad and place again.

6. **Early-open and repeated open**

   - If user opens lid before time, we block and log early-open.  
   - If user opens lid many times in same window but never finishes a correct dose, we warn about repeated opening, to avoid dangerous “play with box” behavior.

---

## 5. Implementation Plan (5 Weeks)

We propose this approximate timeline:

- **Week 1: Hardware and Box**  
  Assemble Raspberry Pi 5, camera, servo, LED, speaker, MPR121, verification pad into the enclosure. Test basic power and physical fit.

- **Week 2: Sensors, Servo and Camera Integration**  
  Write small scripts to read pad data (load cell / IR), read MPR121 for lid vs grip, control servo lock states, and capture 720p images.

- **Week 3: AI Vision and Dose Logic**  
  Collect example pill images and integrate a simple vision model or API. Implement dose recipe comparison and YES/NO decision for the full dose.

- **Week 4: Time Logic and UX**  
  Add scheduling, time windows, LED status rules, speaker voice prompts, screen messages, and event logging.

- **Week 5: Testing, Video and Documentation**  
  Execute testing plan, fix bugs, record demo video and finish final report.

---

## 6. Testing Plan

I separate testing into two level: first we test each component after we finish it, then we do integrated testing for the whole system. I try to keep structure clear but not too many tiny points.

### 6.1 Component Testing

After each hardware/software part is implemented, we do small simple tests:

- **Pi 5 and OS**  
  Check it boot stable, we can run Python scripts and see no overheat under light load.

- **Camera**  
  Capture several 720p pictures of pills under bright, dim and side light inside the box, check manually if pills are clear enough for later AI.

- **Verification Pad**  
  Measure values for empty pad, correct dose, fewer pills, more pills, and random heavy object. We want that the range for “dose present” is separate enough so threshold is easy.

- **MPR121**  
  Touch lid pad vs grip pad and print out which electrode fired. Confirm they do not trigger each other too much.

- **Servo & Lock**  
  Move servo to locked / half / fully open positions and try open lid by hand to feel if it matches the state.

- **LED, Screen, Speaker**  
  Write a small demo that shows different status colors, text, and three kinds of sounds (confirmation, alarm, reminder).

- **Scheduler logic**  
  Use fake time windows (few minutes) and check at start_time we get reminder, at end_time we get “missed” message if no dose taken.

- **AI vision**  
  Offline test on a dataset of pill photos, including correct dose, wrong dose, similar-pill, rotated or partly covered pills. We measure how often the model returns the correct recipe vs wrong; only exact match will be considered YES in system.

- **Logging**  
  Manually trigger events and open log file to see if timestamps and event types make sense.

### 6.2 Integrated Functional Testing

After all basic pieces work, we test the entire flow like a real user:

1. **Different dose combinations**  
   We run several trials:

   - exact correct dose (e.g. Drug A×1, Drug B×2)  
   - missing one pill  
   - extra pill  
   - replacing one pill with wrong drug  

   For each trial we let the system capture 720p image, run AI, and observe LED color, speaker voice, and servo state. Only full correct dose should unlock, others should stay locked and give clear explanation.

2. **Time control and early-open**  
   We test pick up vs open before window. When we only touch grip pad before time, nothing serious happens. When we try to open lid early, we get “too early” voice and log entry, and servo never unlock.

3. **Repeated open in same window**  
   During one active window we open lid three or more times but never put pills. On the third time, system should warn that user open too many times without dose, to encourage user to actually follow instruction.

4. **Normal successful window**  
   We run through a full successful dose: reminder at start, user places correct dose, AI verifies, servo unlock, pills removed, and state becomes `TAKEN` with proper log.

5. **Missed dose**  
   We let entire window pass without a successful dose. At end_time, system should announce that dose is missed and record it.

### 6.3 User Testing

Finally, we also want to see how real people use it:

- For first-time users, we just give simple instruction and watch if they can listen to speaker, read screen, and correctly place all pills for one dose. We record how many attempts they need.
- For misuse simulation, we ask them to try dishonest actions: wrong pills, early open, etc. System should block these and show clear reasons.

---

## 7. Fallback Plan

If the AI vision part is not reliable enough (for example training data too small, or pills too similar), we still can fall back to a simpler **guided medication box** mode.

In that mode:

- The box still knows schedule and time window.  
- It still reminds the user with speaker, locks with servo, and logs early-open and missed dose.  
- It may only ensure “one compartment at a time” or “one-pill-at-a-time”, but not check the exact type of each pill.

So even if advanced computer vision fails, the rest of the system (time control, reminders, logging, safe opening pattern) still provide some safety improvements compared to a normal pill box.

