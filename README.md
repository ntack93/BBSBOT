# BBS Chat Bot

BBS Chat Bot is a Python application that functions as a BBS Teleconference Bot. The application provides a graphical user interface (GUI) built with Tkinter, allowing users to configure connection settings, toggle modes, and manage favorite BBS addresses.

## Features

- Connect to a BBS using a specified host and port.
- Toggle between ANSI and RIPscript terminal emulation modes. *In Development*
- Manage favorite BBS addresses with the ability to add and remove favorites.
- Save and load favorite addresses from local storage.
- Use `!search <keyword>` for web searches.
- Use `!chat <query>` for ChatGPT requests.
- Use `!weather <city or zip>` to fetch weather information.
- Use `!yt <query>` for YouTube searches.
- Use `!news <topic>` for news searches via newsapi.org.
- Use `!map <place>` to fetch place information from Google Places API.
- Use `!pic <query>` to fetch a random picture from Pexels.
- Use `!stocks <symbol>` to fetch the current price of a stock.
- Use `!crypto <symbol>` to fetch the current price of a cryptocurrency.
- Use `!polly <voice> <text>` to convert text to speech using AWS Polly.
- Use `!mp3yt <youtube link>` to download YouTube videos as MP3.
- Use `!gif <query>` to fetch a popular GIF.
- Use `!timer <value> <minutes or seconds>` to set a timer. *still in development*
- Use `!msg <username> <message>` to leave a message for another user.
- **NEW**: Conversation persistence using DynamoDB.
- **NEW**: Split view to create multiple bot instances. *still in development*
- **NEW**: Auto-greeting feature to greet users when they join the chatroom.
- **NEW**: Keep-alive feature to maintain the connection.
- **NEW**: `!nospam` trigger to toggle No Spam Mode on and off.
- **NEW**: `!doc <topic>` to generate a comprehensive document using ChatGPT.

## Requirements

