// ...existing code...

// Function to load favorites from local storage
function loadFavorites() {
    const storedFavorites = localStorage.getItem('favorites');
    return storedFavorites ? JSON.parse(storedFavorites) : [];
}

// Function to save favorites to local storage
function saveFavorites(favorites) {
    localStorage.setItem('favorites', JSON.stringify(favorites));
}

// Function to update the favorites list
function updateFavoritesList(favorites) {
    const favoritesList = document.getElementById('favoritesList');
    favoritesList.innerHTML = '';
    favorites.forEach(function(address) {
        const listItem = document.createElement('li');
        listItem.textContent = address;
        listItem.addEventListener('click', function() {
            Array.from(favoritesList.children).forEach(item => item.classList.remove('selected'));
            listItem.classList.add('selected');
            document.getElementById('hostInput').value = address; // Populate host name field
        });
        favoritesList.appendChild(listItem);
    });
}

let favorites = loadFavorites();

// Load and set the state of the remember checkboxes
document.addEventListener('DOMContentLoaded', function() {
    const rememberUsername = localStorage.getItem('rememberUsername') === 'true';
    const rememberPassword = localStorage.getItem('rememberPassword') === 'true';
    document.getElementById('rememberUsername').checked = rememberUsername;
    document.getElementById('rememberPassword').checked = rememberPassword;

    if (rememberUsername) {
        document.getElementById('usernameInput').value = localStorage.getItem('username') || '';
    }
    if (rememberPassword) {
        document.getElementById('passwordInput').value = localStorage.getItem('password') || '';
    }

    // Load and set the state of the Google Places API key
    const googlePlacesApiKey = localStorage.getItem('googlePlacesApiKey') || '';
    document.getElementById('googlePlacesApiKey').value = googlePlacesApiKey;

    // Add event listener for the "Split View" button
    document.getElementById('splitViewButton').addEventListener('click', splitView);
});

document.getElementById('toggleModeButton').addEventListener('click', function() {
    const currentMode = document.body.getAttribute('data-mode');
    if (currentMode === 'ansi') {
        document.body.setAttribute('data-mode', 'ripscript');
        console.log('Switched to RIPscript graphics mode');
    } else {
        document.body.setAttribute('data-mode', 'ansi');
        console.log('Switched to ANSI terminal emulation mode');
    }
});

// Add event listener for the "Favorites" button
document.getElementById('favoritesButton').addEventListener('click', function() {
    const favoritesWindow = document.getElementById('favoritesWindow');
    favoritesWindow.style.display = 'block';
    updateFavoritesList(favorites);
});

// Add event listener for the "Close" button in the favorites window
document.getElementById('closeFavoritesButton').addEventListener('click', function() {
    const favoritesWindow = document.getElementById('favoritesWindow');
    favoritesWindow.style.display = 'none';
});

// Function to add a new favorite address
document.getElementById('addFavoriteButton').addEventListener('click', function() {
    const newFavoriteInput = document.getElementById('newFavoriteInput');
    const newAddress = newFavoriteInput.value.trim();
    if (newAddress) {
        favorites.push(newAddress);
        updateFavoritesList(favorites);
        saveFavorites(favorites);
        newFavoriteInput.value = '';
    }
});

// Function to remove the selected favorite address
document.getElementById('removeFavoriteButton').addEventListener('click', function() {
    const favoritesList = document.getElementById('favoritesList');
    const selectedIndex = Array.from(favoritesList.children).findIndex(item => item.classList.contains('selected'));
    if (selectedIndex !== -1) {
        favorites.splice(selectedIndex, 1);
        updateFavoritesList(favorites);
        saveFavorites(favorites);
    }
});

// Function to create a custom context menu
function createContextMenu(event, inputElement) {
    event.preventDefault();

    // Remove any existing context menu
    const existingMenu = document.getElementById('contextMenu');
    if (existingMenu) {
        existingMenu.remove();
    }

    // Create the context menu
    const menu = document.createElement('div');
    menu.id = 'contextMenu';
    menu.style.position = 'absolute';
    menu.style.top = `${event.clientY}px`;
    menu.style.left = `${event.clientX}px`;
    menu.style.backgroundColor = '#fff';
    menu.style.border = '1px solid #ccc';
    menu.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.1)';
    menu.style.zIndex = '1000';

    // Add menu items
    const cut = document.createElement('div');
    cut.textContent = 'Cut';
    cut.style.padding = '5px';
    cut.style.cursor = 'pointer';
    cut.addEventListener('click', () => {
        inputElement.select();
        document.execCommand('cut');
        menu.remove();
    });

    const copy = document.createElement('div');
    copy.textContent = 'Copy';
    copy.style.padding = '5px';
    copy.style.cursor = 'pointer';
    copy.addEventListener('click', () => {
        inputElement.select();
        document.execCommand('copy');
        menu.remove();
    });

    const paste = document.createElement('div');
    paste.textContent = 'Paste';
    paste.style.padding = '5px';
    paste.style.cursor = 'pointer';
    paste.addEventListener('click', () => {
        inputElement.select();
        document.execCommand('paste');
        menu.remove();
    });

    menu.appendChild(cut);
    menu.appendChild(copy);
    menu.appendChild(paste);

    document.body.appendChild(menu);

    // Remove the context menu when clicking elsewhere
    document.addEventListener('click', () => {
        menu.remove();
    }, { once: true });
}

