#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive Music Player - Simplified Version
Displays song name, artist name, playback status and volume, with synchronized logging and OLED display.
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
import RPi.GPIO as GPIO
from PIL import Image, ImageDraw, ImageFont
import adafruit_rgb_display.st7789 as st7789

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
            # Reset GPIO to prevent conflicts
            try:
                GPIO.cleanup()
            except:
                pass
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
        
        # Initialize Pygame audio mixer
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        self.volume = 0.5
        pygame.mixer.music.set_volume(self.volume)  # Set initial volume to 50%
        # Music file list and playback status
        self.music_folder = "/home/pi/Interactive-Lab-Hub/Lab 4/music"
        self.music_files = []
        self.current_song_index = 0
        self.is_playing = False
        self.load_music_files()
        
        # Input debounce timing
        self.last_touch_time = 0
        self.touch_debounce = 2.0
        self.last_song_change = 0
        self.last_volume_change = 0
        self.song_change_delay = 5.0
        self.volume_change_delay = 2.0
        
        print("Initialization complete")
        # Update display once after initialization is complete
        self.update_display()
    
    def load_music_files(self):
        """Load music file list"""
        if not os.path.exists(self.music_folder):
            print(f"Music folder not found: {self.music_folder}")
            return
        files = glob.glob(os.path.join(self.music_folder, "*.mp3")) + \
                glob.glob(os.path.join(self.music_folder, "*.wav"))
        self.music_files = files
        if not self.music_files:
            print("No music files found")
            # If directory is empty, use placeholder song name list
            self.music_files = ["song1.wav", "song2.wav", "song3.wav"]
        else:
            print(f"Found {len(self.music_files)} files.")
    
    def get_current_song_name(self):
        """Get current song name (without extension)"""
        if not self.music_files:
            return "No music"
        filename = os.path.basename(self.music_files[self.current_song_index])
        name = os.path.splitext(filename)[0]
        # If filename format is "song_-_artist", split song name
        if "_-_" in name:
            return name.split("_-_", 1)[0].strip()
        return name
    
    def get_current_artist_name(self):
        """Get current artist name"""
        if not self.music_files:
            return "Unknown"
        filename = os.path.basename(self.music_files[self.current_song_index])
        name = os.path.splitext(filename)[0]
        if "_-_" in name:
            return name.split("_-_", 1)[1].strip()
        return "Unknown"
    
    def update_display(self):
        """Synchronously update log output and OLED display content"""
        # Get current playback status and volume
        current_playing = pygame.mixer.music.get_busy()
        current_volume = pygame.mixer.music.get_volume()
        song_name = self.get_current_song_name()
        artist_name = self.get_current_artist_name()
        # Truncate overly long song names and artist names (max 16 characters)
        if len(song_name) > 16:
            song_name = song_name[:13] + "..."
        display_artist = artist_name
        if len(display_artist) > 16:
            display_artist = display_artist[:13] + "..."
        # Determine status text and volume text
        status_text = "Playing" if current_playing else "Paused"
        volume_text = f"Vol: {int(current_volume * 100)}%"
        # Log current status
        print(f"Song: {song_name}")
        print(f"Artist: {display_artist}")
        print(f"Status: {status_text}")
        print(volume_text)
        print("-" * 20)
        # OLED screen displays current status
        if self.disp:
            try:
                image = Image.new("RGB", (self.width, self.height))
                draw = ImageDraw.Draw(image)
                draw.rectangle((0, 0, self.width, self.height), fill=(0, 0, 0))
                y = 5
                draw.text((5, y), song_name, font=self.font, fill="#FFFFFF"); y += 25
                draw.text((5, y), display_artist, font=self.small_font, fill="#CCCCCC"); y += 20
                # Use colors to distinguish playback status: green for playing, red for paused
                color = "#00FF00" if current_playing else "#FF0000"
                draw.text((5, y), status_text, font=self.small_font, fill=color); y += 20
                draw.text((5, y), volume_text, font=self.small_font, fill="#FFFF00")
                self.disp.image(image, self.rotation)
            except Exception as e:
                print(f"Display update error: {e}")
    
    def play_music(self):
        """Play song at current index"""
        if not self.music_files:
            return
        file = self.music_files[self.current_song_index]
        if not os.path.exists(file):
            print(f"File not found: {file}")
            return
        try:
            pygame.mixer.music.load(file)
            pygame.mixer.music.set_volume(self.volume)  # Reset volume after loading
            pygame.mixer.music.play()
            self.is_playing = True
            print(f"Playing: {os.path.basename(file)}")
            time.sleep(0.1)  # Wait for playback to start
            self.update_display()
        except Exception as e:
            print(f"Play error: {e}")
    
    def stop_music(self):
        """Stop playback"""
        pygame.mixer.music.stop()
        self.is_playing = False
        print("Music stopped")
        time.sleep(0.1)
        self.update_display()
    
    def pause_music(self):
        """Pause or resume playback"""
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            print("Music paused")
        else:
            pygame.mixer.music.unpause()
            self.is_playing = True
            print("Music resumed")
        time.sleep(0.1)
        self.update_display()
    
    def next_song(self):
        """Switch to next song"""
        if not self.music_files:
            return
        self.current_song_index = (self.current_song_index + 1) % len(self.music_files)
        print(f"Next song: {self.get_current_song_name()}")
        if self.is_playing:
            # If currently playing, stop current song and play next
            self.stop_music()
            time.sleep(0.1)
            self.play_music()
        else:
            # When not playing, only update display (no auto-play)
            self.update_display()
    
    def previous_song(self):
        """Switch to previous song"""
        if not self.music_files:
            return
        self.current_song_index = (self.current_song_index - 1) % len(self.music_files)
        print(f"Previous song: {self.get_current_song_name()}")
        if self.is_playing:
            self.stop_music()
            time.sleep(0.1)
            self.play_music()
        else:
            self.update_display()
    
    def adjust_volume(self, up):
        """Adjust volume: up=True increase volume, False decrease volume"""
        if up:
            self.volume = min(1.0, self.volume + 0.05)
        else:
            self.volume = max(0.0, self.volume - 0.05)
        pygame.mixer.music.set_volume(self.volume)
        print(f"Volume: {int(self.volume * 100)}%")
        time.sleep(0.1)
        self.update_display()
    
    def check_twizzler_touch(self):
        """Check touch button input (Twizzler)"""
        if not self.mpr121:
            return False
        now = time.time()
        # Touch sensor pin 0 is touched
        if self.mpr121[0].value and now - self.last_touch_time > self.touch_debounce:
            print("Twizzler touch: toggle play/pause")
            self.pause_music()  # Toggle play/pause
            self.last_touch_time = now
            return True
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
            self.adjust_volume(True)
            self.last_volume_change = now
        if down and now - self.last_volume_change > self.volume_change_delay:
            print("Joystick down -> volume down")
            self.adjust_volume(False)
            self.last_volume_change = now
    
    def run(self):
        """Main loop to run player"""
        print("Entering main loop. Ctrl+C to exit.")
        try:
            while True:
                # Check touch buttons and joystick, process input promptly in each loop
                self.check_twizzler_touch()
                self.check_joystick_input()
                # If current song finishes, automatically switch to next
                if self.is_playing and not pygame.mixer.music.get_busy():
                    print("Song finished, moving to next")
                    self.next_song()
                time.sleep(0.1)  # Small delay to avoid high CPU usage
        except KeyboardInterrupt:
            # Catch Ctrl+C for safe exit
            print("Shutting down...")
            self.stop_music()
            pygame.mixer.quit()
            GPIO.cleanup()

def main():
    player = InteractiveMusicPlayer()
    player.run()

if __name__ == "__main__":
    main()