- Python 3.x
- Tkinter (usually included with Python)
- `asyncio` for asynchronous operations
- `boto3` for AWS DynamoDB integration
- `requests` for API requests
- `openai` for ChatGPT integration
- `pytube` for YouTube video downloads
- `pydub` for audio processing
- `subprocess` for running external commands

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/bbschatbot.git
    cd bbschatbot
    ```

2. Install the required Python packages:
    ```sh
    pip install -r requirements.txt
    ```

3. Create `username.json` and `password.json` files in the project directory:
    ```json
    // username.json
    "your_username"
    ```

    ```json
    // password.json
    "your_password"
    ```

## API Setup

To use the various `!triggers` in the bot, you need to set up API keys for different services. Here is a high-level overview of how to obtain these keys:

### OpenAI API Key

1. Sign up for an account at [OpenAI](https://www.openai.com/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "OpenAI API Key".

### Weather API Key

1. Sign up for an account at [OpenWeatherMap](https://openweathermap.org/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "Weather API Key".

### YouTube API Key

1. Sign up for an account at [Google Cloud Platform](https://cloud.google.com/).
2. Create a new project and enable the YouTube Data API v3.
3. Generate an API key for the project.
4. Copy the API key and enter it in the Settings window under "YouTube API Key".

### Google Custom Search API Key and ID (cx)

1. Sign up for an account at [Google Cloud Platform](https://cloud.google.com/).
2. Create a new project and enable the Custom Search API.
3. Generate an API key for the project.
4. Go to the [Custom Search Engine](https://cse.google.com/cse/) and create a new search engine.
5. Copy the Search Engine ID (cx) and the API key.
6. Enter the API key in the Settings window under "Google CSE API Key".
7. Enter the Search Engine ID (cx) in the Settings window under "Google CSE ID (cx)".

### News API Key

1. Sign up for an account at [NewsAPI](https://newsapi.org/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "News API Key".

### Google Places API Key

1. Sign up for an account at [Google Cloud Platform](https://cloud.google.com/).
2. Create a new project and enable the Places API.
3. Generate an API key for the project.
4. Copy the API key and enter it in the Settings window under "Google Places API Key".

### Pexels API Key

1. Sign up for an account at [Pexels](https://www.pexels.com/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "Pexels API Key".

### Alpha Vantage API Key

1. Sign up for an account at [Alpha Vantage](https://www.alphavantage.co/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "Alpha Vantage API Key".

### CoinMarketCap API Key

1. Sign up for an account at [CoinMarketCap](https://coinmarketcap.com/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "CoinMarketCap API Key".

### Giphy API Key

1. Sign up for an account at [Giphy](https://developers.giphy.com/).
2. Navigate to the API section and generate a new API key.
3. Copy the API key and enter it in the Settings window under "Giphy API Key".

## DynamoDB Setup

To enable conversation persistence using DynamoDB, follow these steps:

1. Sign up for an account at [AWS](https://aws.amazon.com/).
2. Navigate to the DynamoDB service in the AWS Management Console.
3. Create a new table with the following settings:
    - **Table name**: `ChatBotConversations`
    - **Primary key**:
        - **Partition key**: `username` (Type: String)
        - **Sort key**: `timestamp` (Type: Number)
4. Create another table for chat members with the following settings:
    - **Table name**: `ChatRoomMembers`
    - **Primary key**:
        - **Partition key**: `room` (Type: String)
5. Create another table for pending messages with the following settings:
    - **Table name**: `PendingMessages`
    - **Primary key**:
        - **Partition key**: `recipient` (Type: String)
        - **Sort key**: `timestamp` (Type: Number)
6. Configure your AWS credentials:
    - Install the AWS CLI: [AWS CLI Installation](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
    - Configure the AWS CLI with your credentials:
        ```sh
        aws configure
        ```
    - Enter your AWS Access Key ID, Secret Access Key, region (e.g., `us-east-1`), and output format (e.g., `json`).

## Usage

1. Run the application:
    ```sh
    python jeremy.py
    ```

2. Use the GUI to enter the BBS host and port, then click "Connect" to establish a connection.

3. Toggle between ANSI and RIPscript modes using the "Toggle Mode" button. *still in dev*

4. Manage your favorite BBS addresses using the "Favorites" button. Add new addresses or remove existing ones.

5. Open the Settings window to configure API keys and other settings required for the various `!triggers` to work:
    - **OpenAI API Key**: Required for the `!chat` trigger to interact with ChatGPT.
    - **Weather API Key**: Required for the `!weather` trigger to fetch weather information.
    - **YouTube API Key**: Required for the `!yt` trigger to perform YouTube searches.
    - **Google CSE API Key**: Required for the `!search` trigger to perform Google Custom Searches.
    - **Google CSE ID (cx)**: Required for the `!search` trigger to perform Google Custom Searches.
    - **News API Key**: Required for the `!news` trigger to fetch news headlines.
    - **Google Places API Key**: Required for the `!map` trigger to fetch place information.
    - **Pexels API Key**: Required for the `!pic` trigger to fetch random pictures.
    - **Alpha Vantage API Key**: Required for the `!stocks` trigger to fetch stock prices.
    - **CoinMarketCap API Key**: Required for the `!crypto` trigger to fetch cryptocurrency prices.
    - **Giphy API Key**: Required for the `!gif` trigger to fetch popular GIFs.

6. To ensure you receive responses to your queries without interruption, turn on unlimited pages by sending:
    ```sh
    /P OK
    ```

## File Structure

- `jeremy.py`: Main application script.
- `doctriggerversion.py`: Alternate version of the bot with document generation trigger.
- `ultron(MacOS).py`: MacOS-specific version of the bot.
- `README.md`: This README file.
- `requirements.txt`: List of required Python packages.
- `api_keys.json`: JSON file to store API keys.
- `favorites.json`: JSON file to store favorite BBS addresses.
- `username.json`: JSON file to store the username.
- `password.json`: JSON file to store the password.
- `last_seen.json`: JSON file to store the last seen timestamps of users.
- `nospam_state.json`: JSON file to store the No Spam Mode state.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
