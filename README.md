# BBS Chat Bot

BBS Chat Bot is a Python application that functions as a BBS Teleconference Bot with the purpose of bringing modern amenities to the teleconference module. It's multi-function operation works via a !trigger system.

## Features

- **BBS Connection:** Connect to a BBS using a specified host and port.
- **Favorites Management:** Add, remove, and load favorite BBS addresses.
- **Web Search:** Use `!search <keyword>` for Google Custom Searches.
- **ChatGPT Interaction:** Use `!chat <query>` to communicate with ChatGPT.
- **Weather Information:** Use `!weather <city or zip>` to fetch current weather data.
- **YouTube Search:** Use `!yt <query>` for YouTube searches.
- **News Headlines:** Use `!news <topic>` to get news headlines via NewsAPI.
- **Map Lookup:** Use `!map <place>` to retrieve place information from Google Places API.
- **Picture Search:** Use `!pic <query>` to get a random picture from Pexels.
- **Stock Prices:** Use `!stocks <symbol>` for the current price of a stock.
- **Cryptocurrency Prices:** Use `!crypto <symbol>` for cryptocurrency price data.
- **Text-to-Speech:** Use `!polly <voice> <text>` to convert text to speech with AWS Polly.
- **YouTube to MP3:** Use `!mp3yt <youtube link>` to download YouTube videos as MP3.
- **GIF Search:** Use `!gif <query>` to fetch a popular GIF.
- **Timer:** Use `!timer <value> <minutes or seconds>` to set a timer. 
- **Private Messaging:** Use `!msg <username> <message>` to leave a message for another user.
- **Conversation Persistence:** Save conversations using DynamoDB.
- **Split View:** Create multiple bot instances in one interface. *(Still in Development)*
- **Auto-Greeting:** Automatically greet new users in the chatroom.
- **Keep-Alive:** Maintains the connection with periodic messages.
- **No Spam Mode:** Prevents the bot from responding to public triggers with `!nospam`.
- **Document Generation:** Use `!doc <topic>` to generate a detailed document using ChatGPT.
- **Trump's Latest Post:** Use `!trump` to fetch and display Donald Trump's latest post from Truth Social.
- **NEW – !said Command:** In public chat, type `!said <username>` to display the three most recent public messages from that user or !said by itself for the last three messages sent to the chatroom in general.
- **Email Sending:** Use `!mail "recipient@example.com" "Subject" "Body"` to send an email using Gmail.

## Requirements

- Python 3.x  
- Tkinter (usually included with Python)  
- asyncio  
- boto3 (for AWS DynamoDB integration)  
- requests (for API requests)  
- openai (for ChatGPT integration)  
- pytube (for YouTube video downloads)  
- pydub (for audio processing)  
- subprocess (for running external commands)
- smtplib (for sending emails)

## Installation

1. **Clone the repository:**

   ```sh
   git clone https://github.com/ntack93/BBSBOT.git  
   cd BBSBOT
   ```

2. **Install the required Python packages:**

   ```sh
   pip install -r requirements.txt
   ```

3. **Create configuration files:**  
   Create `username.json`, `password.json`, and `email_credentials.json` in the project directory containing your credentials. For example:

   For `username.json`:  
   ```json
   "your_username"
   ```

   For `password.json`:  
   ```json
   "your_password"
   ```

   For `email_credentials.json`:  
   ```json
   {
       "smtp_server": "smtp.gmail.com",
       "smtp_port": 587,
       "sender_email": "your-email@gmail.com",
       "sender_password": "your-email-password"
   }
   ```

## API Setup

To enable the various triggers, obtain API keys from these services and enter them via the Settings window:

- **OpenAI API Key:** Sign up at OpenAI, generate an API key, and enter it under "OpenAI API Key".  
- **Weather API Key:** Sign up at OpenWeatherMap, generate an API key, and enter it under "Weather API Key".  
- **YouTube API Key:** Sign up at Google Cloud Platform, enable the YouTube Data API v3, generate an API key, and enter it under "YouTube API Key".  
- **Google Custom Search API Key and ID (cx):** Enable the Custom Search API in Google Cloud Platform, generate an API key, create a search engine via the Custom Search Engine page, then enter the API key under "Google CSE API Key" and the Search Engine ID under "Google CSE ID (cx)".  
- **News API Key:** Sign up at NewsAPI, generate an API key, and enter it under "News API Key".  
- **Google Places API Key:** Enable the Places API in Google Cloud Platform, generate an API key, and enter it under "Google Places API Key".  
- **Pexels API Key:** Sign up at Pexels, generate an API key, and enter it under "Pexels API Key".  
- **Alpha Vantage API Key:** Sign up at Alpha Vantage, generate an API key, and enter it under "Alpha Vantage API Key".  
- **CoinMarketCap API Key:** Sign up at CoinMarketCap, generate an API key, and enter it under "CoinMarketCap API Key".  
- **Giphy API Key:** Sign up at Giphy, generate an API key, and enter it under "Giphy API Key".

## DynamoDB Setup

For conversation persistence and user management, set up the following tables in AWS DynamoDB:

- **ChatBotConversations**  
  - Partition key: `username` (String)  
  - Sort key: `timestamp` (Number)

- **ChatRoomMembers**  
  - Partition key: `room` (String)

- **PendingMessages**  
  - Partition key: `recipient` (String)  
  - Sort key: `timestamp` (Number)

Configure your AWS credentials using:

   ```sh
   aws configure
   ```

and follow the prompts.

## Usage

1. **Run the application:**

   ```sh
   python ultronprealpha.py
   ```

   *Note: Although the main script is named "ultronprealpha.py", the bot’s persona is Ultron.*

2. **Connect to a BBS:**  
   Enter the BBS host and port in the GUI and click "Connect".

3. **Public vs. Private Chat:**  
   - In public chat, the bot only responds when a recognized trigger is present.  
   - Private (whispered or paged) messages without an explicit trigger are automatically treated as `!chat` commands.  
   - The bot does not respond to its own messages.

4. **Using the New !said Command:**  
   In public chat, type:

   ```sh
   !said <username>
   ```

   to retrieve and display the three most recent public messages from that user.

5. **Using the New !mail Command:**  
   In public chat, type:

   ```sh
   !mail "recipient@example.com" "Subject" "Body"
   ```

   to send an email using Gmail.

6. **Other Commands:**  
   Refer to the Features section for a complete list of available commands.

7. **Additional Settings:**  
   Use the Settings window to configure API keys and preferences.  
   Use the Favorites window to manage your favorite BBS addresses.  
   To ensure uninterrupted query responses, send the command `/P OK` in the chat to enable unlimited pages.

## File Structure

- ultronprealpha.py: Main application script.
- ultron(MacOS).py: MacOS-specific version of the bot.
- README.md: This README file.
- requirements.txt: List of required Python packages.
- api_keys.json: Stores API keys.
- favorites.json: Stores favorite BBS addresses.
- username.json: Stores the username.
- password.json: Stores the password.
- email_credentials.json: Stores email credentials.
- last_seen.json: Stores the last seen timestamps for users.
- nospam_state.json: Stores the state of No Spam Mode.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
