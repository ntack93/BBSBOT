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
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from pytube import YouTube
from pydub import AudioSegment
import subprocess

# Load API keys from api_keys.json
def load_api_keys():
    if os.path.exists("api_keys.json"):
        with open("api_keys.json", "r") as file:
            return json.load(file)
    return {}

api_keys = load_api_keys()

###############################################################################
# Default/placeholder API keys (updated in Settings window as needed).
###############################################################################
DEFAULT_OPENAI_API_KEY = api_keys.get("openai_api_key", "")
DEFAULT_WEATHER_API_KEY = api_keys.get("weather_api_key", "")
DEFAULT_YOUTUBE_API_KEY = api_keys.get("youtube_api_key", "")
DEFAULT_GOOGLE_CSE_KEY = api_keys.get("google_cse_api_key", "")  # Google Custom Search API Key
DEFAULT_GOOGLE_CSE_CX = api_keys.get("google_cse_cx", "")   # Google Custom Search Engine ID (cx)
DEFAULT_NEWS_API_KEY = api_keys.get("news_api_key", "")    # NewsAPI Key
DEFAULT_GOOGLE_PLACES_API_KEY = api_keys.get("google_places_api_key", "")  # Google Places API Key
DEFAULT_PEXELS_API_KEY = api_keys.get("pexels_api_key", "")  # Pexels API Key
DEFAULT_ALPHA_VANTAGE_API_KEY = api_keys.get("alpha_vantage_api_key", "")  # Alpha Vantage API Key
DEFAULT_COINMARKETCAP_API_KEY = api_keys.get("coinmarketcap_api_key", "")  # CoinMarketCap API Key
DEFAULT_GIPHY_API_KEY = api_keys.get("giphy_api_key", "")  # Add default Giphy API Key

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
        self.alpha_vantage_api_key = tk.StringVar(value="")  # Add Alpha Vantage API Key
        self.coinmarketcap_api_key = tk.StringVar(value="")  # Add CoinMarketCap API Key
        self.logon_automation_enabled = tk.BooleanVar(value=False)  # Add Logon Automation toggle
        self.auto_login_enabled = tk.BooleanVar(value=False)  # Add Auto Login toggle
        self.giphy_api_key = tk.StringVar(value=DEFAULT_GIPHY_API_KEY)  # Add Giphy API Key
        self.split_view_enabled = False  # Add Split View toggle
        self.split_view_clones = []  # Track split view clones

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
        self.last_seen = self.load_last_seen()  # Load last seen timestamps from file

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
        self.auto_greeting_enabled = False  # Default auto-greeting to off
        self.pending_messages_table_name = 'PendingMessages'
        self.create_pending_messages_table()

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
        except ClientError as e:
            if e.response['Error']['Code'] == 'UnrecognizedClientException':
                print(f"Error: {e}. The security token included in the request is invalid. Please check your AWS credentials.")
            else:
                print(f"Unexpected error: {e}")

    def create_pending_messages_table(self):
        """Create DynamoDB table for pending messages if it doesn't exist."""
        try:
            self.dynamodb_client.describe_table(TableName=self.pending_messages_table_name)
        except self.dynamodb_client.exceptions.ResourceNotFoundException:
            self.dynamodb_client.create_table(
                TableName=self.pending_messages_table_name,
                KeySchema=[
                    {'AttributeName': 'recipient', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'recipient', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'N'}
                ],
                ProvisionedThroughput={
                    'ReadCapacityUnits': 5,
                    'WriteCapacityUnits': 5
                }
            )
            self.dynamodb_client.get_waiter('table_exists').wait(TableName=self.pending_messages_table_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'UnrecognizedClientException':
                print(f"Error: {e}. The security token included in the request is invalid. Please check your AWS credentials.")
            else:
                print(f"Unexpected error: {e}")

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

    def save_pending_message(self, recipient, sender, message):
        """Save a pending message to DynamoDB."""
        timestamp = int(time.time())
        pending_messages_table = dynamodb.Table(self.pending_messages_table_name)
        pending_messages_table.put_item(
            Item={
                'recipient': recipient.lower(),
                'timestamp': timestamp,
                'sender': sender,
                'message': message
            }
        )

    def get_pending_messages(self, recipient):
        """Retrieve pending messages for a recipient from DynamoDB."""
        pending_messages_table = dynamodb.Table(self.pending_messages_table_name)
        response = pending_messages_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('recipient').eq(recipient.lower())
        )
        return response.get('Items', [])

    def delete_pending_message(self, recipient, timestamp):
        """Delete a pending message from DynamoDB."""
        pending_messages_table = dynamodb.Table(self.pending_messages_table_name)
        pending_messages_table.delete_item(
            Key={
                'recipient': recipient.lower(),
                'timestamp': timestamp
            }
        )

    def build_ui(self):
        """Set up frames, text areas, input boxes, etc."""
        main_frame = ttk.Frame(self.master, name='main_frame')
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ----- Config frame -----
        config_frame = ttk.LabelFrame(main_frame, text="Connection Settings")
        config_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(config_frame, text="BBS Host:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)
        self.host_entry = ttk.Entry(config_frame, textvariable=self.host, width=30)
        self.host_entry.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
        self.create_context_menu(self.host_entry)

        ttk.Label(config_frame, text="Port:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.E)
        self.port_entry = ttk.Entry(config_frame, textvariable=self.port, width=6)
        self.port_entry.grid(row=0, column=3, padx=5, pady=5, sticky=tk.W)
        self.create_context_menu(self.port_entry)

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

        # Add a "Split View" button
        split_view_button = ttk.Button(config_frame, text="Split View", command=self.toggle_split_view)
        split_view_button.grid(row=0, column=8, padx=5, pady=5)

        # Add a "Teleconference" button
        teleconference_button = ttk.Button(config_frame, text="Teleconference", command=self.send_teleconference_command)
        teleconference_button.grid(row=0, column=9, padx=5, pady=5)

        # ----- Username frame -----
        username_frame = ttk.LabelFrame(main_frame, text="Username")
        username_frame.pack(fill=tk.X, padx=5, pady=5)

        self.username_entry = ttk.Entry(username_frame, textvariable=self.username, width=30)
        self.username_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.create_context_menu(self.username_entry)

        self.remember_username_check = ttk.Checkbutton(username_frame, text="Remember", variable=self.remember_username)
        self.remember_username_check.pack(side=tk.LEFT, padx=5, pady=5)

        self.send_username_button = ttk.Button(username_frame, text="Send", command=self.send_username)
        self.send_username_button.pack(side=tk.LEFT, padx=5, pady=5)

        # ----- Password frame -----
        password_frame = ttk.LabelFrame(main_frame, text="Password")
        password_frame.pack(fill=tk.X, padx=5, pady=5)

        self.password_entry = ttk.Entry(password_frame, textvariable=self.password, width=30, show="*")
        self.password_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.create_context_menu(self.password_entry)

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
        self.create_context_menu(self.input_box)

        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.LEFT, padx=5, pady=5)

        # Set initial font
        self.update_display_font()

    def create_context_menu(self, widget):
        """Create a right-click context menu for the given widget."""
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_command(label="Select All", command=lambda: widget.event_generate("<<SelectAll>>"))

        def show_context_menu(event):
            menu.tk_popup(event.x_root, event.y_root)

        widget.bind("<Button-3>", show_context_menu)

    def show_settings_window(self):
        """Open a Toplevel with fields for API keys, font settings, etc."""
        settings_win = tk.Toplevel(self.master)
        settings_win.title("Settings")

        row_index = 0

        # ----- OpenAI API Key -----
        ttk.Label(settings_win, text="OpenAI API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        openai_api_key_entry = ttk.Entry(settings_win, textvariable=self.openai_api_key, width=40)
        openai_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(openai_api_key_entry)
        row_index += 1

        # ----- Weather API Key -----
        ttk.Label(settings_win, text="Weather API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        weather_api_key_entry = ttk.Entry(settings_win, textvariable=self.weather_api_key, width=40)
        weather_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(weather_api_key_entry)
        row_index += 1

        # ----- YouTube API Key -----
        ttk.Label(settings_win, text="YouTube API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        youtube_api_key_entry = ttk.Entry(settings_win, textvariable=self.youtube_api_key, width=40)
        youtube_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(youtube_api_key_entry)
        row_index += 1

        # ----- Google CSE Key -----
        ttk.Label(settings_win, text="Google CSE API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        google_cse_api_key_entry = ttk.Entry(settings_win, textvariable=self.google_cse_api_key, width=40)
        google_cse_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(google_cse_api_key_entry)
        row_index += 1

        # ----- Google CSE ID (cx) -----
        ttk.Label(settings_win, text="Google CSE ID (cx):").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        google_cse_cx_entry = ttk.Entry(settings_win, textvariable=self.google_cse_cx, width=40)
        google_cse_cx_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(google_cse_cx_entry)
        row_index += 1

        # ----- News API Key -----
        ttk.Label(settings_win, text="News API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        news_api_key_entry = ttk.Entry(settings_win, textvariable=self.news_api_key, width=40)
        news_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(news_api_key_entry)
        row_index += 1

        # ----- Google Places API Key -----
        ttk.Label(settings_win, text="Google Places API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        google_places_api_key_entry = ttk.Entry(settings_win, textvariable=self.google_places_api_key, width=40)
        google_places_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(google_places_api_key_entry)
        row_index += 1

        # ----- Pexels API Key -----
        ttk.Label(settings_win, text="Pexels API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        pexels_api_key_entry = ttk.Entry(settings_win, textvariable=self.pexels_api_key, width=40)
        pexels_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(pexels_api_key_entry)
        row_index += 1

        # ----- Alpha Vantage API Key -----
        ttk.Label(settings_win, text="Alpha Vantage API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        alpha_vantage_api_key_entry = ttk.Entry(settings_win, textvariable=self.alpha_vantage_api_key, width=40)
        alpha_vantage_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(alpha_vantage_api_key_entry)
        row_index += 1

        # ----- CoinMarketCap API Key -----
        ttk.Label(settings_win, text="CoinMarketCap API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        coinmarketcap_api_key_entry = ttk.Entry(settings_win, textvariable=self.coinmarketcap_api_key, width=40)
        coinmarketcap_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(coinmarketcap_api_key_entry)
        row_index += 1

        # ----- Giphy API Key -----
        ttk.Label(settings_win, text="Giphy API Key:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        giphy_api_key_entry = ttk.Entry(settings_win, textvariable=self.giphy_api_key, width=40)
        giphy_api_key_entry.grid(row=row_index, column=1, padx=5, pady=5)
        self.create_context_menu(giphy_api_key_entry)
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

        # Add Logon Automation checkbox
        ttk.Label(settings_win, text="Logon Automation:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Checkbutton(settings_win, variable=self.logon_automation_enabled).grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # Add Auto Login checkbox
        ttk.Label(settings_win, text="Auto Login:").grid(row=row_index, column=0, padx=5, pady=5, sticky=tk.E)
        ttk.Checkbutton(settings_win, variable=self.auto_login_enabled).grid(row=row_index, column=1, padx=5, pady=5, sticky=tk.W)
        row_index += 1

        # ----- Save Button -----
        save_button = ttk.Button(settings_win, text="Save", command=lambda: self.save_settings(settings_win))
        save_button.grid(row=row_index, column=0, columnspan=2, pady=10)

    def save_settings(self, window):
        """Called when user clicks 'Save' in the settings window."""
        self.update_display_font()
        openai.api_key = self.openai_api_key.get()
        # Save new API keys
        self.save_api_keys()
        window.destroy()

    def save_api_keys(self):
        """Save API keys to a file."""
        api_keys = {
            "openai_api_key": self.openai_api_key.get(),
            "weather_api_key": self.weather_api_key.get(),
            "youtube_api_key": self.youtube_api_key.get(),
            "google_cse_api_key": self.google_cse_api_key.get(),
            "google_cse_cx": self.google_cse_cx.get(),
            "news_api_key": self.news_api_key.get(),
            "google_places_api_key": self.google_places_api_key.get(),
            "pexels_api_key": self.pexels_api_key.get(),
            "alpha_vantage_api_key": self.alpha_vantage_api_key.get(),
            "coinmarketcap_api_key": self.coinmarketcap_api_key.get(),
            "giphy_api_key": self.giphy_api_key.get()  # Save Giphy API Key
        }
        with open("api_keys.json", "w") as file:
            json.dump(api_keys, file)

    def load_api_keys(self):
        """Load API keys from a file."""
        if os.path.exists("api_keys.json"):
            with open("api_keys.json", "r") as file:
                api_keys = json.load(file)
                self.openai_api_key.set(api_keys.get("openai_api_key", ""))
                self.weather_api_key.set(api_keys.get("weather_api_key", ""))
                self.youtube_api_key.set(api_keys.get("youtube_api_key", ""))
                self.google_cse_api_key.set(api_keys.get("google_cse_api_key", ""))
                self.google_cse_cx.set(api_keys.get("google_cse_cx", ""))
                self.news_api_key.set(api_keys.get("news_api_key", ""))
                self.google_places_api_key.set(api_keys.get("google_places_api_key", ""))
                self.pexels_api_key.set(api_keys.get("pexels_api_key", ""))  # Ensure Pexels API Key is loaded
                self.alpha_vantage_api_key.set(api_keys.get("alpha_vantage_api_key", ""))  # Ensure Alpha Vantage API Key is loaded
                self.coinmarketcap_api_key.set(api_keys.get("coinmarketcap_api_key", ""))  # Ensure CoinMarketCap API Key is loaded
                self.giphy_api_key.set(api_keys.get("giphy_api_key", ""))  # Ensure Giphy API Key is loaded

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
        self.append_terminal_text("Connecting to {}:{}...\n".format(host, port), "normal")
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

    def auto_login_sequence(self):
        """Automate the login sequence."""
        if self.connected and self.writer:
            self.send_username()
            self.master.after(1000, self.send_password)
            self.master.after(2000, self.press_enter_repeatedly, 5)

    def press_enter_repeatedly(self, count):
        """Press ENTER every 1 second for a specified number of times."""
        if self.connected and self.writer:
            if count > 0:
                self.send_enter_keystroke()
                self.master.after(1000, self.press_enter_repeatedly, count - 1)
            else:
                self.master.after(1000, self.send_teleconference_command)

    def send_teleconference_command(self):
        """Send '/go tele' and press ENTER."""
        if self.connected and self.writer:
            asyncio.run_coroutine_threadsafe(self._send_message('/go tele\r\n'), self.loop)

    async def disconnect_from_bbs(self):
        """Stop the background thread and close connections."""
        if not self.connected:
            return

        self.stop_event.set()
        self.stop_keep_alive()  # Stop keep-alive coroutine
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()  # Ensure the writer is closed properly
            except Exception as e:
                print(f"Error closing writer: {e}")
        else:
            print("Writer is already None")

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
            try:
                self.master.after_idle(update_connect_button)
            except RuntimeError as e:
                print(f"Error scheduling update_connect_button: {e}")
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
                if self.auto_greeting_enabled:
                    self.handle_user_greeting(username)
                self.previous_line = ""

        # The last piece may be partial if no trailing newline
        self.partial_line = lines[-1]

        # Check for re-logon automation triggers
        if "please finish up and log off." in data.lower():
            self.handle_cleanup_maintenance()
        if self.auto_login_enabled.get() or self.logon_automation_enabled.get():
            if 'otherwise type "new": ' in data.lower() or 'type it in and press enter' in data.lower():
                self.send_username()
            elif 'enter your password: ' in data.lower():
                self.send_password()
            elif 'if you already have a user-id on this system, type it in and press enter. otherwise type "new":' in data.lower():
                self.send_username()
            elif 'greetings, ' in data.lower() and 'glad to see you back again.' in data.lower():
                self.master.after(1000, self.send_teleconference_command)
        elif '(n)onstop, (q)uit, or (c)ontinue?' in data.lower():
            self.send_enter_keystroke()

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

        # Handle the case where users are listed without email addresses
        user_without_domain_match = re.findall(r'\b\S+ is here with you\.', combined_clean)
        for user in user_without_domain_match:
            usernames.append(user.split()[0])

        print(f"[DEBUG] Extracted usernames: {usernames}")  # Debug statement

        # Make them a set to avoid duplicates
        self.chat_members = set(usernames)
        self.save_chat_members()  # Save updated chat members to DynamoDB

        # Update last seen timestamps
        current_time = int(time.time())
        for member in self.chat_members:
            self.last_seen[member.lower()] = current_time

        self.save_last_seen()  # Save updated last seen timestamps to file

        print(f"[DEBUG] Updated chat members: {self.chat_members}")

        # Check and send pending messages for new members
        for new_member_username in usernames:
            self.check_and_send_pending_messages(new_member_username)

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
        Check for commands in the given line: !weather, !yt, !search, !chat, !news, !map, !pic, !polly, !mp3yt, !help, !seen, !greeting, !stocks, !crypto, !timer, !gif, !msg
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

        # Check for page commands (both 'from' and 'via')
        page_message_match = re.match(r'(.+?) is paging you (from|via) (.+?): (.+)', clean_line)
        if page_message_match:
            username = page_message_match.group(1)
            module_or_channel = page_message_match.group(3)
            message = page_message_match.group(4)
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
            elif "!weather" in message:
                location = message.split("!weather", 1)[1].strip()
                self.handle_weather_command(location)
                return
            elif "!yt" in message:
                query = message.split("!yt", 1)[1].strip()
                self.handle_youtube_command(query)
                return
            elif "!search" in message:
                query = message.split("!search", 1)[1].strip()
                self.handle_web_search_command(query)
                return
            elif "!news" in message:
                topic = message.split("!news", 1)[1].strip()
                self.handle_news_command(topic)
                return
            elif "!map" in message:
                place = message.split("!map", 1)[1].strip()
                self.handle_map_command(place)
                return
            elif "!pic" in message:
                query = message.split("!pic", 1)[1].strip()
                self.handle_pic_command(query)
                return
            elif "!polly" in message:
                parts = message.split("!polly", 1)[1].strip().split(maxsplit=1)
                if len(parts) == 2:
                    voice, text = parts
                    self.handle_polly_command(voice, text)
                else:
                    self.send_full_message("Please choose a Polly voice and provide text to convert. The voices are: Matthew, Stephen, Ruth, Joanna, Danielle.")
                return
            elif "!mp3yt" in message:
                url = message.split("!mp3yt", 1)[1].strip()
                self.handle_ytmp3_command(url)
                return
            elif "!help" in message:
                self.handle_help_command()
                return
            elif "!seen" in message:
                target_username = message.split("!seen", 1)[1].strip()
                self.handle_seen_command(target_username)
                return
            elif "!greeting" in message:
                self.handle_greeting_command()
                return
            elif "!stocks" in message:
                symbol = message.split("!stocks", 1)[1].strip()
                self.handle_stock_command(symbol)
                return
            elif "!crypto" in message:
                crypto = message.split("!crypto", 1)[1].strip()
                self.handle_crypto_command(crypto)
                return
            elif "!timer" in message:
                parts = message.split("!timer", 1)[1].strip().split()
                if len(parts) == 2:
                    value, unit = parts
                    self.handle_timer_command(username, value, unit)
                else:
                    self.send_full_message("Please use the syntax '!timer <value> <minutes or seconds>'.")
                return
            elif "!gif" in message:
                query = message.split("!gif", 1)[1].strip()
                self.handle_gif_command(query)
                return
            elif "!msg" in message:
                parts = message.split("!msg", 1)[1].strip().split(maxsplit=1)
                if len(parts) == 2:
                    recipient, message = parts
                    sender_match = re.match(r'From (.+?):', clean_line)
                    sender = sender_match.group(1) if sender_match else "unknown"
                    self.handle_msg_command(recipient, message, sender)
                else:
                    self.send_full_message("Please use the syntax '!msg <username> <message>'.")
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
        elif re.match(r'(.+?)@(.+?) \(.*?\) is now online\.  Total users: \d+\.', clean_line):
            # This line indicates a user logged onto the BBS, not necessarily entered the chatroom
            return

        # Check for re-logon automation triggers
        if "please finish up and log off." in clean_line.lower():
            self.handle_cleanup_maintenance()
        if self.auto_login_enabled.get() or self.logon_automation_enabled.get():
            if 'otherwise type "new": ' in clean_line.lower() or 'type it in and press enter' in clean_line.lower():
                self.send_username()
            elif 'enter your password: ' in clean_line.lower():
                self.send_password()
            elif 'if you already have a user-id on this system, type it in and press enter. otherwise type "new":' in clean_line.lower():
                self.send_username()
            elif 'greetings, ' in clean_line.lower() and 'glad to see you back again.' in clean_line.lower():
                self.master.after(1000, self.send_teleconference_command)
        elif '(n)onstop, (q)uit, or (c)ontinue?' in clean_line.lower():
            self.send_enter_keystroke()

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
        elif "!stocks" in message:
            symbol = message.split("!stocks", 1)[1].strip()
            response = self.get_stock_price(symbol)
        elif "!crypto" in message:
            crypto = message.split("!crypto", 1)[1].strip()
            response = self.get_crypto_price(crypto)
        elif "!gif" in message:
            query = message.split("!gif", 1)[1].strip()
            response = self.get_gif_response(query)
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
        elif "!stocks" in message:
            symbol = message.split("!stocks", 1)[1].strip()
            response = self.get_stock_price(symbol)
        elif "!crypto" in message:
            crypto = message.split("!crypto", 1)[1].strip()
            response = self.get_crypto_price(crypto)
        elif "!who" in message:
            response = self.get_who_response()
        elif "!seen" in message:
            target_username = message.split("!seen", 1)[1].strip()
            response = self.get_seen_response(target_username)
        elif "!gif" in message:
            query = message.split("!gif", 1)[1].strip()
            response = self.get_gif_response(query)
        else:
            response = "Unknown command."

        self.send_page_response(username, module_or_channel, response)

    def get_who_response(self):
        """Return a list of users currently in the chatroom."""
        if not self.chat_members:
            return "No users currently in the chatroom."
        else:
            return "Users currently in the chatroom: " + ", ".join(self.chat_members)

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
            "Your name is Ultron. You speak very casually. When you greet people, you usually say things like 'Hey :)', 'What's up?', 'How's it going?'. "
            "You are just a laidback guy, hanging out in the bbs chatroom. "
            "Respond concisely in 220-characters or less but don't exceed 250 total characters in your responses. "
            "If asked about who's in the room, reference the current chatroom members list. "
            f"The current chatroom members are: {chatroom_members_str}."
        )

        if direct:
            system_message = (
                "Your name is Ultron. You speak very casually. When you greet people, you usually say things like 'Hey :)', 'What's up?', 'How's it going?'. "
                "You are just a laidback guy, hanging out in the bbs chatroom. "
                "Respond concisely in 220-characters or less but don't exceed 250 total characters in your responses. "
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
                max_tokens=250,
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
        The response can be longer than 220 characters but will be split into blocks.
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
            "weather <location>, yt <query>, search <query>, chat <message>, news <topic>, map <place>, pic <query>, "
            "polly <voice> <text>, mp3yt <youtube link>, help, seen <username>, "
            "greeting, stocks <symbol>, crypto <symbol>, timer <value> <minutes or seconds>, gif <query>, msg <username> <message>."
        )

    def handle_help_command(self):
        """Provide a list of available commands, adhering to character and chunk limits."""
        help_message = self.get_help_response()
        self.send_full_message(help_message)

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
        full_message = '\n'.join([prefix + line for line in lines])
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
                    elif "!help" in clean_line:
                        self.handle_help_command()
                    elif "!seen" in clean_line:
                        target_username = clean_line.split("!seen", 1)[1].strip()
                        self.handle_seen_command(target_username)
                    elif "!greeting" in clean_line:
                        self.handle_greeting_command()
                    elif "!stocks" in clean_line:
                        symbol = clean_line.split("!stocks", 1)[1].strip()
                        self.handle_stock_command(symbol)
                    elif "!crypto" in clean_line:
                        crypto = clean_line.split("!crypto", 1)[1].strip()
                        self.handle_crypto_command(crypto)
                    elif "!gif" in clean_line:
                        query = clean_line.split("!gif", 1)[1].strip()
                        self.handle_gif_command(query)
                    elif "!msg" in clean_line:
                        parts = clean_line.split("!msg", 1)[1].strip().split(maxsplit=1)
                        if len(parts) == 2:
                            recipient, message = parts
                            sender_match = re.match(r'From (.+?):', clean_line)
                            sender = sender_match.group(1) if sender_match else "unknown"
                            self.handle_msg_command(recipient, message, sender)
                        else:
                            self.send_full_message("Please use the syntax '!msg <username> <message>'.")

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
        elif "!stocks" in message:
            symbol = message.split("!stocks", 1)[1].strip()
            response = self.get_stock_price(symbol)
        elif "!crypto" in message:
            crypto = message.split("!crypto", 1)[1].strip()
            response = self.get_crypto_price(crypto)
        elif "!gif" in message:
            query = message.split("!gif", 1)[1].strip()
            response = self.get_gif_response(query)
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
        elif "!stocks" in message:
            symbol = message.split("!stocks", 1)[1].strip()
            response = self.get_stock_price(symbol)
        elif "!crypto" in message:
            crypto = message.split("!crypto", 1)[1].strip()
            response = self.get_crypto_price(crypto)
        elif "!who" in message:
            response = self.get_who_response()
        elif "!seen" in message:
            target_username = message.split("!seen", 1)[1].strip()
            response = self.get_seen_response(target_username)
        elif "!gif" in message:
            query = message.split("!gif", 1)[1].strip()
            response = self.get_gif_response(query)
        else:
            response = "Unknown command."

        self.send_page_response(username, module_or_channel, response)

    def get_who_response(self):
        """Return a list of users currently in the chatroom."""
        if not self.chat_members:
            return "No users currently in the chatroom."
        else:
            return "Users currently in the chatroom: " + ", ".join(self.chat_members)

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
        help_message = self.get_help_response()
        self.send_full_message(help_message)

    ########################################################################
    #                           Weather
    ########################################################################
    def handle_weather_command(self, location):
        """Fetch weather info and relay it to the user using ChatGPT."""
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
                    weather_info = {
                        "location": location.title(),
                        "description": data["weather"][0]["description"],
                        "temp_f": data["main"]["temp"],
                        "feels_like": data["main"]["feels_like"],
                        "humidity": data["main"]["humidity"],
                        "wind_speed": data["wind"]["speed"],
                        "precipitation": data.get("rain", {}).get("1h", 0) + data.get("snow", {}).get("1h", 0)
                    }

                    # Prepare the prompt for ChatGPT
                    prompt = (
                        f"The weather in {weather_info['location']} is currently described as {weather_info['description']}. "
                        f"The temperature is {weather_info['temp_f']:.1f}°F, but it feels like {weather_info['feels_like']:.1f}°F. "
                        f"The humidity is {weather_info['humidity']}%, and the wind speed is {weather_info['wind_speed']} mph. "
                        f"There is {weather_info['precipitation']} mm of precipitation. "
                        "Please relay this weather information to the user in a friendly and natural way."
                    )

                    # Get the response from ChatGPT
                    chatgpt_response = self.get_chatgpt_response(prompt)
                    response = chatgpt_response
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
        The response can be longer than 220 characters but will be split into blocks.
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
        """Send an <ENTER> keystroke every 10 seconds to keep the connection alive."""
        while not self.keep_alive_stop_event.is_set():
            if self.connected and self.writer:
                self.writer.write("\r\n")
                await self.writer.drain()
            await asyncio.sleep(10)

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
        valid_voices = {
            "Matthew": "standard",
            "Stephen": "neural",
            "Ruth": "neural",
            "Joanna": "neural",
            "Danielle": "neural"
        }
        if voice not in valid_voices:
            response_message = f"Invalid voice. Please choose from: {', '.join(valid_voices.keys())}."
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
                VoiceId=voice,
                Engine=valid_voices[voice]
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

    def handle_greeting_command(self):
        """Toggle the auto-greeting feature on and off."""
        self.auto_greeting_enabled = not self.auto_greeting_enabled
        state = "enabled" if self.auto_greeting_enabled else "disabled"
        response = f"Auto-greeting has been {state}."
        self.send_full_message(response)

    def handle_seen_command(self, username):
        """Handle the !seen command to report the last seen timestamp of a user."""
        response = self.get_seen_response(username)
        self.send_full_message(response)

    def get_seen_response(self, username):
        """Return the last seen timestamp of a user."""
        username_lower = username.lower()
        last_seen_lower = {k.lower(): v for k, v in self.last_seen.items()}

        if username_lower in last_seen_lower:
            last_seen_time = last_seen_lower[username_lower]
            last_seen_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen_time))
            time_diff = int(time.time()) - last_seen_time
            hours, remainder = divmod(time_diff, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{username} was last seen on {last_seen_str} ({hours} hours, {minutes} minutes, {seconds} seconds ago)."
        else:
            return f"{username} has not been seen in the chatroom."

    def save_last_seen(self):
        """Save the last seen dictionary to a file."""
        with open("last_seen.json", "w") as file:
            json.dump(self.last_seen, file)

    def load_last_seen(self):
        """Load the last seen dictionary from a file."""
        if os.path.exists("last_seen.json"):
            with open("last_seen.json", "r") as file:
                return json.load(file)
        return {}

    def get_stock_price(self, symbol):
        """Fetch the current price of a stock."""
        api_key = self.alpha_vantage_api_key.get()
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
        try:
            response = requests.get(url)
            data = response.json()
            price = data["Global Quote"]["05. price"]
            return f"{symbol.upper()}: ${price}"
        except Exception as e:
            return f"Error fetching stock price: {str(e)}"

    def get_crypto_price(self, crypto):
        """Fetch the current price of a cryptocurrency."""
        api_key = self.coinmarketcap_api_key.get()
        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
        parameters = {
            'symbol': crypto,
            'convert': 'USD'
        }
        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': api_key,
        }
        session = requests.Session()
        session.headers.update(headers)
        try:
            response = session.get(url, params=parameters)
            data = response.json()
            if "data" in data and crypto in data["data"]:
                price = data["data"][crypto]["quote"]["USD"]["price"]
                return f"{crypto.upper()}: ${price:.2f}"
            else:
                return f"Invalid cryptocurrency symbol '{crypto}'. Please use valid symbols like BTC, ETH, DOGE, etc."
        except (requests.ConnectionError, requests.Timeout, requests.TooManyRedirects) as e:
            return f"Error fetching crypto price: {str(e)}"

    def handle_stock_command(self, symbol):
        """Handle the !stocks command to show the current price of a stock."""
        if not self.alpha_vantage_api_key.get():
            response = "Alpha Vantage API key is missing."
        else:
            response = self.get_stock_price(symbol)
        self.send_full_message(response[:50])  # Ensure the response is no more than 50 characters

    def handle_crypto_command(self, crypto):
        """Handle the !crypto command to show the current price of a cryptocurrency."""
        if not self.coinmarketcap_api_key.get():
            response = "CoinMarketCap API key is missing."
        else:
            response = self.get_crypto_price(crypto)
        self.send_full_message(response[:50])  # Ensure the response is no more than 50 characters

    def handle_cleanup_maintenance(self):
        """Handle cleanup maintenance by reconnecting to the BBS."""
        if self.logon_automation_enabled.get():
            print("Cleanup maintenance detected. Reconnecting to the BBS...")
            self.disconnect_from_bbs()
            time.sleep(5)  # Wait for a few seconds before reconnecting
            self.start_connection()

    def handle_timer_command(self, username, value, unit):
        """Handle the !timer command to set a timer for the user."""
        try:
            value = int(value)
            if unit not in ["minutes", "seconds"]:
                raise ValueError("Invalid unit")
        except ValueError:
            self.send_full_message("Invalid timer value or unit. Please use the syntax '!timer <value> <minutes or seconds>'.")
            return

        duration = value * 60 if unit == "minutes" else value
        timer_id = f"{username}_{time.time()}"

        def timer_callback():
            self.send_full_message(f"Timer for {username} has ended.")
            del self.timers[timer_id]

        self.timers[timer_id] = self.master.after(duration * 1000, timer_callback)
        self.send_full_message(f"Timer set for {username} for {value} {unit}.")

    def handle_gif_command(self, query):
        """Fetch a popular GIF based on the query."""
        key = self.giphy_api_key.get()
        if not key:
            response = "Giphy API key is missing."
        elif not query:
            response = "Please specify a query."
        else:
            url = "https://api.giphy.com/v1/gifs/search"
            params = {
                "api_key": key,
                "q": query,
                "limit": 1,
                "rating": "g"
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()  # Raise an HTTPError for bad responses
                data = r.json()
                gifs = data.get("data", [])
                if not gifs:
                    response = f"No GIFs found for '{query}'."
                else:
                    gif_url = gifs[0].get("url", "No URL")
                    response = f"GIF for '{query}': {gif_url}"
            except requests.exceptions.RequestException as e:
                response = f"Error fetching GIF: {str(e)}"

        self.send_full_message(response)

    def toggle_split_view(self):
        """Toggle the split view to create multiple bot instances."""
        if not self.split_view_enabled:
            self.split_view_enabled = True
            main_container = self.master.nametowidget('main_frame')
            main_container.pack_forget()

            split_frame = ttk.Frame(self.master)
            split_frame.pack(fill=tk.BOTH, expand=True)

            left_frame = ttk.Frame(split_frame)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            right_frame = ttk.Frame(split_frame)
            right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

            main_container.pack(in_=left_frame, fill=tk.BOTH, expand=True)
            clone = self.create_clone(main_container)
            clone.pack(in_=right_frame, fill=tk.BOTH, expand=True)

            self.split_view_clones.append(clone)
            print("Split View enabled")
        else:
            self.split_view_enabled = False
            for clone in self.split_view_clones:
                clone.destroy()
            self.split_view_clones.clear()
            main_container = self.master.nametowidget('main_frame')
            main_container.pack(fill=tk.BOTH, expand=True)
            print("Split View disabled")

    def create_clone(self, widget):
        """Create a clone of the given widget."""
        clone = ttk.Frame(self.master)
        for child in widget.winfo_children():
            child_clone = self.clone_widget(child, clone)
            child_clone.pack()
        return clone

    def clone_widget(self, widget, parent):
        """Clone a widget and its configuration."""
        widget_class = widget.__class__
        widget_config = {key: val[-1] for key, val in widget.configure().items() if isinstance(val[-1], (str, int, float)) or key in ('text', 'value')}
        
        # Handle special cases for configuration values
        for key, val in widget_config.items():
            if isinstance(val, str) and val.startswith('-'):
                widget_config[key] = val[1:]
            if key in ('borderwidth', 'highlightthickness', 'padx', 'pady'):
                widget_config[key] = int(val) if val else 0
            if key == 'font':
                font_parts = val.split()
                if len(font_parts) > 1 and font_parts[1].isdigit():
                    widget_config[key] = (font_parts[0], int(font_parts[1]))
                else:
                    widget_config[key] = val
            if key == 'width' and val == 'borderwidth':
                widget_config[key] = 1

        # Ensure valid configuration values
        widget_config = {k: v for k, v in widget_config.items() if v is not None and v != ''}

        # Handle special cases for Text widget
        if widget_class == tk.Text:
            widget_clone = widget_class(parent, **widget_config)
            widget_clone.insert(tk.END, widget.get("1.0", tk.END))
        else:
            widget_clone = widget_class(parent, **widget_config)

        for child in widget.winfo_children():
            self.clone_widget(child, widget_clone)
        return widget_clone

    def handle_msg_command(self, recipient, message, sender):
        """Handle the !msg command to leave a message for another user."""
        self.save_pending_message(recipient, sender, message)
        self.send_full_message(f"Message for {recipient} saved. They will receive it the next time they are seen in the chatroom.")

    def check_and_send_pending_messages(self, username):
        """Check for and send any pending messages for the given username."""
        pending_messages = self.get_pending_messages(username)
        for msg in pending_messages:
            sender = msg['sender']
            message = msg['message']
            timestamp = msg['timestamp']
            self.send_direct_message(username, f"Message from {sender}: {message}")
            self.delete_pending_message(username, timestamp)

def main():
    app = None  # Initialize app variable
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
        if app and app.connected:
            try:
                asyncio.run_coroutine_threadsafe(app.disconnect_from_bbs(), app.loop).result()
            except Exception as e:
                print(f"Error during disconnect: {e}")
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
