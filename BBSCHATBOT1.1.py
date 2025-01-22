import tkinter as tk
from tkinter import ttk
import threading
import asyncio
import telnetlib3
import time
import queue
import re
import requests
import openai
import json
import os

###############################################################################
# Default/placeholder API keys (updated in Settings window as needed).
###############################################################################
DEFAULT_OPENAI_API_KEY = ""
DEFAULT_WEATHER_API_KEY = ""
DEFAULT_YOUTUBE_API_KEY = ""
DEFAULT_GOOGLE_CSE_KEY = ""  # Google Custom Search API Key
DEFAULT_GOOGLE_CSE_CX = ""   # Google Custom Search Engine ID (cx)
DEFAULT_NEWS_API_KEY = ""  # NewsAPI Key
DEFAULT_GOOGLE_PLACES_API_KEY = ""  # Google Places API Key

class BBSBotApp:
    def __init__(self, master):
        self.master = master
        self.master.title("BBS Chatbot - Full-line for !search, 250-limit for !chat")

        # ----------------- Configurable variables ------------------
        self.host = tk.StringVar(value="bbs.example.com")
        self.port = tk.IntVar(value=23)
        self.openai_api_key = tk.StringVar(value=DEFAULT_OPENAI_API_KEY)
        self.weather_api_key = tk.StringVar(value=DEFAULT_WEATHER_API_KEY)
        self.youtube_api_key = tk.StringVar(value=DEFAULT_YOUTUBE_API_KEY)
        self.google_cse_api_key = tk.StringVar(value=DEFAULT_GOOGLE_CSE_KEY)
        self.google_cse_cx = tk.StringVar(value=DEFAULT_GOOGLE_CSE_CX)
        self.news_api_key = tk.StringVar(value=DEFAULT_NEWS_API_KEY)
        self.google_places_api_key = tk.StringVar(value=DEFAULT_GOOGLE_PLACES_API_KEY)
        self.nickname = tk.StringVar(value=self.load_nickname())
        self.username = tk.StringVar(value=self.load_username())
        self.password = tk.StringVar(value=self.load_password())
        self.remember_username = tk.BooleanVar(value=False)
        self.remember_password = tk.BooleanVar(value=False)
        self.in_teleconference = False  # Flag to track teleconference state
        self.mud_mode = tk.BooleanVar(value=False)

        # For best ANSI alignment, recommend a CP437-friendly monospace font:
        self.font_name = tk.StringVar(value="Courier New") 
        self.font_size = tk.IntVar(value=10)

        # Terminal mode (ANSI only)
        self.terminal_mode = tk.StringVar(value="ANSI")

        # Telnet references
        self.reader = None
        self.writer = None
        self.stop_event = threading.Event()  # signals background thread to stop
        self.connected = False

        # A queue to pass data from telnet thread => main thread
        self.msg_queue = queue.Queue()

        # A buffer to accumulate partial lines
        self.partial_line = ""

        self.favorites = self.load_favorites()  # Load favorite BBS addresses
        self.favorites_window = None  # Track the Favorites window instance

        # Build UI
        self.build_ui()

        # Periodically check for incoming messages
        self.master.after(100, self.process_incoming_messages)

        self.keep_alive_stop_event = threading.Event()
        self.keep_alive_task = None
        self.loop = asyncio.new_event_loop()  # Initialize loop attribute
        asyncio.set_event_loop(self.loop)  # Set the event loop

    
        
    def build_ui(self):
        """Set up frames, text areas, input boxes, etc."""
        main_frame = ttk.Frame(self.master)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ----- Config frame -----
        config_frame = ttk.LabelFrame(main_frame, text="Connection Settings")
        config_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(config_frame, text="BBS Host:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(config_frame, textvariable=self.host, width=30).grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)

        ttk.Label(config_frame, text="Port:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(config_frame, textvariable=self.port, width=6).grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)

        self.connect_button = ttk.Button(config_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.grid(row=0, column=4, padx=5, pady=5)

        # Add a "Settings" button
        settings_button = ttk.Button(config_frame, text="Settings", command=self.show_settings_window)
        settings_button.grid(row=0, column=5, padx=5, pady=5)

        # Add a "Favorites" button
        favorites_button = ttk.Button(config_frame, text="Favorites", command=self.show_favorites_window)
        favorites_button.grid(row=0, column=6, padx=5, pady=5)

        # Add a "Mud Mode" checkbox
        mud_mode_check = ttk.Checkbutton(config_frame, text="Mud Mode", variable=self.mud_mode)
        mud_mode_check.grid(row=0, column=7, padx=5, pady=5)

        # ----- Username frame -----
        username_frame = ttk.LabelFrame(main_frame, text="Username")
        username_frame.pack(fill=tk.X, padx=5, pady=5)

        self.username_entry = ttk.Entry(username_frame, textvariable=self.username, width=30)
        self.username_entry.pack(side=tk.LEFT, padx=5, pady=5)

        self.remember_username_check = ttk.Checkbutton(username_frame, text="Remember", variable=self.remember_username)
        self.remember_username_check.pack(side=tk.LEFT, padx=5, pady=5)

        self.send_username_button = ttk.Button(username_frame, text="Send", command=self.send_username)
        self.send_username_button.pack(side=tk.LEFT, padx=5, pady=5)

        # ----- Password frame -----
        password_frame = ttk.LabelFrame(main_frame, text="Password")
        password_frame.pack(fill=tk.X, padx=5, pady=5)

        self.password_entry = ttk.Entry(password_frame, textvariable=self.password, width=30, show="*")
        self.password_entry.pack(side=tk.LEFT, padx=5, pady=5)

        self.remember_password_check = ttk.Checkbutton(password_frame, text="Remember", variable=self.remember_password)
        self.remember_password_check.pack(side=tk.LEFT, padx=5, pady=5)

        self.send_password_button = ttk.Button(password_frame, text="Send", command=self.send_password)
        self.send_password_button.pack(side=tk.LEFT, padx=5, pady=5)

        # ----- Terminal output -----
        terminal_frame = ttk.LabelFrame(main_frame, text="BBS Output")
        terminal_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.terminal_display = tk.Text(
            terminal_frame,
            wrap=tk.WORD,
            height=15,
            state=tk.NORMAL,
            bg="black"
        )
        self.terminal_display.configure(state=tk.DISABLED)
        self.terminal_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll_bar = ttk.Scrollbar(terminal_frame, command=self.terminal_display.yview)
        scroll_bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.terminal_display.configure(yscrollcommand=scroll_bar.set)

        self.define_ansi_tags()

        # ----- Input frame -----
        input_frame = ttk.LabelFrame(main_frame, text="Send Message")
        input_frame.pack(fill=tk.X, padx=5, pady=5)

        self.input_var = tk.StringVar()
        self.input_box = ttk.Entry(input_frame, textvariable=self.input_var, width=80)
        self.input_box.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.input_box.bind("<Return>", self.send_message)

        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Set initial font
        self.update_display_font()

    def show_settings_window(self):
        """Open a Toplevel with fields for API keys, font settings, etc."""
        settings_win = tk.Toplevel(self.master)
        settings_win.title("Settings")

        row_index = 0

        # ----- OpenAI API Key -----
        ttk.Label(settings_win, text="OpenAI API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.openai_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- Weather API Key -----
        ttk.Label(settings_win, text="Weather API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.weather_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- YouTube API Key -----
        ttk.Label(settings_win, text="YouTube API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.youtube_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- Google CSE Key -----
        ttk.Label(settings_win, text="Google CSE API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.google_cse_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- Google CSE ID (cx) -----
        ttk.Label(settings_win, text="Google CSE ID (cx):").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.google_cse_cx, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- News API Key -----
        ttk.Label(settings_win, text="News API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.news_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- Google Places API Key -----
        ttk.Label(settings_win, text="Google Places API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.google_places_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
        row_index += 1

        # ----- Font Name -----
        ttk.Label(settings_win, text="Font Name:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        font_options = ["Courier New", "Px437 IBM VGA8", "Terminus (TTF)", "Consolas", "Lucida Console"]
        font_dropdown = ttk.Combobox(settings_win, textvariable=self.font_name, values=font_options, state="readonly")
        font_dropdown.grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # ----- Font Size -----
        ttk.Label(settings_win, text="Font Size:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.font_size, width=5).grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # Info label about recommended fonts
        info_label = ttk.Label(
            settings_win,
            text=(
                "Tip: For best ANSI alignment, install a CP437-compatible\n"
                "monospace font like 'Px437 IBM VGA8' or 'Terminus (TTF)'.\n"
                "Then select its name from the Font Name dropdown."
            )
        )
        info_label.grid(row=row_index, column=0, columnspan=2, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # Add Mud Mode checkbox
        ttk.Label(settings_win, text="Mud Mode:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Checkbutton(settings_win, variable=self.mud_mode).grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # ----- Save Button -----
        save_button = ttk.Button(settings_win, text="Save", command=lambda: self.save_settings(settings_win))
        save_button.grid(row=row_index, column=0, columnspan=2, pady=10)

    def save_settings(self, window):
        """Called when user clicks 'Save' in the settings window."""
        self.update_display_font()
        openai.api_key = self.openai_api_key.get()
        window.destroy()

    def update_display_font(self):
        """Update the Text widget's font based on self.font_name and self.font_size."""
        new_font = (self.font_name.get(), self.font_size.get())
        self.terminal_display.configure(font=new_font)

    def define_ansi_tags(self):
        """Define text tags for basic ANSI foreground colors (30-37, 90-97)."""
        self.terminal_display.tag_configure("normal", foreground="white")

        color_map = {
            '30': 'black',
            '31': 'red',
            '32': 'green',
            '33': 'yellow',
            '34': 'blue',
            '35': 'magenta',
            '36': 'cyan',
            '37': 'white',
            '90': 'bright_black',
            '91': 'bright_red',
            '92': 'bright_green',
            '93': 'bright_yellow',
            '94': 'bright_blue',
            '95': 'bright_magenta',
            '96': 'bright_cyan',
            '97': 'bright_white'
        }
        for code, color_name in color_map.items():
            if color_name.startswith("bright_"):
                base_color = color_name.split("_", 1)[1]
                self.terminal_display.tag_configure(color_name, foreground=base_color)
            else:
                self.terminal_display.tag_configure(color_name, foreground=color_name)

    def toggle_connection(self):
        """Connect or disconnect from the BBS."""
        if self.connected:
            self.disconnect_from_bbs()
        else:
            self.start_connection()

    def connect_to_bbs(self, address):
        """Connect to the BBS with the given address."""
        self.host.set(address)
        self.start_connection()

    def start_connection(self):
        """Start the telnetlib3 client in a background thread."""
        host = self.host.get()
        port = self.port.get()
        self.stop_event.clear()

        def run_telnet():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.telnet_client_task(host, port))

        thread = threading.Thread(target=run_telnet, daemon=True)
        thread.start()
        self.append_terminal_text(f"Connecting to {host}:{port}...\n", "normal")
        self.start_keep_alive()  # Start keep-alive coroutine

    async def telnet_client_task(self, host, port):
        """Async function connecting via telnetlib3 (CP437 + ANSI), reading bigger chunks."""
        try:
            reader, writer = await telnetlib3.open_connection(
                host=host,
                port=port,
                term=self.terminal_mode.get().lower(),
                encoding='cp437',
            )
        except Exception as e:
            self.msg_queue.put_nowait(f"Connection failed: {e}\n")
            return

        self.reader = reader
        self.writer = writer
        self.connected = True
        self.connect_button.config(text="Disconnect")
        self.msg_queue.put_nowait(f"Connected to {host}:{port}\n")

        try:
            while not self.stop_event.is_set():
                data = await reader.read(4096)
                if not data:
                    break
                self.msg_queue.put_nowait(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.msg_queue.put_nowait(f"Error reading from server: {e}\n")

        self.disconnect_from_bbs()

    def disconnect_from_bbs(self):
        """Stop the background thread and close connections."""
        if not self.connected:
            return

        self.stop_event.set()
        self.stop_keep_alive()  # Stop keep-alive coroutine
        if self.writer:
            self.writer.close()

        time.sleep(0.1)
        self.connected = False
        self.reader = None
        self.writer = None
        try:
            if self.connect_button and self.connect_button.winfo_exists():
                self.connect_button.config(text="Connect")
        except tk.TclError:
            pass
        self.msg_queue.put_nowait("Disconnected from BBS.\n")

    def process_incoming_messages(self):
        """Check the queue for data, parse lines, schedule next check."""
        try:
            while True:
                data = self.msg_queue.get_nowait()
                self.process_data_chunk(data)
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self.process_incoming_messages)

    def process_data_chunk(self, data):
        """
        Accumulate data in self.partial_line.
        Split on newline, parse triggers for complete lines.
        """
        self.partial_line += data
        lines = self.partial_line.split("\n")
        for line in lines[:-1]:
            # Display each complete line
            self.append_terminal_text(line + "\n", "normal")
            self.parse_incoming_triggers(line)  # Ensure triggers are parsed

        # The last piece may be partial if no trailing newline
        self.partial_line = lines[-1]

    def parse_incoming_triggers(self, line):
        """
        Check for commands in the given line: !weather, !yt, !search, !chat, !news, !map, !help
        """
        # Remove ANSI codes for easier parsing
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')
        clean_line = ansi_escape_regex.sub('', line)

        # Check if the message is private
        private_message_match = re.match(r'From (.+?) \(whispered\): (.+)', clean_line)
        if private_message_match:
            username = private_message_match.group(1)
            message = private_message_match.group(2)
            self.handle_private_trigger(username, message)
        else:
            # Check for page commands
            page_message_match = re.match(r'(.+?) is paging you from (.+?): (.+)', clean_line)
            if page_message_match:
                username = page_message_match.group(1)
                module_or_channel = page_message_match.group(2)
                message = page_message_match.group(3)
                self.handle_page_trigger(username, module_or_channel, message)
            else:
                # Check for trigger commands in public messages
                if "!weather" in clean_line:
                    location = clean_line.split("!weather", 1)[1].strip()
                    self.handle_weather_command(location)
                elif "!yt" in clean_line:
                    query = clean_line.split("!yt", 1)[1].strip()
                    self.handle_youtube_command(query)
                elif "!search" in clean_line:
                    query = clean_line.split("!search", 1)[1].strip()
                    self.handle_web_search_command(query)
                elif "!chat" in clean_line:
                    query = clean_line.split("!chat", 1)[1].strip()
                    self.handle_chatgpt_command(query)
                elif "!news" in clean_line:
                    topic = clean_line.split("!news", 1)[1].strip()
                    self.handle_news_command(topic)
                elif "!map" in clean_line:
                    place = clean_line.split("!map", 1)[1].strip()
                    self.handle_map_command(place)
                elif "!help" in clean_line:
                    self.handle_help_command()

    def handle_private_trigger(self, username, message):
        """
        Handle private message triggers and respond privately.
        """
        if "!weather" in message:
            location = message.split("!weather", 1)[1].strip()
            response = self.get_weather_response(location)
        elif "!yt" in message:
            query = message.split("!yt", 1)[1].strip()
            response = self.get_youtube_response(query)
        elif "!search" in message:
            query = message.split("!search", 1)[1].strip()
            response = self.get_web_search_response(query)
        elif "!chat" in message:
            query = message.split("!chat", 1)[1].strip()
            response = self.get_chatgpt_response(query)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            response = "Unknown command."

        self.send_private_message(username, response)

    def send_private_message(self, username, message):
        """
        Send a private message to the specified user.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f"Whisper to {username} {chunk}"
            asyncio.run_coroutine_threadsafe(self._send_message(full_message + "\r\n"), self.loop)
            self.append_terminal_text(full_message + "\n", "normal")

    def handle_page_trigger(self, username, module_or_channel, message):
        """
        Handle page message triggers and respond accordingly.
        """
        if "!weather" in message:
            location = message.split("!weather", 1)[1].strip()
            response = self.get_weather_response(location)
        elif "!yt" in message:
            query = message.split("!yt", 1)[1].strip()
            response = self.get_youtube_response(query)
        elif "!search" in message:
            query = message.split("!search", 1)[1].strip()
            response = self.get_web_search_response(query)
        elif "!chat" in message:
            query = message.split("!chat", 1)[1].strip()
            response = self.get_chatgpt_response(query)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            response = "Unknown command."

        self.send_page_response(username, module_or_channel, response)

    def send_page_response(self, username, module_or_channel, message):
        """
        Send a page response to the specified user and module/channel.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f"/P {username} {chunk}"
            asyncio.run_coroutine_threadsafe(self._send_message(full_message + "\r\n"), self.loop)
            self.append_terminal_text(full_message + "\n", "normal")

    def get_weather_response(self, location):
        """Fetch weather info and return the response as a string."""
        key = self.weather_api_key.get()
        if not key:
            return "Weather API key is missing."
        elif not location:
            return "Please specify a city or zip code."
        else:
            url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": key,
                "units": "imperial"
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                if data.get("cod") != 200:
                    return f"Could not get weather for '{location}'."
                else:
                    desc = data["weather"][0]["description"]
                    temp_f = data["main"]["temp"]
                    feels_like = data["main"]["feels_like"]
                    humidity = data["main"]["humidity"]
                    wind_speed = data["wind"]["speed"]
                    precipitation = data.get("rain", {}).get("1h", 0) + data.get("snow", {}).get("1h", 0)
                    
                    return (
                        f"Weather in {location.title()}: {desc}, {temp_f:.1f}°F "
                        f"(feels like {feels_like:.1f}°F), Humidity {humidity}%, Wind {wind_speed} mph, "
                        f"Precipitation {precipitation} mm."
                    )
            except requests.exceptions.RequestException as e:
                return f"Error fetching weather: {str(e)}"

    def get_youtube_response(self, query):
        """Perform a YouTube search and return the response as a string."""
        key = self.youtube_api_key.get()
        if not key:
            return "YouTube API key is missing."
        else:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": query,
                "key": key,
                "maxResults": 1
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                items = data.get("items", [])
                if not items:
                    return f"No YouTube results found for '{query}'."
                else:
                    video_id = items[0]["id"].get("videoId")
                    title = items[0]["snippet"]["title"]
                    url_link = f"https://www.youtube.com/watch?v={video_id}"
                    return f"Top YouTube result: {title}\n{url_link}"
            except Exception as e:
                return f"Error fetching YouTube results: {str(e)}"

    def get_web_search_response(self, query):
        """Perform a Google Custom Search and return the response as a string."""
        cse_key = self.google_cse_api_key.get()
        cse_id = self.google_cse_cx.get()
        if not cse_key or not cse_id:
            return "Google CSE API key or engine ID is missing."
        else:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": cse_key,
                "cx": cse_id,
                "q": query,
                "num": 1  # just one top result
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                items = data.get("items", [])
                if not items:
                    return f"No Google search results found for '{query}'."
                else:
                    top = items[0]
                    title = top.get("title", "No Title")
                    snippet = top.get("snippet", "")
                    link = top.get("link", "No Link")

                    return (
                        f"Top Google result for '{query}':\n"
                        f"Title: {title}\n"
                        f"Snippet: {snippet}\n"
                        f"Link: {link}"
                    )
            except Exception as e:
                return f"Error with Google search: {str(e)}"

    def get_chatgpt_response(self, user_text):
        """Send user_text to ChatGPT and return the response as a string."""
        key = self.openai_api_key.get()
        if not key:
            return "OpenAI API key is missing."

        openai.api_key = key

        system_message = (
            "You are a helpful assistant. Respond concisely, longer responses should split into "
            "250-character blocks for display, but don't exceed 500 total characters in your responses."
        )

        try:
            completion = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                n=1,
                max_tokens=500,  # Allow for longer responses
                messages=[
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user",
                        "content": user_text
                    }
                ]
            )
            return completion.choices[0].message["content"]

        except Exception as e:
            return f"Error with ChatGPT API: {str(e)}"

    def get_news_response(self, topic):
        """Fetch top 2 news headlines and return the response as a string."""
        key = self.news_api_key.get()
        if not key:
            return "News API key is missing."
        else:
            url = "https://newsapi.org/v2/everything"  # Using "everything" endpoint for broader topic search
            params = {
                "q": topic,  # The keyword/topic to search for
                "apiKey": key,
                "language": "en",
                "pageSize": 2  # Fetch top 2 headlines
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                articles = data.get("articles", [])
                if not articles:
                    return f"No news articles found for '{topic}'."
                else:
                    response = f"Top news on '{topic}':\n"
                    for i, article in enumerate(articles):
                        title = article.get("title", "No Title")
                        description = article.get("description", "No Description")
                        link = article.get("url", "No URL")
                        response += f"{i + 1}. {title}\n   {description}\n   {link}\n\n"
                    return response
            except Exception as e:
                return f"Error fetching news: {str(e)}"

    def get_map_response(self, place):
        """Fetch place info from Google Places API and return the response as a string."""
        key = self.google_places_api_key.get()
        if not key:
            return "Google Places API key is missing."
        elif not place:
            return "Please specify a place."
        else:
            url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.types,places.websiteUri"
            }
            data = {
                "textQuery": place
            }
            try:
                r = requests.post(url, headers=headers, json=data, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                places = data.get("places", [])
                if not places:
                    return f"Could not find place '{place}'."
                else:
                    place_info = places[0]
                    name = place_info.get("displayName", {}).get("text", "No Name")
                    address = place_info.get("formattedAddress", "No Address")
                    types = ", ".join(place_info.get("types", []))
                    website = place_info.get("websiteUri", "No Website")
                    return (
                        f"Place: {name}\n"
                        f"Address: {address}\n"
                        f"Types: {types}\n"
                        f"Website: {website}"
                    )
            except requests.exceptions.RequestException as e:
                return f"Error fetching place info: {str(e)}"

    def get_help_response(self):
        """Return the help message as a string."""
        return (
            "Available commands: Please use a ! immediately followed by one of the following keywords (no space): "
            "weather <location>, yt <query>, search <query>, chat <message>, news <topic>, map <place>."
        )

    def append_terminal_text(self, text, default_tag="normal"):
        """Append text to the terminal display with ANSI parsing."""
        self.terminal_display.configure(state=tk.NORMAL)
        self.parse_ansi_and_insert(text)
        self.terminal_display.see(tk.END)
        self.terminal_display.configure(state=tk.DISABLED)

    def parse_ansi_and_insert(self, text_data):
        """Minimal parser for ANSI color codes (foreground only)."""
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')

        last_end = 0
        current_tag = "normal"

        for match in ansi_escape_regex.finditer(text_data):
            start, end = match.span()
            # Insert text before this ANSI code with current tag
            if start > last_end:
                self.terminal_display.insert(tk.END, text_data[last_end:start], current_tag)

            code_string = match.group(1)
            codes = code_string.split(';')
            if '0' in codes:
                current_tag = "normal"
                codes.remove('0')

            for c in codes:
                mapped_tag = self.map_code_to_tag(c)
                if mapped_tag:
                    current_tag = mapped_tag

            last_end = end

        if last_end < len(text_data):
            self.terminal_display.insert(tk.END, text_data[last_end:], current_tag)

    def map_code_to_tag(self, color_code):
        """Map a numeric color code to a defined Tk text tag."""
        valid_codes = {
            '30': 'black',
            '31': 'red',
            '32': 'green',
            '33': 'yellow',
            '34': 'blue',
            '35': 'magenta',
            '36': 'cyan',
            '37': 'white',
            '90': 'bright_black',
            '91': 'bright_red',
            '92': 'bright_green',
            '93': 'bright_yellow',
            '94': 'bright_blue',
            '95': 'bright_magenta',
            '96': 'bright_cyan',
            '97': 'bright_white',
        }
        return valid_codes.get(color_code, None)

    def send_message(self, event=None):
        """Send the user's typed message to the BBS."""
        if not self.connected or not self.writer:
            self.append_terminal_text("Not connected to any BBS.\n", "normal")
            return

        user_input = self.input_var.get()
        self.input_var.set("")
        if user_input.strip():
            prefix = "Gos " if self.mud_mode.get() else ""
            message = prefix + user_input
            asyncio.run_coroutine_threadsafe(self._send_message(message + "\r\n"), self.loop)
            self.append_terminal_text(message + "\n", "normal")
            print(f"Sent to BBS: {message}")

    async def _send_message(self, message):
        """Coroutine to send a message."""
        self.writer.write(message)
        await self.writer.drain()

    def send_full_message(self, message):
        """Send a full message to the terminal display and the BBS server."""
        prefix = "Gos " if self.mud_mode.get() else ""
        lines = message.split('\n')
        full_message = prefix + '\n'.join(lines)
        chunks = self.chunk_message(full_message, 250)
        for chunk in chunks:
            self.append_terminal_text(chunk + "\n", "normal")
            if self.connected and self.writer:
                asyncio.run_coroutine_threadsafe(self._send_message(chunk + "\r\n"), self.loop)
                print(f"Sent to BBS: {chunk}")

    def chunk_message(self, message, chunk_size):
        """Chunk a message into specified size, ensuring no content is lost."""
        words = message.split()
        chunks = []
        current_chunk = []

        for word in words:
            if len(' '.join(current_chunk + [word])) <= chunk_size:
                current_chunk.append(word)
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def show_favorites_window(self):
        """Open a Toplevel window to manage favorite BBS addresses."""
        if self.favorites_window and self.favorites_window.winfo_exists():
            self.favorites_window.lift()
            return

        self.favorites_window = tk.Toplevel(self.master)
        self.favorites_window.title("Favorite BBS Addresses")

        row_index = 0

        # Listbox to display favorite addresses
        self.favorites_listbox = tk.Listbox(self.favorites_window, height=10, width=50)
        self.favorites_listbox.grid(row=row_index, column=0, columnspan=2, padx=5, pady=5)
        self.update_favorites_listbox()

        row_index += 1

        # Entry to add a new favorite address
        self.new_favorite_var = tk.StringVar()
        ttk.Entry(self.favorites_window, textvariable=self.new_favorite_var, width=40).grid(row=row_index, column=0, padx=5, pady=5)

        # Button to add the new favorite address
        add_button = ttk.Button(self.favorites_window, text="Add", command=self.add_favorite)
        add_button.grid(row=row_index, column=1, padx=5, pady=5)

        row_index += 1

        # Button to remove the selected favorite address
        remove_button = ttk.Button(self.favorites_window, text="Remove", command=self.remove_favorite)
        remove_button.grid(row=row_index, column=0, columnspan=2, pady=5)

        # Bind listbox selection to populate host field
        self.favorites_listbox.bind("<<ListboxSelect>>", self.populate_host_field)

    def update_favorites_listbox(self):
        """Update the Listbox with the current favorite addresses."""
        self.favorites_listbox.delete(0, tk.END)
        for address in self.favorites:
            self.favorites_listbox.insert(tk.END, address)

    def add_favorite(self):
        """Add a new favorite address."""
        new_address = self.new_favorite_var.get().strip()
        if new_address and new_address not in self.favorites:
            self.favorites.append(new_address)
            self.update_favorites_listbox()
            self.new_favorite_var.set("")
            self.save_favorites()

    def remove_favorite(self):
        """Remove the selected favorite address."""
        selected_index = self.favorites_listbox.curselection()
        if selected_index:
            address = self.favorites_listbox.get(selected_index)
            self.favorites.remove(address)
            self.update_favorites_listbox()
            self.save_favorites()

    def load_favorites(self):
        """Load favorite BBS addresses from a file."""
        if os.path.exists("favorites.json"):
            with open("favorites.json", "r") as file:
                return json.load(file)
        return []

    def save_favorites(self):
        """Save favorite BBS addresses to a file."""
        with open("favorites.json", "w") as file:
            json.dump(self.favorites, file)

    def populate_host_field(self, event):
        """Populate the host field with the selected favorite address."""
        selected_index = self.favorites_listbox.curselection()
        if selected_index:
            address = self.favorites_listbox.get(selected_index)
            self.host.set(address)

    def load_nickname(self):
        """Load nickname from a file."""
        if os.path.exists("nickname.json"):
            with open("nickname.json", "r") as file:
                return json.load(file)
        return ""

    def save_nickname(self):
        """Save nickname to a file."""
        with open("nickname.json", "w") as file:
            json.dump(self.nickname.get(), file)

    def send_username(self):
        """Send the username to the BBS."""
        if self.connected and self.writer:
            username = self.username.get()
            asyncio.run_coroutine_threadsafe(self._send_message(username + "\r\n"), self.loop)  # Append carriage return and newline
            if self.remember_username.get():
                self.save_username()

    def send_password(self):
        """Send the password to the BBS."""
        if self.connected and self.writer:
            password = self.password.get()
            asyncio.run_coroutine_threadsafe(self._send_message(password + "\r\n"), self.loop)  # Append carriage return and newline
            if self.remember_password.get():
                self.save_password()

    def load_username(self):
        """Load username from a file."""
        if os.path.exists("username.json"):
            with open("username.json", "r") as file:
                return json.load(file)
        return ""

    def save_username(self):
        """Save username to a file."""
        with open("username.json", "w") as file:
            json.dump(self.username.get(), file)

    def load_password(self):
        """Load password from a file."""
        if os.path.exists("password.json"):
            with open("password.json", "r") as file:
                return json.load(file)
        return ""

    def save_password(self):
        """Save password to a file."""
        with open("password.json", "w") as file:
            json.dump(self.password.get(), file)

    ########################################################################
    #                           Trigger Parsing
    ########################################################################
    def parse_incoming_triggers(self, line):
        """
        Check for commands in the given line: !weather, !yt, !search, !chat, !news, !help
        """
        # Remove ANSI codes for easier parsing
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')
        clean_line = ansi_escape_regex.sub('', line)

        # Check if the message is private
        private_message_match = re.match(r'From (.+?) \(whispered\): (.+)', clean_line)
        if private_message_match:
            username = private_message_match.group(1)
            message = private_message_match.group(2)
            self.handle_private_trigger(username, message)
        else:
            # Check for page commands
            page_message_match = re.match(r'(.+?) is paging you from (.+?): (.+)', clean_line)
            if page_message_match:
                username = page_message_match.group(1)
                module_or_channel = page_message_match.group(2)
                message = page_message_match.group(3)
                self.handle_page_trigger(username, module_or_channel, message)
            else:
                # Check for trigger commands in public messages
                if "!weather" in clean_line:
                    location = clean_line.split("!weather", 1)[1].strip()
                    self.handle_weather_command(location)
                elif "!yt" in clean_line:
                    query = clean_line.split("!yt", 1)[1].strip()
                    self.handle_youtube_command(query)
                elif "!search" in clean_line:
                    query = clean_line.split("!search", 1)[1].strip()
                    self.handle_web_search_command(query)
                elif "!chat" in clean_line:
                    query = clean_line.split("!chat", 1)[1].strip()
                    self.handle_chatgpt_command(query)
                elif "!news" in clean_line:
                    topic = clean_line.split("!news", 1)[1].strip()
                    self.handle_news_command(topic)
                elif "!map" in clean_line:
                    place = clean_line.split("!map", 1)[1].strip()
                    self.handle_map_command(place)
                elif "!help" in clean_line:
                    self.handle_help_command()

    def handle_private_trigger(self, username, message):
        """
        Handle private message triggers and respond privately.
        """
        if "!weather" in message:
            location = message.split("!weather", 1)[1].strip()
            response = self.get_weather_response(location)
        elif "!yt" in message:
            query = message.split("!yt", 1)[1].strip()
            response = self.get_youtube_response(query)
        elif "!search" in message:
            query = message.split("!search", 1)[1].strip()
            response = self.get_web_search_response(query)
        elif "!chat" in message:
            query = message.split("!chat", 1)[1].strip()
            response = self.get_chatgpt_response(query)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            response = "Unknown command."

        self.send_private_message(username, response)

    def send_private_message(self, username, message):
        """
        Send a private message to the specified user.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f"Whisper to {username} {chunk}"
            asyncio.run_coroutine_threadsafe(self._send_message(full_message + "\r\n"), self.loop)
            self.append_terminal_text(full_message + "\n", "normal")

    def handle_page_trigger(self, username, module_or_channel, message):
        """
        Handle page message triggers and respond accordingly.
        """
        if "!weather" in message:
            location = message.split("!weather", 1)[1].strip()
            response = self.get_weather_response(location)
        elif "!yt" in message:
            query = message.split("!yt", 1)[1].strip()
            response = self.get_youtube_response(query)
        elif "!search" in message:
            query = message.split("!search", 1)[1].strip()
            response = self.get_web_search_response(query)
        elif "!chat" in message:
            query = message.split("!chat", 1)[1].strip()
            response = self.get_chatgpt_response(query)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            response = "Unknown command."

        self.send_page_response(username, module_or_channel, response)

    def send_page_response(self, username, module_or_channel, message):
        """
        Send a page response to the specified user and module/channel.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f"/P {username} {chunk}"
            asyncio.run_coroutine_threadsafe(self._send_message(full_message + "\r\n"), self.loop)
            self.append_terminal_text(full_message + "\n", "normal")

    ########################################################################
    #                           Help
    ########################################################################
    def handle_help_command(self):
        """Provide a list of available commands, adhering to character and chunk limits."""
        help_message = (
            "Available commands: Please use a ! immediately followed by one of the following keywords (no space): "
            "weather <location>, yt <query>, search <query>, chat <message>, news <topic>, map <place>."
        )

        # Send the help message as a single chunk if possible
        self.send_full_message(help_message)

    ########################################################################
    #                           Weather
    ########################################################################
    def handle_weather_command(self, location):
        """Fetch weather info in Fahrenheit with details (unlimited length)."""
        key = self.weather_api_key.get()
        if not key:
            response = "Weather API key is missing."
        elif not location:
            response = "Please specify a city or zip code."
        else:
            url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": key,
                "units": "imperial"
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                if data.get("cod") != 200:
                    response = f"Could not get weather for '{location}'."
                else:
                    desc = data["weather"][0]["description"]
                    temp_f = data["main"]["temp"]
                    feels_like = data["main"]["feels_like"]
                    humidity = data["main"]["humidity"]
                    wind_speed = data["wind"]["speed"]
                    precipitation = data.get("rain", {}).get("1h", 0) + data.get("snow", {}).get("1h", 0)
                    
                    response = (
                        f"Weather in {location.title()}: {desc}, {temp_f:.1f}°F "
                        f"(feels like {feels_like:.1f}°F), Humidity {humidity}%, Wind {wind_speed} mph, "
                        f"Precipitation {precipitation} mm."
                    )
            except requests.exceptions.RequestException as e:
                response = f"Error fetching weather: {str(e)}"

        self.send_full_message(response)

    ########################################################################
    #                           YouTube
    ########################################################################
    def handle_youtube_command(self, query):
        """Perform a YouTube search for the given query (unlimited length)."""
        key = self.youtube_api_key.get()
        if not key:
            response = "YouTube API key is missing."
        else:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "q": query,
                "key": key,
                "maxResults": 1
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                items = data.get("items", [])
                if not items:
                    response = f"No YouTube results found for '{query}'."
                else:
                    video_id = items[0]["id"].get("videoId")
                    title = items[0]["snippet"]["title"]
                    url_link = f"https://www.youtube.com/watch?v={video_id}"
                    response = f"Top YouTube result: {title}\n{url_link}"
            except Exception as e:
                response = f"Error fetching YouTube results: {str(e)}"

        self.send_full_message(response)

    ########################################################################
    #                           Google Custom Search (with Link)
    ########################################################################
    def handle_web_search_command(self, query):
        """
        Perform a Google Custom Search (unlimited length) for better link display.
        """
        cse_key = self.google_cse_api_key.get()
        cse_id = self.google_cse_cx.get()
        if not cse_key or not cse_id:
            response = "Google CSE API key or engine ID is missing."
        else:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": cse_key,
                "cx": cse_id,
                "q": query,
                "num": 1  # just one top result
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                items = data.get("items", [])
                if not items:
                    response = f"No Google search results found for '{query}'."
                else:
                    top = items[0]
                    title = top.get("title", "No Title")
                    snippet = top.get("snippet", "")
                    link = top.get("link", "No Link")

                    response = (
                        f"Top Google result for '{query}':\n"
                        f"Title: {title}\n"
                        f"Snippet: {snippet}\n"
                        f"Link: {link}"
                    )
            except Exception as e:
                response = f"Error with Google search: {str(e)}"

        self.send_full_message(response)

    ########################################################################
    #                           ChatGPT
    ########################################################################
    def handle_chatgpt_command(self, user_text):
        """
        Send user_text to ChatGPT and handle responses.
        The response can be longer than 200 characters but will be split into blocks.
        """
        key = self.openai_api_key.get()
        if not key:
            gpt_response = "OpenAI API key is missing."
            self.send_full_message(gpt_response)
            return

        openai.api_key = key

        system_message = (
            "You are a helpful assistant. Respond concisely, longer responses should split into "
            "200-character blocks for display, but don't exceed 500 total characters in your responses."
        )

        try:
            completion = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                n=1,
                max_tokens=500,  # Allow for longer responses
                messages=[
                    {
                        "role": "system",
                        "content": system_message
                    },
                    {
                        "role": "user",
                        "content": user_text
                    }
                ]
            )
            gpt_response = completion.choices[0].message["content"]

        except Exception as e:
            gpt_response = f"Error with ChatGPT API: {str(e)}"

        # Send the full response to be chunked and transmitted
        self.send_full_message(gpt_response)

    ########################################################################
    #                           News
    ########################################################################
    def handle_news_command(self, topic):
        """Fetch top 2 news headlines based on the given topic."""
        key = self.news_api_key.get()
        if not key:
            response = "News API key is missing."
        else:
            url = "https://newsapi.org/v2/everything"  # Using "everything" endpoint for broader topic search
            params = {
                "q": topic,  # The keyword/topic to search for
                "apiKey": key,
                "language": "en",
                "pageSize": 2  # Fetch top 2 headlines
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                articles = data.get("articles", [])
                if not articles:
                    response = f"No news articles found for '{topic}'."
                else:
                    response = f"Top news on '{topic}':\n"
                    for i, article in enumerate(articles):
                        title = article.get("title", "No Title")
                        description = article.get("description", "No Description")
                        link = article.get("url", "No URL")
                        response += f"{i + 1}. {title}\n   {description}\n   {link}\n\n"
            except Exception as e:
                response = f"Error fetching news: {str(e)}"

        self.send_full_message(response)

    ########################################################################
    #                           Map
    ########################################################################
    def handle_map_command(self, place):
        """Fetch place info from Google Places API and return the response as a string."""
        key = self.google_places_api_key.get()
        if not key:
            response = "Google Places API key is missing."
        elif not place:
            response = "Please specify a place."
        else:
            url = "https://places.googleapis.com/v1/places:searchText"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key,
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.types,places.websiteUri"
            }
            data = {
                "textQuery": place
            }
            try:
                r = requests.post(url, headers=headers, json=data, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                places = data.get("places", [])
                if not places:
                    response = f"Could not find place '{place}'."
                else:
                    place_info = places[0]
                    name = place_info.get("displayName", {}).get("text", "No Name")
                    address = place_info.get("formattedAddress", "No Address")
                    types = ", ".join(place_info.get("types", []))
                    website = place_info.get("websiteUri", "No Website")
                    response = (
                        f"Place: {name}\n"
                        f"Address: {address}\n"
                        f"Types: {types}\n"
                        f"Website: {website}"
                    )
            except requests.exceptions.RequestException as e:
                response = f"Error fetching place info: {str(e)}"

        self.send_full_message(response)

    ########################################################################
    #                           Keep Alive
    ########################################################################
    async def keep_alive(self):
        """Send an <ENTER> keystroke every 1 minute to keep the connection alive."""
        while not self.keep_alive_stop_event.is_set():
            if self.connected and self.writer:
                self.writer.write("\r\n")
                await self.writer.drain()
            await asyncio.sleep(60)

    def start_keep_alive(self):
        """Start the keep-alive coroutine."""
        self.keep_alive_stop_event.clear()
        if self.loop:
            self.keep_alive_task = self.loop.create_task(self.keep_alive())

    def stop_keep_alive(self):
        """Stop the keep-alive coroutine."""
        self.keep_alive_stop_event.set()
        if self.keep_alive_task:
            self.keep_alive_task.cancel()

def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
        root = tk.Tk()
        app = BBSBotApp(root)
        root.mainloop()
    except KeyboardInterrupt:
        print("Script interrupted by user. Exiting...")
    finally:
        if app.connected:
            app.disconnect_from_bbs()
        try:
            if root.winfo_exists():
                root.quit()
        except tk.TclError:
            pass

if __name__ == "__main__":
    main()
