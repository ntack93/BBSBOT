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
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from pytube import YouTube
from pydub import AudioSegment
import subprocess

###############################################################################
# Default/placeholder API keys (updated in Settings window as needed).
###############################################################################
DEFAULT_OPENAI_API_KEY = ""
DEFAULT_WEATHER_API_KEY = ""
DEFAULT_YOUTUBE_API_KEY = ""
DEFAULT_GOOGLE_CSE_KEY = ""  # Google Custom Search API Key
DEFAULT_GOOGLE_CSE_CX = ""   # Google Custom Search Engine ID (cx)
DEFAULT_NEWS_API_KEY = ""    # NewsAPI Key
DEFAULT_GOOGLE_PLACES_API_KEY = ""  # Google Places API Key

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table_name = 'ChatBotConversations'
table = dynamodb.Table(table_name)

class BBSBotApp:
    def __init__(self, master):
        self.master = master
        self.master.title("BBS Chatbot Jeremy")

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
        self.pexels_api_key = tk.StringVar(value="")  # Add Pexels API Key
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

        self.chat_members = set()  # Set to keep track of chat members
        self.last_seen = {}  # Dictionary to store the last seen timestamp of each user

        # Build UI
        self.build_ui()

        # Periodically check for incoming messages
        self.master.after(100, self.process_incoming_messages)

        self.keep_alive_stop_event = threading.Event()
        self.keep_alive_task = None
        self.loop = asyncio.new_event_loop()  # Initialize loop attribute
        asyncio.set_event_loop(self.loop)  # Set the event loop

        self.dynamodb_client = boto3.client('dynamodb', region_name='us-east-1')
        self.table_name = table_name
        self.create_dynamodb_table()
        self.previous_line = ""  # Store the previous line to detect multi-line triggers
        self.user_list_buffer = []  # Buffer to accumulate user list lines
        self.timers = {}  # Dictionary to store active timers
        self.auto_greeting_enabled = True  # Attribute to track auto-greeting state

    def create_dynamodb_table(self):
        """Create DynamoDB table if it doesn't exist."""
        try:
            self.dynamodb_client.describe_table(TableName=self.table_name)
        except self.dynamodb_client.exceptions.ResourceNotFoundException:
            self.dynamodb_client.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {'AttributeName': 'username', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'username', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            self.dynamodb_client.get_waiter('table_exists').wait(TableName=self.table_name)

    def save_conversation(self, username, message, response):
        """Save conversation to DynamoDB."""
        timestamp = int(time.time())
        # Ensure the response is split into chunks of 250 characters
        response_chunks = self.chunk_message(response, 250)
        for chunk in response_chunks:
            table.put_item(
                Item={
                    'username': username,
                    'timestamp': timestamp,
                    'message': message,
                    'response': chunk
                }
            )
            # Update the timestamp for each chunk to maintain order
            timestamp += 1

    def get_conversation_history(self, username):
        """Retrieve conversation history from DynamoDB."""
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('username').eq(username)
        )
        items = response.get('Items', [])
        # Combine response chunks into full responses
        conversation_history = []
        current_response = ""
        for item in items:
            current_response += item['response']
            if len(current_response) >= 250:
                conversation_history.append({
                    'message': item['message'],
                    'response': current_response
                })
                current_response = ""
        if current_response:
            conversation_history.append({
                'message': items[-1]['message'],
                'response': current_response
            })
        return conversation_history

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

        # ----- Pexels API Key -----
        ttk.Label(settings_win, text="Pexels API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Entry(settings_win, textvariable=self.pexels_api_key, width=40).grid(row=row_index, column=1, padx=5, pady=5)
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
            asyncio.run_coroutine_threadsafe(self.disconnect_from_bbs(), self.loop).result()
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
        finally:
            await self.disconnect_from_bbs()

    async def disconnect_from_bbs(self):
        """Stop the background thread and close connections."""
        if not self.connected:
            return

        self.stop_event.set()
        self.stop_keep_alive()  # Stop keep-alive coroutine
        if self.writer:
            try:
                if hasattr(self.writer, 'is_closing') and not self.writer.is_closing():
                    self.writer.close()
                    await self.writer.drain()  # Ensure all data is sent before closing
            except Exception as e:
                print(f"Error closing writer: {e}")
        else:
            print("Writer is already None")

        time.sleep(0.1)
        self.connected = False
        self.reader = None
        self.writer = None

        def update_connect_button():
            try:
                if self.connect_button and self.connect_button.winfo_exists():
                    self.connect_button.config(text="Connect")
            except tk.TclError:
                pass

        # Schedule the update_connect_button call from the main thread
        if threading.current_thread() is threading.main_thread():
            update_connect_button()
        else:
            self.master.after_idle(update_connect_button)
        self.msg_queue.put_nowait("Disconnected from BBS.\n")

    def process_incoming_messages(self):
        """Check the queue for data, parse lines, schedule next check."""
        try:
            while True:
                data = self.msg_queue.get_nowait()
                print(f"Incoming message: {data}")  # Log incoming messages
                self.process_data_chunk(data)
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self.process_incoming_messages)

    def process_data_chunk(self, data):
        """
        Accumulate data in self.partial_line.
        Unify carriage returns, split on newline, parse triggers for complete lines.
        """
        # Replace all \r\n with \n, then replace remaining \r with \n.
        data = data.replace('\r\n', '\n').replace('\r', '\n')

        # Accumulate into partial_line
        self.partial_line += data

        # Split on \n to get complete lines
        lines = self.partial_line.split("\n")

        # Process all but the last entry; that last might be incomplete
        for line in lines[:-1]:
            self.append_terminal_text(line + "\n", "normal")
            print(f"Incoming line: {line}")  # Log each incoming line
            self.parse_incoming_triggers(line)

            # If line contains '@', it might be part of the user list
            if "@" in line:
                self.user_list_buffer.append(line)

            # If line ends with "are here with you." or "is here with you.", parse the entire buffer
            if re.search(r'(is|are) here with you\.$', line.strip()):
                if line not in self.user_list_buffer:
                    self.user_list_buffer.append(line)
                self.update_chat_members(self.user_list_buffer)
                self.user_list_buffer = []

            # Check for user joining message
            if line.strip() == ":***":
                self.previous_line = ":***"
            elif self.previous_line == ":***" and re.match(r'(.+?) just joined this channel!', line.strip()):
                username = re.match(r'(.+?) just joined this channel!', line.strip()).group(1)
                self.handle_user_greeting(username)
                self.previous_line = ""

        # The last piece may be partial if no trailing newline
        self.partial_line = lines[-1]

    def update_chat_members(self, lines_with_users):
        """
        lines_with_users: list of lines that contain '@', culminating in 'are here with you.'
        We'll combine them all, remove ANSI codes, then parse out the user@host addresses and usernames.
        """
        combined = " ".join(lines_with_users)  # join with space
        print(f"[DEBUG] Combined user lines: {combined}")  # Debug statement

        # Remove ANSI codes
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')
        combined_clean = ansi_escape_regex.sub('', combined)
        print(f"[DEBUG] Cleaned combined user lines: {combined_clean}")  # Debug statement

        # Refine regex to capture usernames and addresses
        addresses = re.findall(r'\b\S+@\S+\.\S+\b', combined_clean)
        print(f"[DEBUG] Regex match result: {addresses}")  # Debug statement

        # Extract usernames from addresses
        usernames = [address.split('@')[0] for address in addresses]

        # Handle the case where the last user is listed without an email address
        last_user_match = re.search(r'and (\S+) are here with you\.', combined_clean)
        if last_user_match:
            usernames.append(last_user_match.group(1))

        print(f"[DEBUG] Extracted usernames: {usernames}")  # Debug statement

        # Make them a set to avoid duplicates
        self.chat_members = set(usernames)
        self.save_chat_members()  # Save updated chat members to DynamoDB

        # Update last seen timestamps
        current_time = int(time.time())
        for member in self.chat_members:
            self.last_seen[member.lower()] = current_time

        print(f"[DEBUG] Updated chat members: {self.chat_members}")

    def save_chat_members(self):
        """Save chat members to DynamoDB."""
        chat_members_table = dynamodb.Table('ChatRoomMembers')
        try:
            chat_members_table.put_item(
                Item={
                    'room': 'default',
                    'members': list(self.chat_members)
                }
            )
            print(f"[DEBUG] Saved chat members to DynamoDB: {self.chat_members}")
        except Exception as e:
            print(f"Error saving chat members to DynamoDB: {e}")

    def get_chat_members(self):
        """Retrieve chat members from DynamoDB."""
        chat_members_table = dynamodb.Table('ChatRoomMembers')
        try:
            response = chat_members_table.get_item(Key={'room': 'default'})
            members = response.get('Item', {}).get('members', [])
            print(f"[DEBUG] Retrieved chat members from DynamoDB: {members}")
            return members
        except Exception as e:
            print(f"Error retrieving chat members from DynamoDB: {e}")
            return []

    def parse_incoming_triggers(self, line):
        """
        Check for commands in the given line: !weather, !yt, !search, !chat, !news, !map, !pic, !polly, !mp3yt, !help, !seen, !greeting
        And now also capture public messages for conversation history.
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
            return

        # Check for page commands
        page_message_match = re.match(r'(.+?) is paging you from (.+?): (.+)', clean_line)
        if page_message_match:
            username = page_message_match.group(1)
            module_or_channel = page_message_match.group(2)
            message = page_message_match.group(3)
            self.handle_page_trigger(username, module_or_channel, message)
            return

        # Check for direct messages
        direct_message_match = re.match(r'From (.+?) \(to you\): (.+)', clean_line)
        if direct_message_match:
            username = direct_message_match.group(1)
            message = direct_message_match.group(2)
            self.handle_direct_message(username, message)
            return

        # Check for public messages
        public_message_match = re.match(r'From (.+?): (.+)', clean_line)
        if public_message_match:
            username = public_message_match.group(1).strip()
            message = public_message_match.group(2).strip()

            # If the message includes "!chat", let's process it like any other chat trigger
            if "!chat" in message:
                query = message.split("!chat", 1)[1].strip()
                self.handle_chatgpt_command(query, username=username)
                return

        # Check for user-specific triggers
        if self.previous_line == ":***" and clean_line.startswith("->"):
            entrance_message = clean_line[3:].strip()
            self.handle_user_greeting(entrance_message)
        elif re.match(r'(.+?) just joined this channel!', clean_line):
            username = re.match(r'(.+?) just joined this channel!', clean_line).group(1)
            self.handle_user_greeting(username)
        elif re.match(r'(.+?)@(.+?) just joined this channel!', clean_line):
            username = re.match(r'(.+?)@(.+?) just joined this channel!', clean_line).group(1)
            self.handle_user_greeting(username)
        elif re.match(r'Topic: \(.*?\)\.\s*(.*?)\s*are here with you\.', clean_line, re.DOTALL):
            self.update_chat_members(clean_line)
        # Check for trigger commands in public messages
        elif "!weather" in clean_line:
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
            # Extract the username from the line
            username_match = re.match(r'From (.+?):', clean_line)
            username = username_match.group(1) if username_match else "public_chat"
            self.handle_chatgpt_command(query, username=username)
        elif "!news" in clean_line:
            topic = clean_line.split("!news", 1)[1].strip()
            self.handle_news_command(topic)
        elif "!map" in clean_line:
            place = clean_line.split("!map", 1)[1].strip()
            self.handle_map_command(place)
        elif "!pic" in clean_line:
            query = clean_line.split("!pic", 1)[1].strip()
            self.handle_pic_command(query)
        elif "!polly" in clean_line:
            parts = clean_line.split("!polly", 1)[1].strip().split(maxsplit=1)
            if len(parts) == 2:
                voice, text = parts
                self.handle_polly_command(voice, text)
            else:
                self.send_full_message("Please choose a Polly voice and provide text to convert. The voices are: Matthew, Stephen, Ruth, Joanna, Danielle.")
        elif "!mp3yt" in clean_line:
            url = clean_line.split("!mp3yt", 1)[1].strip()
            self.handle_ytmp3_command(url)
        elif "!timer" in clean_line:
            parts = clean_line.split("!timer", 1)[1].strip().split()
            if len(parts) == 3:
                label, value, unit = parts
                self.handle_timer_command(label, value, unit, username)
        elif "!help" in clean_line:
            self.handle_help_command()
        elif "!seen" in clean_line:
            target_username = clean_line.split("!seen", 1)[1].strip()
            self.handle_seen_command(target_username)
        elif "!greeting" in clean_line:
            self.handle_greeting_command()

        # Update the previous line
        self.previous_line = clean_line

    def send_enter_keystroke(self):
        """Send an <ENTER> keystroke to get the list of current chat members."""
        if self.connected and self.writer:
            asyncio.run_coroutine_threadsafe(self._send_message("\r\n"), self.loop)

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
            response = self.get_chatgpt_response(query, username=username)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!pic" in message:
            query = message.split("!pic", 1)[1].strip()
            response = self.get_pic_response(query)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            # Assume it's a message for the !chat trigger
            response = self.get_chatgpt_response(message, username=username)

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
            response = self.get_chatgpt_response(query, username=username)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!pic" in message:
            query = message.split("!pic", 1)[1].strip()
            response = self.get_pic_response(query)
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

    def handle_direct_message(self, username, message):
        """
        Handle direct messages and interpret them as !chat queries.
        """
        self.refresh_membership()  # Refresh membership before generating response
        time.sleep(1)  # Allow time for membership list to be updated
        self.master.update()  # Process any pending updates

        # Fetch the latest chat members from DynamoDB
        self.chat_members = set(self.get_chat_members())
        print(f"[DEBUG] Updated chat members list before generating response: {self.chat_members}")

        if "who's here" in message.lower() or "who is here" in message.lower():
            query = "who else is in the chat room?"
            response = self.get_chatgpt_response(query, direct=True, username=username)
        else:
            response = self.get_chatgpt_response(message, direct=True, username=username)

        self.send_direct_message(username, response)

    def send_direct_message(self, username, message):
        """
        Send a direct message to the specified user.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f">{username} {chunk}"
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

    def get_chatgpt_response(self, user_text, direct=False, username=None):
        """Send user_text to ChatGPT and return the response as a string."""
        key = self.openai_api_key.get()
        if not key:
            return "OpenAI API key is missing."

        openai.api_key = key

        # Fetch the latest chat members from DynamoDB
        self.chat_members = set(self.get_chat_members())
        members = list(self.chat_members)
        print(f"[DEBUG] Members list used for ChatGPT response: {members}")

        # Turn user@domain into just the username portion if you want:
        chatroom_usernames = []
        for member in members:
            name_part = member.split('@')[0]
            chatroom_usernames.append(name_part)

        # Create a simple comma-separated string for the system prompt
        chatroom_members_str = ", ".join(chatroom_usernames)
        print(f"[DEBUG] Chatroom members string for ChatGPT: {chatroom_members_str}")

        system_message = (
            "Your name is Jeremy. You speak very casually. When you greet people, you usually say things like 'Hey :)', 'What's up?', 'How's it going?', or just wave (wave <user>). "
            "You are just a laidback guy, hanging out in the chatroom. "
            "If a user says #flirtmodeon, you are to engage a mode to respond to queries with a very raunchy, flirty tone. When the user says #flirtmodeoff, it disables. "
            "If a user says '#tedmodeon', you are to respond as Ted from the Bill and Ted movies, while still having the knowledge and ability of a powerful A.I. "
            "#tedmodeoff toggles you back to a friendly A.I. assistant who's sitting in a chatroom. Maintain your toggle state relative to each user. "
            "Respond concisely, longer responses should split into 250-character blocks for display, but don't exceed 500 total characters in your responses. "
            "If asked about who's in the room, reference the current chatroom members list. "
            f"The current chatroom members are: {chatroom_members_str}."
        )

        if direct:
            system_message = (
                "Your name is Jeremy. You speak very casually. When you greet people, you usually say things like 'Hey :)', 'What's up?', 'How's it going?', or just wave (wave <user>). "
                "You are just a laidback guy, hanging out in the chatroom. "
                "If a user says #flirtmodeon, you are to respond to queries with a very raunchy, flirty tone. When the user says #flirtmodeoff, it disables. "
                "If a user says '#tedmodeon', you are to respond as Ted from the Bill and Ted movies, while still having the knowledge and ability of a powerful A.I. "
                "#tedmodeoff toggles you back to a friendly A.I. assistant who's sitting in a chatroom. Maintain your toggle state relative to each user. "
                "Respond concisely, and ensure your response is 230 characters or fewer. "
                "If asked about who's in the room, reference the current chatroom members list. "
                f"The current chatroom members are: {chatroom_members_str}."
            )

        # Optionally load conversation history from DynamoDB
        if username:
            conversation_history = self.get_conversation_history(username)
        else:
            conversation_history = self.get_conversation_history("public_chat")

        messages = [
            {"role": "system", "content": system_message}
        ]
        # Then append user messages and assistant replies from the DB ...
        for item in conversation_history:
            messages.append({"role": "user", "content": item['message']})
            messages.append({"role": "assistant", "content": item['response']})

        # (Optional) add a mini fact about who is speaking:
        if username:
            messages.append({"role": "system", "content": f"Reminder: The user speaking is named {username}."})

        # Finally append this new user_text
        messages.append({"role": "user", "content": user_text})

        print(f"[DEBUG] Chunks sent to ChatGPT: {messages}")  # Log chunks sent to ChatGPT

        try:
            completion = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                n=1,
                max_tokens=500 if not direct else 230,
                temperature=0.5,
                messages=messages
            )
            gpt_response = completion.choices[0].message["content"]

            if username:
                self.save_conversation(username, user_text, gpt_response)
            else:
                self.save_conversation("public_chat", user_text, gpt_response)

        except Exception as e:
            gpt_response = f"Error with ChatGPT API: {str(e)}"

        print(f"[DEBUG] ChatGPT response: {gpt_response}")  # Log ChatGPT response
        return gpt_response

    def handle_chatgpt_command(self, user_text, username=None):
        """
        Send user_text to ChatGPT and handle responses.
        The response can be longer than 200 characters but will be split into blocks.
        """
        self.refresh_membership()  # Refresh membership before generating response
        time.sleep(1)  # Allow time for membership list to be updated
        self.master.update()  # Process any pending updates

        # Fetch the latest chat members from DynamoDB
        self.chat_members = set(self.get_chat_members())
        print(f"[DEBUG] Updated chat members list before generating response: {self.chat_members}")

        response = self.get_chatgpt_response(user_text, username=username)
        self.send_full_message(response)

        # Save the conversation for non-directed messages
        if username is None:
            username = "public_chat"
        self.save_conversation(username, user_text, response)

    def handle_news_command(self, topic):
        """Fetch top 2 news headlines based on the given topic."""
        response = self.get_news_response(topic)
        chunks = self.chunk_message(response, 250)
        for chunk in chunks:
            self.send_full_message(chunk)

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
                r = requests.post(url, json=data, headers=headers, timeout=10)
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
            "weather <location>, yt <query>, search <query>, chat <message>, news <topic>, map <place>, pic <query>, mp3yt <youtube link>."
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
                self.terminal_display.insert(tk.END, text_data[last_end:start].replace('& # 3 9 ;', "'"), current_tag)

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
            self.terminal_display.insert(tk.END, text_data[last_end:].replace('& # 3 9 ;', "'"), current_tag)

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
        """
        Send a full message to the terminal display and the BBS server.
        """
        prefix = "Gos " if self.mud_mode.get() else ""
        lines = message.split('\n')
        full_message = prefix + '\n'.join(lines)
        chunks = self.chunk_message(full_message, 250)  # Use the new chunk_message!

        for chunk in chunks:
            self.append_terminal_text(chunk + "\n", "normal")
            if self.connected and self.writer:
                asyncio.run_coroutine_threadsafe(self._send_message(chunk + "\r\n"), self.loop)
                time.sleep(0.1)  # Add a short delay to ensure messages are sent in sequence
                print(f"Sent to BBS: {chunk}")  # Log chunks sent to BBS

    def chunk_message(self, message, chunk_size):
        """
        Break a message into chunks, up to `chunk_size` characters each,
        ensuring no splits in the middle of words or lines.

        1. Split by newline to preserve paragraph boundaries.
        2. For each paragraph, break it into word-based lines
           that do not exceed chunk_size.
        """
        paragraphs = message.split('\n')
        final_chunks = []

        for para in paragraphs:
            # If paragraph is totally empty, keep it as a blank line
            if not para.strip():
                final_chunks.append('')
                continue

            words = para.split()
            current_line_words = []

            for word in words:
                if not current_line_words:
                    # Start a fresh line
                    current_line_words.append(word)
                else:
                    # Test if we can add " word" without exceeding chunk_size
                    test_line = ' '.join(current_line_words + [word])
                    if len(test_line) <= chunk_size:
                        current_line_words.append(word)
                    else:
                        # We have to finalize the current line
                        final_chunks.append(' '.join(current_line_words))
                        current_line_words = [word]

            # Any leftover words in current_line_words
            if current_line_words:
                final_chunks.append(' '.join(current_line_words))

        return final_chunks

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
                # Check for direct messages
                direct_message_match = re.match(r'From (.+?) \(to you\): (.+)', clean_line)
                if direct_message_match:
                    username = direct_message_match.group(1)
                    message = direct_message_match.group(2)
                    self.handle_direct_message(username, message)
                else:
                    # Check for user-specific triggers
                    if self.previous_line == ":***" and clean_line.startswith("->"):
                        entrance_message = clean_line[3:].strip()
                        self.handle_user_greeting(entrance_message)
                    elif re.match(r'(.+?) just joined this channel!', clean_line):
                        username = re.match(r'(.+?) just joined this channel!', clean_line).group(1)
                        self.handle_user_greeting(username)
                    elif re.match(r'(.+?)@(.+?) just joined this channel!', clean_line):
                        username = re.match(r'(.+?)@(.+?) just joined this channel!', clean_line).group(1)
                        self.handle_user_greeting(username)
                    elif re.match(r'Topic: \(.*?\)\.\s*(.*?)\s*are here with you\.', clean_line, re.DOTALL):
                        self.update_chat_members(clean_line)
                    # Check for trigger commands in public messages
                    elif "!weather" in clean_line:
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
                        # Extract the username from the line
                        username_match = re.match(r'From (.+?):', clean_line)
                        username = username_match.group(1) if username_match else "public_chat"
                        self.handle_chatgpt_command(query, username=username)
                    elif "!news" in clean_line:
                        topic = clean_line.split("!news", 1)[1].strip()
                        self.handle_news_command(topic)
                    elif "!map" in clean_line:
                        place = clean_line.split("!map", 1)[1].strip()
                        self.handle_map_command(place)
                    elif "!pic" in clean_line:
                        query = clean_line.split("!pic", 1)[1].strip()
                        self.handle_pic_command(query)
                    elif "!polly" in clean_line:
                        parts = clean_line.split("!polly", 1)[1].strip().split(maxsplit=1)
                        if len(parts) == 2:
                            voice, text = parts
                            self.handle_polly_command(voice, text)
                        else:
                            self.send_full_message("Please choose a Polly voice and provide text to convert. The voices are: Matthew, Stephen, Ruth, Joanna, Danielle.")
                    elif "!mp3yt" in clean_line:
                        url = clean_line.split("!mp3yt", 1)[1].strip()
                        self.handle_ytmp3_command(url)
                    elif "!timer" in clean_line:
                        parts = clean_line.split("!timer", 1)[1].strip().split()
                        if len(parts) == 3:
                            label, value, unit = parts
                            self.handle_timer_command(label, value, unit, username)
                    elif "!help" in clean_line:
                        self.handle_help_command()
                    elif "!seen" in clean_line:
                        target_username = clean_line.split("!seen", 1)[1].strip()
                        self.handle_seen_command(target_username)
                    elif "!greeting" in clean_line:
                        self.handle_greeting_command()

        # Update the previous line
        self.previous_line = clean_line

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
            response = self.get_chatgpt_response(query, username=username)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!pic" in message:
            query = message.split("!pic", 1)[1].strip()
            response = self.get_pic_response(query)
        elif "!help" in message:
            response = self.get_help_response()
        else:
            # Assume it's a message for the !chat trigger
            response = self.get_chatgpt_response(message, username=username)

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
            response = self.get_chatgpt_response(query, username=username)
        elif "!news" in message:
            topic = message.split("!news", 1)[1].strip()
            response = self.get_news_response(topic)
        elif "!map" in message:
            place = message.split("!map", 1)[1].strip()
            response = self.get_map_response(place)
        elif "!pic" in message:
            query = message.split("!pic", 1)[1].strip()
            response = self.get_pic_response(query)
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
            "weather <location>, yt <query>, search <query>, chat <message>, news <topic>, map <place>, pic <query>."
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
    def handle_chatgpt_command(self, user_text, username=None):
        """
        Send user_text to ChatGPT and handle responses.
        The response can be longer than 200 characters but will be split into blocks.
        """
        self.refresh_membership()  # Refresh membership before generating response
        time.sleep(1)  # Allow time for membership list to be updated
        self.master.update()  # Process any pending updates

        # Fetch the latest chat members from DynamoDB
        self.chat_members = set(self.get_chat_members())
        print(f"[DEBUG] Updated chat members list before generating response: {self.chat_members}")

        response = self.get_chatgpt_response(user_text, username=username)
        self.send_full_message(response)

        # Save the conversation for non-directed messages
        if username is None:
            username = "public_chat"
        self.save_conversation(username, user_text, response)

    ########################################################################
    #                           News
    ########################################################################
    def handle_news_command(self, topic):
        """Fetch top 2 news headlines based on the given topic."""
        response = self.get_news_response(topic)
        chunks = self.chunk_message(response, 250)
        for chunk in chunks:
            self.send_full_message(chunk)

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
                r = requests.post(url, json=data, headers=headers, timeout=10)
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

    def handle_user_greeting(self, username):
        """
        Handle user-specific greeting when they enter the chatroom.
        """
        if not self.auto_greeting_enabled:
            return

        self.send_enter_keystroke()  # Send ENTER keystroke to get the list of users
        time.sleep(1)  # Wait for the response to be processed
        current_members = self.chat_members.copy()
        new_member_username = username.split('@')[0]  # Remove the @<bbsaddress> part
        if new_member_username not in current_members:
            greeting_message = f"{new_member_username} just came into the chatroom, give them a casual greeting directed at them."
            response = self.get_chatgpt_response(greeting_message, direct=True, username=new_member_username)
            self.send_direct_message(new_member_username, response)

    def handle_pic_command(self, query):
        """Fetch a random picture from Pexels based on the query."""
        key = self.pexels_api_key.get()
        if not key:
            response = "Pexels API key is missing."
        elif not query:
            response = "Please specify a query."
        else:
            url = "https://api.pexels.com/v1/search"
            headers = {
                "Authorization": key
            }
            params = {
                "query": query,
                "per_page": 1,
                "page": 1
            }
            try:
                r = requests.get(url, headers=headers, params=params, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                photos = data.get("photos", [])
                if not photos:
                    response = f"No pictures found for '{query}'."
                else:
                    photo = photos[0]
                    photographer = photo.get("photographer", "Unknown")
                    src = photo.get("src", {}).get("original", "No URL")
                    response = f"Photo by {photographer}: {src}"
            except requests.exceptions.RequestException as e:
                response = f"Error fetching picture: {str(e)}"

        self.send_full_message(response)

    def refresh_membership(self):
        """Refresh the membership list by sending an ENTER keystroke and allowing time for processing."""
        self.send_enter_keystroke()
        time.sleep(1)         # Allow BBS lines to arrive
        self.master.update()  # Let process_incoming_messages() parse them

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
                    response = ""
                    for i, article in enumerate(articles):
                        title = article.get("title", "No Title")
                        description = article.get("description", "No Description")
                        link = article.get("url", "No URL")
                        response += f"{i + 1}. {title}\n   {description[:230]}...\n"
                        response += f"Link: {link}\n\n"
                    return response.strip()
            except Exception as e:
                return f"Error fetching news: {str(e)}"

    def handle_polly_command(self, voice, text):
        """Convert text to speech using AWS Polly and provide an S3 link to the MP3 file."""
        valid_voices = ["Matthew", "Stephen", "Ruth", "Joanna", "Danielle"]
        if voice not in valid_voices:
            response_message = f"Invalid voice. Please choose from: {', '.join(valid_voices)}."
            self.send_full_message(response_message)
            return

        if len(text) > 200:
            response_message = "Error: The text for Polly must be 200 characters or fewer."
            self.send_full_message(response_message)
            return

        polly_client = boto3.client('polly', region_name='us-east-1')
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'bbs-audio-files'
        object_key = f"polly_output_{int(time.time())}.mp3"

        try:
            response = polly_client.synthesize_speech(
                Text=text,
                OutputFormat='mp3',
                VoiceId=voice
            )
            audio_stream = response['AudioStream'].read()

            s3_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=audio_stream,
                ContentType='audio/mpeg'
            )

            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{object_key}"
            response_message = f"Here is your Polly audio: {s3_url}"
        except Exception as e:
            response_message = f"Error with Polly: {str(e)}"

        self.send_full_message(response_message)

    def handle_ytmp3_command(self, url):
        """Download YouTube video as MP3, upload to S3, and provide the link."""
        try:
            # Use yt-dlp to download and convert the YouTube video to MP3
            result = subprocess.run(
                ["yt-dlp", "-x", "--audio-format", "mp3", url, "-o", "/tmp/%(id)s.%(ext)s"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise Exception(result.stderr)

            # Extract the video ID from the URL
            video_id = url.split("v=")[1].split("&")[0]
            mp3_filename = f"/tmp/{video_id}.mp3"

            s3_client = boto3.client('s3', region_name='us-east-1')
            bucket_name = 'bbs-audio-files'
            object_key = f"ytmp3_{video_id}.mp3"

            with open(mp3_filename, 'rb') as mp3_file:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=mp3_file,
                    ContentType='audio/mpeg'
                )

            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{object_key}"
            response_message = f"Here is your MP3: {s3_url}"
        except Exception as e:
            response_message = f"Error processing YouTube link: {str(e)}"

        self.send_full_message(response_message)

    def handle_timer_command(self, label, value, unit, username):
        """Set a timer and notify the user when it completes."""
        try:
            value = int(value)
            if unit not in ["second", "seconds", "minute", "minutes"]:
                raise ValueError("Invalid time unit")
            
            duration = value * 60 if "minute" in unit else value
            timer_id = f"{username}_{label}"
            self.timers[timer_id] = self.master.after(duration * 1000, self.timer_complete, label, username)
            response = f"Timer '{label}' set for {value} {unit}."
        except ValueError as e:
            response = f"Error setting timer: {str(e)}"
        
        self.send_direct_message(username, response)

    def timer_complete(self, label, username):
        """Notify the user that their timer is complete."""
        response = f"Timer '{label}' is complete!"
        self.send_direct_message(username, response)
        timer_id = f"{username}_{label}"
        if timer_id in self.timers:
            del self.timers[timer_id]

    def handle_greeting_command(self):
        """Toggle the auto-greeting feature on and off."""
        self.auto_greeting_enabled = not self.auto_greeting_enabled
        state = "enabled" if self.auto_greeting_enabled else "disabled"
        response = f"Auto-greeting has been {state}."
        self.send_full_message(response)

    def handle_seen_command(self, username):
        """Handle the !seen command to report the last seen timestamp of a user."""
        username_lower = username.lower()
        last_seen_lower = {k.lower(): v for k, v in self.last_seen.items()}

        if username_lower in last_seen_lower:
            last_seen_time = last_seen_lower[username_lower]
            last_seen_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen_time))
            response = f"{username} was last seen on {last_seen_str}."
        else:
            response = f"{username} has not been seen in the chatroom."

        self.send_full_message(response)

def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
        root = tk.Tk()
        app = BBSBotApp(root)
        root.mainloop()
    except KeyboardInterrupt:
        print("Script interrupted by user. Exiting...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if app.connected:
            asyncio.run_coroutine_threadsafe(app.disconnect_from_bbs(), app.loop).result()
        try:
            if root.winfo_exists():
                root.quit()
        except tk.TclError:
            pass
        finally:
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.close()
            except Exception as e:
                print(f"Error closing event loop: {e}")

if __name__ == "__main__":
    main()