// Add context menu event listeners to input fields
document.querySelectorAll('input[type="text"], input[type="password"]').forEach(input => {
    input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
});

// Add context menu event listeners to input fields in the Settings window
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#settingsWindow input[type="text"], #settingsWindow input[type="password"]').forEach(input => {
        input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
    });
});

// Add context menu event listener to the BBS input field
document.getElementById('hostInput').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// Add context menu event listener to the BBS input field
document.getElementById('inputBox').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// Add event listener for the "Mud Mode" checkbox
document.getElementById('mudModeCheckbox').addEventListener('change', function() {
    const mudMode = document.getElementById('mudModeCheckbox').checked;
    localStorage.setItem('mudMode', mudMode);
});

// Function to send an ENTER keystroke to check chatroom members
function checkChatroomMembers() {
    sendMessage('\r\n');
}

// Function to send a message with optional Mud Mode prefix
function sendMessage(message) {
    checkChatroomMembers(); // Check chatroom members before sending the message
    const mudMode = localStorage.getItem('mudMode') === 'true';
    const prefix = mudMode ? 'Gos ' : '';
    const fullMessage = prefix + message + '\r\n'; // Append carriage return and newline
    const chunks = chunkMessage(fullMessage, 250);
    chunks.forEach(chunk => {
        // Send each chunk to the BBS (implement the actual sending logic)
        console.log('Message sent:', chunk);
    });
}

// Function to chunk a message into 250-character chunks
function chunkMessage(message, chunkSize) {
    const chunks = [];
    for (let i = 0; i < message.length; i += chunkSize) {
        chunks.push(message.slice(i, i + chunkSize));
    }
    return chunks;
}

// Add event listener for the "Send Username" button
document.getElementById('sendUsernameButton').addEventListener('click', function() {
    const username = document.getElementById('usernameInput').value;
    const rememberUsername = document.getElementById('rememberUsername').checked;
    localStorage.setItem('rememberUsername', rememberUsername);
    if (rememberUsername) {
        localStorage.setItem('username', username);
    }
    sendMessage(username + '\r\n'); // Append carriage return and newline
});

// Add event listener for the "Send Password" button
document.getElementById('sendPasswordButton').addEventListener('click', function() {
    const password = document.getElementById('passwordInput').value;
    const rememberPassword = document.getElementById('rememberPassword').checked;
    localStorage.setItem('rememberPassword', rememberPassword);
    if (rememberPassword) {
        localStorage.setItem('password', password);
    }
    sendMessage(password + '\r\n'); // Append carriage return and newline
});

// Save settings when the "Save" button is clicked
document.getElementById('saveSettingsButton').addEventListener('click', function() {
    // ...existing code...

    // Save the Google Places API key
    const googlePlacesApiKey = document.getElementById('googlePlacesApiKey').value;
    localStorage.setItem('googlePlacesApiKey', googlePlacesApiKey);
});

// Function to create a new bot instance
function createBotInstance(containerId) {
    const container = document.getElementById(containerId);
    const botFrame = document.createElement('iframe');
    botFrame.src = 'ui.html'; // Assuming the bot UI is in ui.html
    botFrame.style.width = '100%';
    botFrame.style.height = '100%';
    botFrame.style.border = 'none';
    container.appendChild(botFrame);
}

// Function to split the view
function splitView() {
    const mainContainer = document.getElementById('mainContainer');
    mainContainer.innerHTML = ''; // Clear existing content

    const leftContainer = document.createElement('div');
    leftContainer.id = 'leftContainer';
    leftContainer.style.width = '50%';
    leftContainer.style.height = '100%';
    leftContainer.style.float = 'left';

    const rightContainer = document.createElement('div');
    rightContainer.id = 'rightContainer';
    rightContainer.style.width = '50%';
    rightContainer.style.height = '100%';
    rightContainer.style.float = 'left';

    mainContainer.appendChild(leftContainer);
    mainContainer.appendChild(rightContainer);

    createBotInstance('leftContainer');
    createBotInstance('rightContainer');
}

// Function to handle the Teleconference button click
document.getElementById('teleconferenceButton').addEventListener('click', function() {
    sendMessage('/go teleconference');
});

// ...existing code...
