<<<<<<< HEAD
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
        document.execCommand('cut');
        menu.remove();
    });

    const copy = document.createElement('div');
    copy.textContent = 'Copy';
    copy.style.padding = '5px';
    copy.style.cursor = 'pointer';
    copy.addEventListener('click', () => {
        document.execCommand('copy');
        menu.remove();
    });

    const paste = document.createElement('div');
    paste.textContent = 'Paste';
    paste.style.padding = '5px';
    paste.style.cursor = 'pointer';
    paste.addEventListener('click', () => {
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
document.querySelectorAll('input[type="text"]').forEach(input => {
    input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
});

// Add context menu event listeners to input fields in the Settings window
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#settingsWindow input[type="text"]').forEach(input => {
        input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
    });
});

// Add context menu event listener to the BBS input field
document.getElementById('hostInput').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// Add context menu event listener to the BBS input field
document.getElementById('inputBox').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// ...existing code...
=======
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
        document.execCommand('cut');
        menu.remove();
    });

    const copy = document.createElement('div');
    copy.textContent = 'Copy';
    copy.style.padding = '5px';
    copy.style.cursor = 'pointer';
    copy.addEventListener('click', () => {
        document.execCommand('copy');
        menu.remove();
    });

    const paste = document.createElement('div');
    paste.textContent = 'Paste';
    paste.style.padding = '5px';
    paste.style.cursor = 'pointer';
    paste.addEventListener('click', () => {
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
document.querySelectorAll('input[type="text"]').forEach(input => {
    input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
});

// Add context menu event listeners to input fields in the Settings window
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#settingsWindow input[type="text"]').forEach(input => {
        input.addEventListener('contextmenu', (event) => createContextMenu(event, input));
    });
});

// Add context menu event listener to the BBS input field
document.getElementById('hostInput').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// Add context menu event listener to the BBS input field
document.getElementById('inputBox').addEventListener('contextmenu', (event) => createContextMenu(event, event.target));

// ...existing code...
>>>>>>> 125f854 (added Mud Mode button, keepalive logic)
