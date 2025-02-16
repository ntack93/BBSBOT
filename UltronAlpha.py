import threading
import asyncio
import telnetlib3
import time
import queue
import re
import sys
import requests
import openai
import json
import os
import boto3
from botocore.exceptions import NoCredentialsError, PartialCredentialsError
from pytube import YouTube
from pydub import AudioSegment
import subprocess
from openai import OpenAI
import smtplib
from email.mime.text import MIMEText
import shlex
import curses  # <-- UI change: added for CLI interface
from BBSBotCLITmux import main_cli_tmux  # added import
from shared_queue import incoming_message_queue, outgoing_message_queue  # Import the shared message queues

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
    def __init__(self):
        # Initialize core components
        self.chat_members = set()
        self.last_seen = self.load_last_seen()
        self.public_message_history = {}
        self.timers = {}
        self.partial_message = ""
        self.previous_line = ""
        self.user_list_buffer = []
        self.favorites = self.load_favorites()
        self.msg_queue = queue.Queue()
        
        # API client initialization
        self.openai_client = OpenAI(api_key=DEFAULT_OPENAI_API_KEY)
        
        # Initialize DynamoDB clients
        self.dynamodb_client = boto3.client('dynamodb', region_name='us-east-1')
        self.table_name = 'ChatBotConversations'
        self.pending_messages_table_name = 'PendingMessages'
        
        self.stop_event = threading.Event()
        self.start_message_processing()

    def start_message_processing(self):
        """Start a background thread to process incoming messages from the shared queue."""
        def process_messages():
            while not self.stop_event.is_set():
                try:
                    data = incoming_message_queue.get(timeout=1)
                    self.process_data_chunk(data)
                except queue.Empty:
                    continue

        thread = threading.Thread(target=process_messages, daemon=True)
        thread.start()

    def stop_message_processing(self):
        """Stop the background message processing thread."""
        self.stop_event.set()

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
        self.start_keep_alive()  # Start keep-alive coroutine

    async def telnet_client_task(self, host, port):
        """Async function connecting via telnetlib3 (CP437 + ANSI), reading bigger chunks."""
        try:
            reader, writer = await telnetlib3.open_connection(
                host=host,
                port=port,
                term=self.terminal_mode.get().lower(),
                encoding='cp437',
                cols=136  # Set terminal width to 136 columns
            )
        except Exception as e:
            self.msg_queue.put_nowait(f"Connection failed: {e}\n")
            return

        self.reader = reader
        self.writer = writer
        self.connected = True
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
                await self.writer.drain()  # Ensure the writer is closed properly
            except Exception as e:
                print(f"Error closing writer: {e}")
        else:
            print("Writer is already None")

        self.connected = False
        self.reader = None
        self.writer = None

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

    
        """
        Check for commands in the given line: !weather, !yt, !search, !chat, !news, !map, !pic, !polly, !mp3yt, !help, !seen, !greeting, !stocks, !crypto, !timer, !gif, !msg, !nospam
        And now also capture public messages for conversation history.
        """
        # Remove ANSI codes for easier parsing
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')
        clean_line = ansi_escape_regex.sub('', line)

        # Handle !nospam toggle first, so you can always toggle it
        if "!nospam" in clean_line:
            self.no_spam_mode.set(not self.no_spam_mode.get())
            state = "enabled" if self.no_spam_mode.get() else "disabled"
            self.send_full_message(f"No Spam Mode has been {state}.")
            return

        # Check if the message is private
        private_message_match = re.match(r'From (.+?) \(whispered\): (.+)', clean_line)
        page_message_match = re.match(r'(.+?) is paging you (from|via) (.+?): (.+)', clean_line)
        direct_message_match = re.match(r'From (.+?) \(to you\): (.+)', clean_line)

        # Ignore other public messages if no_spam_mode is enabled
        if self.no_spam_mode.get() and not private_message_match and not page_message_match and not direct_message_match:
            return

        # Check for private messages
        if private_message_match:
            username = private_message_match.group(1)
            message = private_message_match.group(2)
            self.partial_message += message + " "
            if message.endswith("."):
                self.handle_private_trigger(username, self.partial_message.strip())
                self.partial_message = ""
            return

        # Check for page commands (both 'from' and 'via')
        if page_message_match:
            username = page_message_match.group(1)
            module_or_channel = page_message_match.group(3)
            message = page_message_match.group(4)
            self._trigger(username, module_or_channel, message)
            return

        # Check for direct messages
        if direct_message_match:
            username = direct_message_match.group(1)
            message = direct_message_match.group(2)
            self.partial_message += message + " "
            if message.endswith("."):
                self.handle_chatgpt_command(self.partial_message.strip(), username=username)
                self.partial_message = ""
            return

        # Check for public triggers
        public_trigger_match = re.match(r'From (.+?): (.+)', clean_line)
        if public_trigger_match:
            username = public_trigger_match.group(1)
            message = public_trigger_match.group(2)
            if self.no_spam_mode.get():
                return
            if message.startswith("!said"):
                self.handle_said_command(username, message)
            else:
                self.store_public_message(username, message)
                self.handle_public_trigger(username, message)
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
        response = "Unknown command."  # Initialize response with a default value
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
        elif "!doc" in message:
            query = message.split("!doc", 1)[1].strip()
            self.handle_doc_command(query, username)
            return  # Exit early to avoid sending a response twice
        elif "!said" in message:
            self.handle_said_command(username, message)
        elif "!pod" in message:
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                self.send_private_message(username, "Usage: !pod <show> <episode name or number>")
                return
            show = parts[1]
            episode = parts[2]
            self.handle_pod_command(username, show, episode)
            return
        elif "!mail" in message:
            self.handle_mail_command(message)
        elif "!radio" in message:
            match = re.match(r'!radio\s+"([^"]+)"', message)
            if match:
                query = match.group(1)
                self.handle_radio_command(query)
            else:
                self.send_private_message(username, 'Usage: !radio "search query"')
        else:
            response = self.get_chatgpt_response(message, username=username)

        self.send_private_message(username, response)

    

    def handle_page_trigger(self, username, module_or_channel, message):
        """
        Handle page message triggers and respond accordingly.
        """
        response = None  # Initialize response with None
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
        elif "!doc" in message:
            query = message.split("!doc", 1)[1].strip()
            self.handle_doc_command(query, username)
        elif "!said" in message:
            self.handle_said_command(username, message, is_page=True, module_or_channel=module_or_channel)
        elif "!pod" in message:
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                self.send_page_response(username, module_or_channel, "Usage: !pod <show> <episode name or number>")
                return
            show = parts[1]
            episode = parts[2]
            self.handle_pod_command(username, show, episode, is_page=True, module_or_channel=module_or_channel)
            return
        elif "!mail" in message:
            self.handle_mail_command(message)
        elif "!radio" in message:
            match = re.match(r'!radio\s+"([^"]+)"', message)
            if match:
                query = match.group(1)
                self.handle_radio_command(query)
            else:
                self.send_page_response(username, module_or_channel, 'Usage: !radio "search query"')

        if response:
            self.send_page_response(username, module_or_channel, response)

    

    

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
        elif "!said" in message:
            self.handle_said_command(username, message)
            return
        elif "!pod" in message:
            parts = message.split(maxsplit=2)
            if len(parts) < 3:
                self.send_direct_message(username, "Usage: !pod <show> <episode name or number>")
                return
            show = parts[1]
            episode = parts[2]
            self.handle_pod_command(username, show, episode)
            return
        elif "!mail" in message:
            self.handle_mail_command(message)
            return
        elif "!radio" in message:
            match = re.match(r'!radio\s+"([^"]+)"', message)
            if match:
                query = match.group(1)
                self.handle_radio_command(query)
            else:
                self.send_direct_message(username, 'Usage: !radio "search query"')
                return
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
            outgoing_message_queue.put(full_message)

    def get_weather_response(self, args):
        """Fetch weather info and return the response as a string."""
        key = self.weather_api_key.get()
        if not key:
            return "Weather API key is missing."

        # Split args into command, city, and state
        parts = args.strip().split(maxsplit=3)
        if len(parts) < 3:
            return "Usage: !weather <current/forecast> <city> <state>"

        command, city, state = parts[0], parts[1], parts[2]

        if command.lower() not in ['current', 'forecast']:
            return "Please specify either 'current' or 'forecast' as the first argument."

        if not city or not state:
            return "Please specify both city and state."

        location = f"{city},{state}"

        if command.lower() == 'current':
            # Get current weather
            url = "http://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": key,
                "units": "imperial"
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                if data.get("cod") != 200:
                    return f"Could not get weather for '{location}'."
                
                desc = data["weather"][0]["description"]
                temp_f = data["main"]["temp"]
                feels_like = data["main"]["feels_like"]
                humidity = data["main"]["humidity"]
                wind_speed = data["wind"]["speed"]
                precipitation = data.get("rain", {}).get("1h", 0) + data.get("snow", {}).get("1h", 0)

                return (
                    f"Current weather in {city.title()}, {state.upper()}: {desc}, {temp_f:.1f}°F "
                    f"(feels like {feels_like:.1f}°F), Humidity {humidity}%, Wind {wind_speed} mph, "
                    f"Precipitation {precipitation} mm."
                )
            except requests.exceptions.RequestException as e:
                return f"Error fetching weather: {str(e)}"

        else:  # forecast
            # Get 5-day forecast
            url = "http://api.openweathermap.org/data/2.5/forecast"
            params = {
                "q": location,
                "appid": key,
                "units": "imperial"
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                r.raise_for_status()
                data = r.json()
                if data.get("cod") != "200":
                    return f"Could not get forecast for '{location}'."

                # Get next 3 days forecast (excluding today)
                forecasts = []
                current_date = None
                for item in data['list']:
                    date = time.strftime('%Y-%m-%d', time.localtime(item['dt']))
                    if date == time.strftime('%Y-%m-%d'):  # Skip today
                        continue
                    if date != current_date and len(forecasts) < 3:  # Get next 3 days
                        current_date = date
                        temp = item['main']['temp']
                        desc = item['weather'][0]['description']
                        forecasts.append(f"{time.strftime('%A', time.localtime(item['dt']))}: {desc}, {temp:.1f}°F")

                return (
                    f"3-day forecast for {city.title()}, {state.upper()}: " + 
                    ", ".join(forecasts)
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
        if not self.openai_client:
            return "OpenAI client is not initialized."

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
            "You are speaking in a BBS plain text chatroom, please make sure any emoji you use are plain text, and that the format of your responses is ideal for plain text. "
            f"The current chatroom members are: {chatroom_members_str}."
        )

        if direct:
            system_message = (
                "Your name is Ultron. You speak very casually. When you greet people, you usually say things like 'Hey :)', 'What's up?', 'How's it going?'. "
                "You are just a laidback guy, hanging out in the bbs chatroom. "
                "Respond concisely in 220-characters or less but don't exceed 250 total characters in your responses. "
                "If asked about who's in the room, reference the current chatroom members list. "
                "You are speaking in a BBS plain text chatroom, please make sure any emoji you use are plain text, and that the format of your responses is ideal for plain text. "
                f"The current chatroom members are: {chatroom_members_str}."
            )

        # Optionally load conversation history from DynamoDB
        if username:
            conversation_history = self.get_conversation_history(username)
        else:
            conversation_history = self.get_conversation_history("public_chat")

        # Truncate conversation history to the last 5 messages
        truncated_history = conversation_history[-5:]

        messages = [
            {"role": "system", "content": system_message}
        ]
        # Then append user messages and assistant replies from the truncated history
        for item in truncated_history:
            messages.append({"role": "user", "content": item['message']})
            messages.append({"role": "assistant", "content": item['response']})

        # (Optional) add a mini fact about who is speaking:
        if username:
            messages.append({"role": "system", "content": f"Reminder: The user speaking is named {username}."})

        # Finally append this new user_text
        messages.append({"role": "user", "content": user_text})

        print(f"[DEBUG] Chunks sent to ChatGPT: {messages}")  # Log chunks sent to ChatGPT

        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                n=1,
                max_tokens=500,  # Allow for longer responses
                temperature=0.2,  # Set temperature to 0.2
                messages=messages
            )
            gpt_response = completion.choices[0].message.content

            if username:
                self.save_conversation(username, user_text, gpt_response)
            else:
                self.save_conversation("public_chat", user_text, gpt_response)

        except Exception as e:
            gpt_response = f"Error with ChatGPT API: {str(e)}"

        print(f"[DEBUG] ChatGPT response: {gpt_response}")  # Log ChatGPT response
        return gpt_response

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
            "polly <voice> <text>, mp3yt <youtube link>, help, seen <username>, greeting, stocks <symbol>, "
            "crypto <symbol>, timer <value> <minutes or seconds>, gif <query>, msg <username> <message>, doc <query>, pod <show> <episode>, !trump, nospam.\n"
        )

    def send_message(self, event=None):
        """Send the user's typed message to the BBS."""
        if not self.connected or not self.writer:
            return

        user_input = self.input_var.get()
        self.input_var.set("")
        # Replace the /n markers with newline characters
        processed_input = self.replace_newline_markers(user_input)

        if processed_input.strip():
            prefix = "Gos " if self.mud_mode.get() else ""
            message = prefix + processed_input
            asyncio.run_coroutine_threadsafe(self._send_message(message + "\r\n"), self.loop)

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
            if self.connected and self.writer:
                asyncio.run_coroutine_threadsafe(self._send_message(chunk + "\r\n"), self.loop)
                time.sleep(0.1)  # Add a short delay to ensure messages are sent in sequence
            outgoing_message_queue.put(full_message)

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
        # Remove ANSI codes for easier parsing.
        ansi_escape_regex = re.compile(r'\x1b\[(.*?)m')
        clean_line = ansi_escape_regex.sub('', line)

        # Always allow the !nospam command to toggle state
        if "!nospam" in clean_line:
            # Toggle and persist the new state
            self.no_spam_mode.set(not self.no_spam_mode.get())
            state = "enabled" if self.no_spam_mode.get() else "disabled"
            self.send_full_message(f"No Spam Mode has been {state}.")
            self.save_no_spam_state()
            return

        # Detect message types
        private_message_match = re.match(r'From (.+?) \(whispered\): (.+)', clean_line)
        page_message_match = re.match(r'(.+?) is paging you from (.+?): (.+)', clean_line)
        direct_message_match = re.match(r'From (.+?) \(to you\): (.+)', clean_line)

        # If !nospam is ON, only allow whispered and paging messages.
        if self.no_spam_mode.get() and not (private_message_match or page_message_match):
            return

        # Process private messages
        if private_message_match:
            username = private_message_match.group(1)
            message = private_message_match.group(2)
            self.handle_private_trigger(username, message)
        else:
            # Process page commands
            if page_message_match:
                username = page_message_match.group(1)
                module_or_channel = page_message_match.group(2)
                message = page_message_match.group(3)
                self.handle_page_trigger(username, module_or_channel, message)
            # Process direct messages (only if !nospam is OFF)
            elif direct_message_match:
                username = direct_message_match.group(1)
                message = direct_message_match.group(2)
                self.handle_direct_message(username, message)
            else:
                # Process known commands.
                public_trigger_match = re.match(r'From (.+?): (.+)', clean_line)
                if public_trigger_match:
                    sender = public_trigger_match.group(1)
                    message = public_trigger_match.group(2)

                    # Always store the public message.
                    self.store_public_message(sender, message)

                    # Ignore messages from Ultron (the bot itself).
                    if sender.lower() == "ultron":
                        return

                    # Only process messages that begin with a recognized command.
                    valid_commands = [
                        "!weather", "!yt", "!search", "!chat", "!news", "!map",
                        "!pic", "!polly", "!mp3yt", "!help", "!seen", "!greeting",
                        "!stocks", "!crypto", "!timer", "!gif", "!msg", "!doc", "!pod", "!said", "!trump", "!mail", "!blaz"
                    ]
                    if not any(message.startswith(cmd) for cmd in valid_commands):
                        return

                    # Process recognized commands.
                    if message.startswith("!weather"):
                        location = message.split("!weather", 1)[1].strip()
                        self.send_full_message(self.get_weather_response(location))
                    elif message.startswith("!yt"):
                        query = message.split("!yt", 1)[1].strip()
                        self.send_full_message(self.get_youtube_response(query))
                    elif message.startswith("!search"):
                        query = message.split("!search", 1)[1].strip()
                        self.send_full_message(self.get_web_search_response(query))
                    elif message.startswith("!chat"):
                        query = message.split("!chat", 1)[1].strip()
                        self.send_full_message(self.get_chatgpt_response(query, username=sender))
                    elif message.startswith("!news"):
                        topic = message.split("!news", 1)[1].strip()
                        self.send_full_message(self.get_news_response(topic))
                    elif message.startswith("!map"):
                        place = message.split("!map", 1)[1].strip()
                        self.send_full_message(self.get_map_response(place))
                    elif message.startswith("!pic"):
                        query = message.split("!pic", 1)[1].strip()
                        self.send_full_message(self.get_pic_response(query))
                    elif message.startswith("!polly"):
                        parts = message.split(maxsplit=2)
                        if len(parts) < 3:
                            self.send_full_message("Usage: !polly <voice> <text> - Voices are Ruth, Joanna, Danielle, Matthew, Stephen")
                        else:
                            voice = parts[1]
                            text = parts[2]
                            self.handle_polly_command(voice, text)
                    elif message.startswith("!mp3yt"):
                        url = message.split("!mp3yt", 1)[1].strip()
                        self.handle_ytmp3_command(url)
                    elif message.startswith("!help"):
                        self.send_full_message(self.get_help_response())
                    elif message.startswith("!seen"):
                        target_username = message.split("!seen", 1)[1].strip()
                        self.send_full_message(self.get_seen_response(target_username))
                    elif message.startswith("!greeting"):
                        self.handle_greeting_command()
                    elif message.startswith("!stocks"):
                        symbol = message.split("!stocks", 1)[1].strip()
                        self.send_full_message(self.get_stock_price(symbol))
                    elif message.startswith("!crypto"):
                        crypto = message.split("!crypto", 1)[1].strip()
                        self.send_full_message(self.get_crypto_price(crypto))
                    elif message.startswith("!timer"):
                        parts = message.split(maxsplit=3)
                        if len(parts) < 3:
                            self.send_full_message("Usage: !timer <value> <minutes or seconds>")
                        else:
                            value = parts[1]
                            unit = parts[2]
                            self.handle_timer_command(sender, value, unit)
                    elif message.startswith("!gif"):
                        query = message.split("!gif", 1)[1].strip()
                        self.send_full_message(self.get_gif_response(query))
                    elif message.startswith("!msg"):
                        parts = message.split(maxsplit=2)
                        if len(parts) < 3:
                            self.send_full_message("Usage: !msg <username> <message>")
                        else:
                            recipient = parts[1]
                            message = parts[2]
                            self.handle_msg_command(recipient, message, sender)
                    elif message.startswith("!doc"):
                        query = message.split("!doc", 1)[1].strip()
                        self.handle_doc_command(query, sender, public=True)
                    elif message.startswith("!pod"):
                        self.handle_pod_command(sender, message)
                    elif message.startswith("!said"):
                        self.handle_said_command(sender, message)
                        return
                    elif message.startswith("!trump"):
                        trump_text = self.get_trump_post()
                        chunks = self.chunk_message(trump_text, 250)
                        for chunk in chunks:
                            self.send_full_message(chunk)
                        return
                    elif message.startswith("!mail"):
                        self.handle_mail_command(message)
                    elif message.startswith("!blaz"):
                        call_letters = message.split("!blaz", 1)[1].strip()
                        self.handle_blaz_command(call_letters)

        # Update the previous line
        self.previous_line = clean_line

    

    def send_private_message(self, username, message):
        """
        Send a private message to the specified user.
        """
        chunks = self.chunk_message(message, 250)
        for chunk in chunks:
            full_message = f"Whisper to {username} {chunk}"
            asyncio.run_coroutine_threadsafe(self._send_message(full_message + "\r\n"), self.loop)
            outgoing_message_queue.put(full_message)

    

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
            outgoing_message_queue.put(full_message)

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
            return f"{username} was last seen on {last_seen_str} ({hours} hours, {minutes, seconds} seconds ago)."
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

    def load_no_spam_state(self):
        if os.path.exists("nospam_state.json"):
            with open("nospam_state.json", "r") as file:
                data = json.load(file)
                return data.get("nospam", False)
        return False

    def save_no_spam_state(self):
        with open("nospam_state.json", "w") as file:
            json.dump({"nospam": self.no_spam_mode.get()}, file)

    def handle_doc_command(self, query, username, public=False):
        """Handle the !doc command to create a document using ChatGPT and provide an S3 link to the file."""
        if not query:
            if public:
                self.send_full_message(f"Please provide a query for the document, {username}.")
            else:
                self.send_private_message(username, "Please provide a query for the document.")
            return

        # Prepare the prompt for ChatGPT
        prompt = f"Please write a detailed, verbose document based on the following query: {query}"

        try:
            # Get the response from ChatGPT
            response = self.get_chatgpt_document_response(prompt)

            # Save the response to a .txt file
            filename = f"document_{int(time.time())}.txt"
            with open(filename, 'w') as file:
                file.write(response)

            # Upload the file to S3
            s3_client = boto3.client('s3', region_name='us-east-1')
            bucket_name = 'bot-files-repo'
            object_key = filename

            with open(filename, 'rb') as file:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=file,
                    ContentType='text/plain'
                )

            # Generate the S3 URL
            s3_url = f"https://{bucket_name}.s3.amazonaws.com/{object_key}"
            response_message = f"Here is your document: {s3_url}"

            # Delete the local file after uploading
            os.remove(filename)

        except Exception as e:
            response_message = f"Error creating document: {str(e)}"

        # Send the download link to the user
        if public:
            self.send_full_message(response_message)
        else:
            self.send_private_message(username, response_message)

    def get_chatgpt_document_response(self, prompt):
        """Send a prompt to ChatGPT and return the full response as a string."""
        if not self.openai_client:
            return "OpenAI client is not initialized."

        messages = [
            {"role": "system", "content": "You are a writer of detailed, verbose documents."},
            {"role": "user", "content": prompt}
        ]

        try:
            completion = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                n=1,
                max_tokens=10000,  # Allow for longer responses
                temperature=0.2,  # Set temperature
                messages=messages
            )
            gpt_response = completion.choices[0].message.content
        except Exception as e:
            gpt_response = f"Error with ChatGPT API: {str(e)}"

        return gpt_response

    def store_public_message(self, username, message):
        """Store the public message for the given username (keeping only the three most recent)."""
        username = username.lower()
        if username not in self.public_message_history:
            self.public_message_history[username] = []
        # Split the message into lines and store each line separately
        lines = message.split('\n')
        for line in lines:
            self.public_message_history[username].append(line)
        if len(self.public_message_history[username]) > 3:
            self.public_message_history[username] = self.public_message_history[username][-3:]

    def handle_said_command(self, sender, command_text, is_page=False, module_or_channel=None):
        """Handle the !said command to report the last three public messages of a user."""
        parts = command_text.split()
        if len(parts) == 1:
            # No username provided, report the last three things said in the chatroom
            all_messages = []
            for user_messages in self.public_message_history.values():
                all_messages.extend(user_messages)
            all_messages = all_messages[-3:]  # Get the last three messages
            if not all_messages:
                response = "No public messages found."
            else:
                response = "Last three public messages in the chatroom: " + " ".join(all_messages)
        elif len(parts) == 2:
            # Username provided, report the last three messages from that user
            target_username = parts[1].lower()
            if target_username not in self.public_message_history:
                response = f"No public messages found for {target_username}."
            else:
                messages = self.public_message_history[target_username][-3:]  # Get the last three messages
                response = f"Last three public messages from {target_username}: " + " ".join(messages)
        else:
            response = "Usage: !said [<username>]"

        if is_page and module_or_channel:
            self.send_page_response(sender, module_or_channel, response)
        else:
            self.send_full_message(response)

    def handle_public_trigger(self, username, message):
        """
        Handle public message triggers and respond accordingly.
        """
        response = None  # Initialize response with None
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
        elif "!doc" in message:
            query = message.split("!doc", 1)[1].strip()
            self.handle_doc_command(query, username, public=True)
            return  # Exit early to avoid sending a response twice
        elif "!said" in message:
            self.handle_said_command(username, message)
            return
        elif "!pod" in message:
            self.handle_pod_command(username, message)
            return
        elif "!mail" in message:
            self.handle_mail_command(message)
        elif "!blaz" in message:
            call_letters = message.split("!blaz", 1)[1].strip()
            self.handle_blaz_command(call_letters)

        if response:
            self.send_full_message(response)

    def handle_pod_command(self, sender, command_text, is_page=False, module_or_channel=None):
        """Handle the !pod command to fetch podcast episode details."""
        match = re.match(r'!pod\s+"([^"]+)"\s+"([^"]+)"', command_text)
        if not match:
            response = 'Usage: !pod "<show>" "<episode name or number>"'
            if is_page and module_or_channel:
                self.send_page_response(sender, module_or_channel, response)
            else:
                self.send_full_message(response)
            return

        show = match.group(1)
        episode = match.group(2)
        response = self.get_podcast_response(show, episode)
        if is_page and module_or_channel:
            self.send_page_response(sender, module_or_channel, response)
        else:
            self.send_full_message(response)

    def get_podcast_response(self, show, episode):
        """Query the iTunes API for podcast episode details."""
        url = "https://itunes.apple.com/search"
        # Build parameters with a cache-buster parameter
        params = {
            "term": f"{show} {episode}",
            "media": "podcast",
            "entity": "podcastEpisode",
            "limit": 10,  # Increase limit to 10 results
            "cb": int(time.time())  # Cache buster to force a fresh request
        }
        try:
            # Add header to prevent caching
            r = requests.get(url, params=params, headers={"Cache-Control": "no-cache"})
            data = r.json()
            if data["resultCount"] == 0:
                # Retry with just the show name if no results found
                params["term"] = show
                params["cb"] = int(time.time())  # Update cache buster
                r = requests.get(url, params=params, headers={"Cache-Control": "no-cache"})
                data = r.json()
                if data["resultCount"] == 0:
                    return f"No matching episode found for {show} {episode}."

            results = data["results"]
            best_match = None

            # Check if the episode argument is numeric and adjust matching accordingly.
            is_numeric_episode = episode.isdigit()

            for result in results:
                title = result.get("trackName", "").lower()
                description = result.get("description", "").lower()
                if is_numeric_episode:
                    if f"episode {episode}" in title or f"episode {episode}" in description:
                        best_match = result
                        break
                else:
                    if episode.lower() in title or episode.lower() in description:
                        best_match = result
                        break

            if not best_match:
                return f"No matching episode found for {show} {episode}."

            title = best_match.get("trackName", "N/A")
            release_date = best_match.get("releaseDate", "N/A")
            preview_url = best_match.get("previewUrl", "N/A")
            return f"Title: {title}\nRelease Date: {release_date}\nPreview: {preview_url}"
        except Exception as e:
            return f"Error fetching podcast details: {str(e)}"

    def get_trump_post(self):
        """Run the Trump post scraper script and return the latest post."""
        try:
            command = [
                sys.executable,
                r"C:\Users\Noah\OneDrive\Documents\bbschatbot1.0\TrumpsLatestPostScraper.py"
            ]
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=180)
            output = result.stdout.strip()

            if result.returncode != 0:
                # If the script returned a non-zero exit code
                error_msg = result.stderr.strip() or "Unknown error from Trump scraper."
                return f"Error from Trump post script: {error_msg}"

            # Split the output into lines and get the last two lines
            lines = output.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[-2:])
            else:
                return output
        except Exception as e:
            return f"Error running Trump post script: {str(e)}"

    def load_email_credentials(self):
        """Load email credentials from a file."""
        if os.path.exists("email_credentials.json"):
            with open("email_credentials.json", "r") as file:
                return json.load(file)
        return {}

    def send_email(self, recipient, subject, body):
        """Send an email using Gmail."""
        credentials = self.load_email_credentials()
        smtp_server = credentials.get("smtp_server", "smtp.gmail.com")
        smtp_port = credentials.get("smtp_port", 587)
        sender_email = credentials.get("sender_email")
        sender_password = credentials.get("sender_password")

        if not sender_email or not sender_password:
            return "Email credentials are missing."

        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = sender_email
            msg["To"] = recipient

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, [recipient], msg.as_string())

            return f"Email sent to {recipient} successfully."
        except Exception as e:
            return f"Error sending email: {str(e)}"

    def handle_mail_command(self, command_text):
        """Handle the !mail command to send an email."""
        try:
            parts = shlex.split(command_text)
            if len(parts) < 4:
                self.send_full_message("Usage: !mail \"recipient@example.com\" \"Subject\" \"Body\"")
                return

            recipient = parts[1]
            subject = parts[2]
            body = parts[3]
            response = self.send_email(recipient, subject, body)
            self.send_full_message(response)
        except ValueError as e:
            self.send_full_message(f"Error parsing command: {str(e)}")

    def get_pic_response(self, query):
        """Fetch a random picture from Pexels based on the query."""
        key = self.pexels_api_key.get()
        if not key:
            return "Pexels API key is missing."
        elif not query:
            return "Please specify a query."
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
                    return f"No pictures found for '{query}'."
                else:
                    photo_url = photos[0]["src"]["original"]
                    return f"Here is a picture of {query}: {photo_url}"
            except requests.exceptions.RequestException as e:
                return f"Error fetching picture: {str(e)}"

    def handle_blaz_command(self, call_letters):
        """Handle the !blaz command to provide the radio station's live broadcast link based on call letters."""
        radio_links = {
            "WPBG": "https://playerservices.streamtheworld.com/api/livestream-redirect/WPBGFM.mp3",
            "WSWT": "https://playerservices.streamtheworld.com/api/livestream-redirect/WSWTFM.mp3",
            "WMBD": "https://playerservices.streamtheworld.com/api/livestream-redirect/WMBDAM.mp3",
            "WIRL": "https://playerservices.streamtheworld.com/api/livestream-redirect/WIRLAM.mp3",
            "WXCL": "https://playerservices.streamtheworld.com/api/livestream-redirect/WXCLFM.mp3",
            "WKZF": "https://playerservices.streamtheworld.com/api/livestream-redirect/WKZFFM.mp3"
        }
        stream_link = radio_links.get(call_letters.upper(), "No matching radio station found.")
        response = f"Listen to {call_letters.upper()} live: {stream_link}"
        self.send_full_message(response)

    def handle_radio_command(self, query):
        """Handle the !radio command to provide an internet radio station link based on the search query."""
        if not query:
            response = "Please provide a search query in quotes, e.g., !radio \"classic rock\"."
        else:
            # Example implementation using a predefined list of radio stations
            radio_stations = {
                "classic rock": "https://www.classicrockradio.com/stream",
                "jazz": "https://www.jazzradio.com/stream",
                "pop": "https://www.popradio.com/stream",
                "news": "https://www.newsradio.com/stream"
            }
            station_link = radio_stations.get(query.lower(), "No matching radio station found.")
            response = f"Radio station for '{query}': {station_link}"
        self.send_full_message(response)

