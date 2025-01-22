# BBS Chat Bot

BBS Chat Bot is a Python application that functions as a BBS Teleconference Bot. The application provides a graphical user interface (GUI) built with Tkinter, allowing users to configure connection settings, toggle modes, and manage favorite BBS addresses.

## Features

- Connect to a BBS using a specified host and port.
- Toggle between ANSI and plain text terminal emulation modes.
- Manage favorite BBS addresses with the ability to add and remove favorites.
- Save and load favorite addresses from local storage.
- Use `!search <keyword>` for web searches.
- Use `!chat <query>` for ChatGPT requests.
- Use `!weather <city or zip>` to fetch weather information.
- Use `!yt <query>` for YouTube searches.
- Use `!news <topic>` for news searches via newsapi.org.
- Use `!map <place>` to fetch place information from Google Places API.

## Requirements

- Python 3.x
- Tkinter (usually included with Python)
- `asyncio` for asynchronous operations

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/bbs-chat-bot.git
    cd bbs-chat-bot
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

## Usage

1. Run the application:
    ```sh
    python BBSCHATBOT1.1.py
    ```

2. Use the GUI to enter the BBS host and port, then click "Connect" to establish a connection.

3. Toggle between ANSI and plain text modes using the "Toggle Mode" button.

4. Manage your favorite BBS addresses using the "Favorites" button. Add new addresses or remove existing ones.

5. Open the Settings window to configure API keys and other settings required for the various `!triggers` to work:
    - **OpenAI API Key**: Required for the `!chat` trigger to interact with ChatGPT.
    - **Weather API Key**: Required for the `!weather` trigger to fetch weather information.
    - **YouTube API Key**: Required for the `!yt` trigger to perform YouTube searches.
    - **Google CSE API Key**: Required for the `!search` trigger to perform Google Custom Searches.
    - **Google CSE ID (cx)**: Required for the `!search` trigger to perform Google Custom Searches.
    - **News API Key**: Required for the `!news` trigger to fetch news headlines.
    - **Google Places API Key**: Required for the `!map` trigger to fetch place information.

## File Structure

- [BBSCHATBOT1.1.py](http://_vscodecontentref_/0): Main application script.
- [ui.html](http://_vscodecontentref_/1): HTML file for the GUI.
- [ui.js](http://_vscodecontentref_/2): JavaScript file for handling UI interactions.
- [settings.json](http://_vscodecontentref_/3): VS Code settings for the project.
- [favorites.json](http://_vscodecontentref_/4): JSON file to store favorite BBS addresses.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
