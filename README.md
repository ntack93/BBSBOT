# BBS Chat Bot

BBS Chat Bot is a Python application that functions as a BBS Teleconference Bot. The application provides a graphical user interface (GUI) built with Tkinter, allowing users to configure connection settings, toggle modes, and manage favorite BBS addresses.

## Features

- Connect to a BBS using a specified host and port.
- Toggle between ANSI and RIPscript terminal emulation modes.
- Manage favorite BBS addresses with the ability to add and remove favorites.
- Save and load favorite addresses from local storage.
- Use `!search <keyword>` for web searches.
- Use `!chat <query>` for ChatGPT requests.
- Use `!weather <city or zip>` to fetch weather information.
- Use `!yt <query>` for YouTube searches.
- Use `!news <topic>` for news searches via newsapi.org.

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

## Usage

1. Run the application:
    ```sh
    python BBSCHATBOT1.1.py
    ```

2. Use the GUI to enter the BBS host and port, then click "Connect" to establish a connection.

3. Toggle between ANSI and RIPscript modes using the "Toggle Mode" button.

4. Manage your favorite BBS addresses using the "Favorites" button. Add new addresses or remove existing ones.

5. Open the Settings window to configure API keys and other settings required for the various `!triggers` to work:
    - **OpenAI API Key**: Required for the `!chat` trigger to interact with ChatGPT.
    - **Weather API Key**: Required for the `!weather` trigger to fetch weather information.
    - **YouTube API Key**: Required for the `!yt` trigger to perform YouTube searches.
    - **Google CSE API Key**: Required for the `!search` trigger to perform Google Custom Searches.
    - **Google CSE ID (cx)**: Required for the `!search` trigger to perform Google Custom Searches.
    - **News API Key**: Required for the `!news` trigger to fetch news headlines.

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