class BBSBotCLI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_line = 0
        self.buffer_lines = []
        self.scroll_position = 0  # Add scroll position tracking
        self.init_screen()
        self.host = ""
        self.port = 0
        self.loop = asyncio.new_event_loop()
        self.msg_queue = queue.Queue()
        self.partial_line = ""
        self.connected = False
        self.reader = None
        self.writer = None
        self.get_input("Command: ")  # Add this line to prompt for input immediately

    def init_screen(self):
        curses.use_default_colors()
        curses.start_color()
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        
        # Create output window with a border and make it scrollable
        self.output_win = curses.newwin(height - 3, width, 0, 0)
        self.input_win = curses.newwin(3, width, height - 3, 0)
        
        # Enable scrolling for both windows
        self.output_win.scrollok(True)
        self.output_win.idlok(True)
        self.input_win.scrollok(True)
        
        # Enable keypad input for scrolling
        self.output_win.keypad(True)
        self.stdscr.keypad(True)
        
        self.max_lines = height - 5
        self.height = height
        self.width = width
        
        # Initialize color pairs
        self.init_colors()
        
        self.refresh_output("CLI interface active. Type 'exit' or 'quit' to leave.")
        self.get_input("Command: ")  # Add this line to prompt for input immediately

    def init_colors(self):
        """Initialize color pairs for ANSI colors"""
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)

    def refresh_output(self, text):
        """Refresh the output window with buffered content"""
        # Add new text to buffer
        if text:
            new_lines = text.split('\n')
            self.buffer_lines.extend(new_lines)
        
        # Keep buffer size manageable
        if len(self.buffer_lines) > 1000:
            self.buffer_lines = self.buffer_lines[-1000:]
        
        # Calculate visible area
        height, width = self.output_win.getmaxyx()
        start_line = max(0, len(self.buffer_lines) - height + 1 + self.scroll_position)
        end_line = min(start_line + height - 1, len(self.buffer_lines))
        
        # Clear and redraw
        self.output_win.clear()
        
        try:
            # Display each line in the visible area
            for i, line in enumerate(self.buffer_lines[start_line:end_line]):
                y_pos = i
                # Ensure we don't write beyond window boundaries
                if y_pos < height:
                    self.output_win.addstr(y_pos, 0, line[:width-1])
        except curses.error:
            pass  # Ignore curses errors from writing at bottom-right corner
        
        self.output_win.refresh()

    def process_incoming_messages(self):
        """Process incoming messages and update display"""
        while True:
            try:
                data = self.msg_queue.get_nowait()
                if data:
                    # Split data into lines and add to buffer
                    new_lines = data.split('\n')
                    for line in new_lines:
                        if line.strip():  # Only add non-empty lines
                            self.buffer_lines.append(line)
                    
                    # Auto-scroll to bottom when new data arrives
                    self.scroll_position = 0
                    self.refresh_output("")
            except queue.Empty:
                time.sleep(0.1)
            except curses.error:
                continue
            except Exception as e:
                self.buffer_lines.append(f"Error: {str(e)}")
                self.refresh_output("")

    def get_input(self, prompt):
        """Get input from user with support for scrolling"""
        self.input_win.clear()
        self.input_win.border(0)
        self.input_win.addstr(1, 1, prompt)
        self.input_win.refresh()
        
        curses.echo()
        
        # Handle special keys for scrolling
        while True:
            try:
                key = self.stdscr.getch()
                if key == curses.KEY_UP:
                    self.scroll_position = min(self.scroll_position + 1, len(self.buffer_lines) - self.height + 5)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_DOWN:
                    self.scroll_position = max(self.scroll_position - 1, 0)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_PPAGE:  # Page Up
                    self.scroll_position = min(self.scroll_position + self.height - 5, len(self.buffer_lines) - self.height + 5)
                    self.refresh_output("")
                    continue
                elif key == curses.KEY_NPAGE:  # Page Down
                    self.scroll_position = max(self.scroll_position - (self.height - 5), 0)
                    self.refresh_output("")
                    continue
                else:
                    # Normal input handling
                    self.input_win.clear()
                    self.input_win.border(0)
                    self.input_win.addstr(1, 1, prompt)
                    user_input = self.input_win.getstr(1, len(prompt) + 1).decode("utf-8")
                    curses.noecho()
                    return user_input
            except curses.error:
                continue

    def run(self):
        self.host = self.get_input("Enter BBS hostname: ")
        self.port = int(self.get_input("Enter BBS port: "))
        self.refresh_output(f"Connecting to {self.host}:{self.port}...")
        self.start_connection()

        while True:
            try:
                cmd = self.get_input("Command: ")
                self.refresh_output("> " + cmd)
                if cmd.strip().lower() in ['exit', 'quit']:
                    break
                if self.connected and self.writer:
                    asyncio.run_coroutine_threadsafe(self._send_message(cmd + "\r\n"), self.loop)
            except KeyboardInterrupt:
                self.refresh_output("Exiting...")
                break

    def start_connection(self):
        """Start the telnetlib3 client in a background thread."""
        self.stop_event = threading.Event()

        def run_telnet():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.telnet_client_task(self.host, self.port))

        thread = threading.Thread(target=run_telnet, daemon=True)
        thread.start()

        # Start a separate thread to process incoming messages
        threading.Thread(target=self.process_incoming_messages, daemon=True).start()

    async def telnet_client_task(self, host, port):
        """Async function connecting via telnetlib3 (CP437 + ANSI), reading bigger chunks."""
        try:
            reader, writer = await telnetlib3.open_connection(
                host=host,
                port=port,
                term='ansi',
                encoding='cp437',
                cols=136  # Set terminal width to 136 columns
            )
        except Exception as e:
            self.msg_queue.put_nowait(f"Connection failed: {e}\n")
            return

        self.reader = reader
        self.writer = writer
        self.connected = True
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
        if self.writer:
            try:
                self.writer.close()
                await self.writer.drain()  # Ensure the writer is closed properly
            except Exception as e:
                print(f"Error closing writer: {e}")

        self.connected = False
        self.reader = None
        self.writer = None
        self.msg_queue.put_nowait("Disconnected from BBS.\n")

    def display_data(self, data):
        """Display data with extended ASCII and ANSI parsing."""
        ansi_escape_regex = re.compile(r'\x1b\[(\d+)(;\d+)*m')
        clean_data = ansi_escape_regex.sub('', data)  # Strip ANSI codes for now
        
        # Split incoming data into lines
        new_lines = clean_data.split('\n')
        
        # Add to our buffer and refresh display
        for line in new_lines:
            if line.strip():  # Only add non-empty lines
                self.buffer_lines.append(line)
        
        # Keep buffer at a reasonable size
        if len(self.buffer_lines) > 1000:
            self.buffer_lines = self.buffer_lines[-1000:]
        
        # Refresh the display
        height, _ = self.output_win.getmaxyx()
        display_start = max(0, len(self.buffer_lines) - height + 1)
        
        self.output_win.clear()
        try:
            for i, line in enumerate(self.buffer_lines[display_start:display_start + height - 1]):
                self.output_win.addstr(i, 0, line + '\n')
        except curses.error:
            pass  # Ignore overflow errors
        
        self.output_win.refresh()

    async def _send_message(self, message):
        """Coroutine to send a message."""
        self.writer.write(message)
        await self.writer.drain()

def main_cli(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)
    cli = BBSBotCLI(stdscr)
    cli.run()

def main():
    curses.wrapper(main_cli)

if __name__ == "__main__":
    main()
