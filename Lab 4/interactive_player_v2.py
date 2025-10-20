#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive Music Player - Simplified Version
Basic music player with joystick, touch sensor, proximity sensor, and display.
"""
import time
import os
import glob
import pygame
from pathlib import Path

# Hardware control library imports
import board
import busio
import digitalio
import adafruit_mpr121
import lgpio
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789
from adafruit_apds9960.apds9960 import APDS9960
# Note: Qwiic Joystick uses its own library (SparkFun Qwiic Joystick)
try:
    import qwiic_joystick  # ensure this library is installed
except ImportError:
    qwiic_joystick = None

class InteractiveMusicPlayer:
    def __init__(self):
        # Initialize touch sensor (Twizzler button)
        try:
            self.i2c = busio.I2C(board.SCL, board.SDA)
            self.mpr121 = adafruit_mpr121.MPR121(self.i2c)
            print("MPR121 touch sensor initialized successfully")
        except Exception as e:
            print(f"MPR121 initialization failed: {e}")
            self.i2c = None
            self.mpr121 = None
        
        # Initialize ST7789 color display
        try:
            print("Initializing ST7789 display...")
            # Stop services that might occupy SPI bus (like Bluetooth)
            try:
                import subprocess
                subprocess.run(["sudo", "systemctl", "stop", "bluetooth"], capture_output=True)
                subprocess.run(["sudo", "systemctl", "stop", "hciuart"], capture_output=True)
            except:
                pass
            # GPIO will be initialized later
            time.sleep(1)
            # First try configuration with RST pin
            try:
                cs_pin = digitalio.DigitalInOut(board.D5)
                dc_pin = digitalio.DigitalInOut(board.D25)
                reset_pin = digitalio.DigitalInOut(board.D24)  # Use GPIO24 as RST
                BAUDRATE = 32000000  # 32MHz baud rate
                spi = board.SPI()
                self.disp = st7789.ST7789(
                    spi, cs=cs_pin, dc=dc_pin, rst=reset_pin,
                    baudrate=BAUDRATE, width=135, height=240,
                    x_offset=53, y_offset=40
                )
            except Exception as pin_error:
                print(f"Primary ST7789 config failed: {pin_error}")
                # If failed, try without RST pin and reduce baud rate
                cs_pin = digitalio.DigitalInOut(board.D5)
                dc_pin = digitalio.DigitalInOut(board.D25)
                reset_pin = None
                BAUDRATE = 16000000  # Reduce to 16MHz baud rate
                spi = board.SPI()
                self.disp = st7789.ST7789(
                    spi, cs=cs_pin, dc=dc_pin, rst=reset_pin,
                    baudrate=BAUDRATE, width=135, height=240,
                    x_offset=53, y_offset=40
                )
            # Set display parameters
            self.height = self.disp.width   # Swap width/height for screen rotation
            self.width = self.disp.height
            self.image = Image.new("RGB", (self.width, self.height))
            self.rotation = 90
            self.draw = ImageDraw.Draw(self.image)
            # Load fonts
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
            self.small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            # Turn on backlight
            self.backlight = digitalio.DigitalInOut(board.D22)
            self.backlight.switch_to_output()
            self.backlight.value = True
            print("ST7789 display initialized")
            # Initial screen prompt
            self.draw.rectangle((0, 0, self.width, self.height), fill=(0, 0, 0))
            self.draw.text((5, 5), "Music Player", font=self.font, fill="#FFFFFF")
            self.draw.text((5, 30), "Initializing...", font=self.small_font, fill="#CCCCCC")
            self.disp.image(self.image, self.rotation)
            time.sleep(0.5)  # Briefly show initialization status
        except Exception as e:
            print(f"ST7789 display initialization failed: {e}")
            self.disp = None
        
        # Initialize joystick (Qwiic Joystick)
        try:
            import qwiic_joystick
            self.joystick = qwiic_joystick.QwiicJoystick()
            if not self.joystick.connected:
                print("Qwiic Joystick not connected")
                self.joystick = None
                self.joystick_left_pin = None
                self.use_qwiic_joystick = False
            else:
                self.joystick.begin()
                self.joystick_left_pin = "qwiic"  # Mark using Qwiic interface
                self.use_qwiic_joystick = True
                print("Qwiic Joystick initialized")
        except Exception as e:
            print(f"Joystick initialization failed: {e}")
            self.joystick = None
            self.joystick_left_pin = None
            self.use_qwiic_joystick = False
        
        # Initialize proximity sensor (APDS9960)
        try:
            self.apds = APDS9960(self.i2c)
            self.apds.enable_proximity = True
            print("APDS9960 proximity sensor initialized successfully")
        except Exception as e:
            print(f"APDS9960 proximity sensor initialization failed: {e}")
            self.apds = None
        
        # Initialize GPIO output pins for signal control
        try:
            self.chip = lgpio.gpiochip_open(0)  # Open GPIO chip
            self.output_pins = [18, 19, 20]  # GPIO18, GPIO19, GPIO20 (safe for lights)
            for pin in self.output_pins:
                lgpio.gpio_claim_output(self.chip, pin, 0)  # Start with all pins LOW
            print("GPIO output pins initialized: 18, 19, 20 - All set to LOW (OFF)")
        except Exception as e:
            print(f"GPIO output pins initialization failed: {e}")
            self.chip = None
            self.output_pins = None
        
        # Initialize Pygame mixer for audio playback
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self.volume = 0.5
            pygame.mixer.music.set_volume(self.volume)  # set initial volume to 50%
            print("Audio system initialized successfully")
        except Exception as e:
            print(f"Audio system initialization failed: {e}")
            print("Continuing without audio...")
            self.volume = 0.5
        # Load music file list
        self.music_folder = "/home/pi/Interactive-Lab-Hub/Lab 4/music"
        self.music_files = []
        self.current_song_index = 0
        self.is_playing = False
        self.load_music_files()
        
        # Input debounce timing variables
        self.last_touch_time = 0
        self.touch_debounce = 2.0  # 2 seconds debounce for touch
        self.last_song_change = 0
        self.last_volume_change = 0
        self.song_change_delay = 5.0   # 5 seconds debounce for song skip
        self.volume_change_delay = 2.0  # 2 seconds debounce for volume
        
        # Joystick debug
        self.debug_joystick = True
        self.joystick_debug_count = 0
        self.joystick_enabled = True
        
        # GPIO output control variables
        self.light_pattern_index = 0
        self.last_light_update = 0
        self.light_update_interval = 0.5  # update outputs every 0.5 sec (like test program)
        self.current_light_state = False  # track output state for patterns
        
        # Light status logging
        self.light_log_enabled = True
        self.last_light_log_time = 0
        self.light_log_interval = 1.0  # log every 1 second
        
        print("Initialization complete. Entering main loop...")
        self.update_display()  # show initial status on display
    
    def load_music_files(self):
        """Load music files from the designated folder."""
        if not os.path.exists(self.music_folder):
            print(f"Music folder not found: {self.music_folder}")
            return
        files = glob.glob(os.path.join(self.music_folder, "*.mp3")) + \
                glob.glob(os.path.join(self.music_folder, "*.wav"))
        self.music_files = files
        if not self.music_files:
            print("No music files found in folder; using placeholder names.")
            # Placeholder list if no files found
            self.music_files = ["song1.wav", "song2.wav", "song3.wav"]
        else:
            print(f"Found {len(self.music_files)} audio files.")
    
    def get_current_song_name(self):
        """Get current song name (filename without extension)."""
        if not self.music_files:
            return "No music"
        filename = os.path.basename(self.music_files[self.current_song_index])
        name = os.path.splitext(filename)[0]
        # If filename formatted as "SongName_-_Artist", split out the song part
        if "_-_" in name:
            return name.split("_-_", 1)[0].strip()
        return name
    
    def get_current_artist_name(self):
        """Get current artist name from filename."""
        if not self.music_files:
            return "Unknown"
        filename = os.path.basename(self.music_files[self.current_song_index])
        name = os.path.splitext(filename)[0]
        if "_-_" in name:
            return name.split("_-_", 1)[1].strip()
        return "Unknown"
    
    def update_display(self):
        """Update the OLED display and console log with current status."""
        # Gather current playback status and volume
        try:
            is_playing_now = pygame.mixer.music.get_busy()
            current_volume = pygame.mixer.music.get_volume()
        except:
            # If audio system not available, use internal state
            is_playing_now = self.is_playing
            current_volume = self.volume
        song_name = self.get_current_song_name()
        artist_name = self.get_current_artist_name()
        # Truncate names if too long for display
        if len(song_name) > 16:
            song_name = song_name[:13] + "..."
        display_artist = artist_name
        if len(display_artist) > 16:
            display_artist = display_artist[:13] + "..."
        # Prepare status and volume text
        status_text = "Playing" if is_playing_now else "Paused"
        volume_text = f"Vol: {int(current_volume * 100)}%"
        # Log to console
        print(f"Song: {song_name}")
        print(f"Artist: {display_artist}")
        print(f"Status: {status_text}")
        print(volume_text)
        print("-" * 20)
        # Update OLED display if available
        if self.disp:
            try:
                image = Image.new("RGB", (self.width, self.height))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, self.width, self.height), fill=(0, 0, 0))
                y = 5
                draw.text((5, y), song_name, font=self.font, fill="#FFFFFF"); y += 25
                draw.text((5, y), display_artist, font=self.small_font, fill="#CCCCCC"); y += 20
                # Color status: green if playing, red if paused
                status_color = "#00FF00" if is_playing_now else "#FF0000"
                draw.text((5, y), status_text, font=self.small_font, fill=status_color); y += 20
                draw.text((5, y), volume_text, font=self.small_font, fill="#FFFF00")
                self.disp.image(image, self.rotation)
            except Exception as e:
                print(f"Display update error: {e}")
    
    def play_music(self):
        """Load and play the current song (by index)."""
        if not self.music_files:
            return
        file_path = self.music_files[self.current_song_index]
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.set_volume(self.volume)  # ensure volume setting persists
            pygame.mixer.music.play()
            self.is_playing = True
            print(f"Playing: {os.path.basename(file_path)}")
            print("LIGHTS: Music started - lights will begin flashing")
            # Reset light timing to start immediately
            self.last_light_update = 0
            time.sleep(0.1)  # small delay to allow playback to start
            self.update_display()
        except Exception as e:
            print(f"Error playing file '{file_path}': {e}")
    
    def stop_music(self):
        """Stop playback completely."""
        pygame.mixer.music.stop()
        self.is_playing = False
        print("Music stopped.")
        print("LIGHTS: Music stopped - turning off all lights")
        # Turn off all GPIO outputs when music stops
        self.turn_off_all_outputs()
        time.sleep(0.1)
        self.update_display()
    
    def pause_music(self):
        """Toggle pause/resume on the music."""
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            print("Music paused.")
            print("LIGHTS: Music paused - turning off all lights")
            # Turn off all GPIO outputs when music is paused
            self.turn_off_all_outputs()
        else:
            pygame.mixer.music.unpause()
            self.is_playing = True
            print("Music resumed.")
            print("LIGHTS: Music resumed - lights will begin flashing")
            # Reset light timing to start immediately
            self.last_light_update = 0
        time.sleep(0.1)
        self.update_display()
    
    def next_song(self):
        """Advance to the next song in the list."""
        if not self.music_files:
            return
        self.current_song_index = (self.current_song_index + 1) % len(self.music_files)
        print(f"Next song selected: {self.get_current_song_name()}")
        if self.is_playing:
            # If music was playing, stop current and immediately play next
            self.stop_music()
            time.sleep(0.1)
            self.play_music()
        else:
            # If music was paused/stopped, just update the display to show new selection
            self.update_display()
    
    def previous_song(self):
        """Go back to the previous song in the list."""
        if not self.music_files:
            return
        self.current_song_index = (self.current_song_index - 1) % len(self.music_files)
        print(f"Previous song selected: {self.get_current_song_name()}")
        if self.is_playing:
            self.stop_music()
            time.sleep(0.1)
            self.play_music()
        else:
            self.update_display()
    
    def adjust_volume(self, increase=True):
        """Adjust volume up or down by a step."""
        if increase:
            self.volume = min(1.0, self.volume + 0.05)
        else:
            self.volume = max(0.0, self.volume - 0.05)
        pygame.mixer.music.set_volume(self.volume)
        print(f"Volume set to {int(self.volume * 100)}%")
        time.sleep(0.1)
        self.update_display()
    
    def get_proximity_reading(self):
        """Read the proximity level from APDS9960 sensor."""
        if not self.apds:
            return 0
        try:
            # Read proximity value from APDS9960 (0-255, higher = closer)
            proximity_value = self.apds.proximity
            # Return 1 if proximity is above threshold (close), 0 if far
            return 1 if proximity_value > 50 else 0
        except Exception as e:
            print(f"Proximity read error: {e}")
            return 0
    
    
    def turn_off_all_outputs(self):
        """Turn off all GPIO output pins."""
        if not self.output_pins or not self.chip:
            return
        try:
            for pin in self.output_pins:
                lgpio.gpio_write(self.chip, pin, 0)
            print("All GPIO outputs turned OFF (LOW)")  # Debug output
        except Exception as e:
            print(f"GPIO output error: {e}")
    
    def output_pattern_alternating(self):
        """Output pattern: one pin HIGH at a time in rotation."""
        if not self.output_pins or not self.chip:
            return
        try:
            # Turn off all first
            for pin in self.output_pins:
                lgpio.gpio_write(self.chip, pin, 0)
            # Turn on the current index pin
            lgpio.gpio_write(self.chip, self.output_pins[self.light_pattern_index], 1)
            print(f"Alternating pattern: GPIO{self.output_pins[self.light_pattern_index]} ON")  # Debug output
            # Advance to next pin for next cycle
            self.light_pattern_index = (self.light_pattern_index + 1) % len(self.output_pins)
        except Exception as e:
            print(f"Alternating pattern error: {e}")
    
    def output_pattern_all_on(self):
        """Output pattern: all pins HIGH."""
        if not self.output_pins or not self.chip:
            return
        try:
            for pin in self.output_pins:
                lgpio.gpio_write(self.chip, pin, 1)
        except Exception as e:
            print(f"All on pattern error: {e}")
    
    def output_pattern_all_off(self):
        """Output pattern: all pins LOW."""
        if not self.output_pins:
            return
        try:
            self.turn_off_all_outputs()
        except Exception as e:
            print(f"All off pattern error: {e}")
    
    def output_pattern_flash_all(self):
        """Output pattern: all pins flash together (toggle state)."""
        if not self.output_pins or not self.chip:
            return
        try:
            # Toggle the stored output state for continuous flashing
            self.current_light_state = not self.current_light_state
            for i in range(len(self.output_pins)):
                lgpio.gpio_write(self.chip, self.output_pins[i], 1 if self.current_light_state else 0)
            print(f"Flash all pattern: {'ON' if self.current_light_state else 'OFF'}")  # Debug output
        except Exception as e:
            print(f"Flash all pattern error: {e}")
    
    def log_light_status(self):
        """Log current light status periodically."""
        if not self.light_log_enabled:
            return
        now = time.time()
        
        # Log every second
        if now - self.last_light_log_time >= self.light_log_interval:
            if self.output_pins and self.chip:
                # Read actual GPIO states
                try:
                    pin_states = []
                    for pin in self.output_pins:
                        state = lgpio.gpio_read(self.chip, pin)
                        pin_states.append(f"GPIO{pin}:{'ON' if state else 'OFF'}")
                    pin_status = " | ".join(pin_states)
                except Exception as e:
                    pin_status = f"GPIO read error: {e}"
            else:
                pin_status = "GPIO not available (initialization failed)"
            
            music_status = "PLAYING" if self.is_playing else "STOPPED"
            light_state = "ON" if self.current_light_state else "OFF"
            
            print(f"LIGHT_LOG: Music={music_status} | LightState={light_state} | {pin_status}")
            self.last_light_log_time = now
    
    def update_outputs(self):
        """Update GPIO output pattern based on music playback."""
        now = time.time()
        
        # If GPIO not available, just log status
        if not self.output_pins or not self.chip:
            self.log_light_status()
            return
        
        # If music isn't playing, turn off all outputs immediately
        if not self.is_playing:
            # Only turn off if not already off to avoid spam
            if self.current_light_state:
                self.turn_off_all_outputs()
                self.current_light_state = False
                print("LIGHTS: Music not playing - all lights OFF")
            return
        
        # Music is playing – decide pattern based on proximity
        if now - self.last_light_update >= self.light_update_interval:
            proximity = self.get_proximity_reading()
            print(f"Proximity reading: {proximity}")  # Debug output
            
            if proximity:
                # If proximity detected: alternate pins rapidly
                print("Proximity detected - using alternating pattern")
                self.output_pattern_alternating()
            else:
                # No proximity: all pins flash together
                print("No proximity - using flash all pattern")
                self.output_pattern_flash_all()
            
            self.last_light_update = now
        
        # Log light status
        self.log_light_status()
    
    
    
    def check_twizzler_touch(self):
        """Check touch button input (Twizzler)"""
        if not self.mpr121:
            return False
        now = time.time()
        try:
            if self.mpr121[0].value and (now - self.last_touch_time > self.touch_debounce):
                print("Twizzler touched: toggling play/pause")
                self.pause_music()  # Toggle play/pause
                self.last_touch_time = now
                return True
        except Exception as e:
            # In case of I2C error or sensor not ready
            print(f"MPR121 read error: {e}")
        return False
    
    def check_joystick_input(self):
        """Check joystick input"""
        if self.joystick_left_pin is None:
            return
        now = time.time()
        # Use Qwiic joystick analog values to determine direction
        if self.use_qwiic_joystick:
            x = self.joystick.horizontal
            y = self.joystick.vertical
            button = self.joystick.button
            # When X or Y deviates from center beyond threshold, consider as valid input
            # Based on joystick_test.py output, center values are X: 524, Y: 514
            threshold = 200
            left = (x < 524 - threshold)
            right = (x > 524 + threshold)
            up = (y < 514 - threshold)
            down = (y > 514 + threshold)
            
            # Debug output: show joystick values and detection status
            if left or right or up or down or button == 0:
                print(f"Joystick: X={x}, Y={y}, Button={button}, L={left}, R={right}, U={up}, D={down}")
            if button == 0 and now - self.last_touch_time > self.touch_debounce:
                print("Joystick button: toggle play/pause")
                self.pause_music()
                self.last_touch_time = now
        else:
            # Other types of joysticks (not implemented)
            left = right = up = down = False
        # Execute corresponding operations based on directional input (with debounce delay)
        if left and now - self.last_song_change > self.song_change_delay:
            print("Joystick left -> previous song")
            self.previous_song()
            self.last_song_change = now
        if right and now - self.last_song_change > self.song_change_delay:
            print("Joystick right -> next song")
            self.next_song()
            self.last_song_change = now
        if up and now - self.last_volume_change > self.volume_change_delay:
            print("Joystick up -> volume up")
            self.adjust_volume(increase=True)
            self.last_volume_change = now
        if down and now - self.last_volume_change > self.volume_change_delay:
            print("Joystick down -> volume down")
            self.adjust_volume(increase=False)
            self.last_volume_change = now
    
    def run(self):
        """Main loop to handle inputs and playback continuously."""
        print("Entering main loop. Press Ctrl+C to exit.")
        try:
            while True:
                # Check inputs
                self.check_twizzler_touch()
                self.check_joystick_input()
                # Update GPIO outputs based on music & proximity
                self.update_outputs()
                # Auto-advance to next song if the current song finished
                if self.is_playing and not pygame.mixer.music.get_busy():
                    print("Song finished. Advancing to next track...")
                    self.next_song()
                time.sleep(0.1)  # loop delay to reduce CPU usage
        except KeyboardInterrupt:
            # Graceful shutdown on Ctrl+C
            print("Shutting down gracefully...")
            self.stop_music()
            # Turn off all GPIO outputs
            self.turn_off_all_outputs()
            pygame.mixer.quit()
            if self.chip:
                lgpio.gpiochip_close(self.chip)

# Run the music player if this script is executed directly
if __name__ == "__main__":
    player = InteractiveMusicPlayer()
    player.run()
