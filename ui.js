// ...existing code...

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

    // Load and set the state of the Logon Automation checkbox
    const logonAutomation = localStorage.getItem('logonAutomation') === 'true';
    document.getElementById('logonAutomation').checked = logonAutomation;

    // Load and set the state of the Auto Login checkbox
    const autoLogin = localStorage.getItem('autoLogin') === 'true';
    document.getElementById('autoLogin').checked = autoLogin;

    // Load and set the state of the Giphy API key
    const giphyApiKey = localStorage.getItem('giphyApiKey') || '';
    document.getElementById('giphyApiKey').value = giphyApiKey;

    // Add event listener for the "Split View" button
    document.getElementById('splitViewButton').addEventListener('click', splitView);

    // Add event listener for the "Teleconference" button
    document.getElementById('teleconferenceButton').addEventListener('click', startTeleconference);

    // Add context menus to input fields
    addContextMenu(document.getElementById('hostInput'));
    addContextMenu(document.getElementById('usernameInput'));
    addContextMenu(document.getElementById('passwordInput'));
    addContextMenu(document.getElementById('inputBox'));
    addContextMenu(document.getElementById('googlePlacesApiKey'));
    addContextMenu(document.getElementById('giphyApiKey'));
});

// Save settings when the "Save" button is clicked
document.getElementById('saveSettingsButton').addEventListener('click', function() {
    // ...existing code...

    // Save the Google Places API key
    const googlePlacesApiKey = document.getElementById('googlePlacesApiKey').value;
    localStorage.setItem('googlePlacesApiKey', googlePlacesApiKey);

    // Save the state of the Logon Automation checkbox
    const logonAutomation = document.getElementById('logonAutomation').checked;
    localStorage.setItem('logonAutomation', logonAutomation);

    // Save the state of the Auto Login checkbox
    const autoLogin = document.getElementById('autoLogin').checked;
    localStorage.setItem('autoLogin', autoLogin);

    // Save the Giphy API key
    const giphyApiKey = document.getElementById('giphyApiKey').value;
    localStorage.setItem('giphyApiKey', giphyApiKey);
});

// ...existing code...

function splitView() {
    // Implement split view logic here
    const mainContainer = document.getElementById('mainContainer');
    const clone = mainContainer.cloneNode(true);
    mainContainer.parentNode.appendChild(clone);
    console.log("Split View button clicked");
}

function startTeleconference() {
    // Implement teleconference logic here
    sendMessage('/go tele');
    console.log("Teleconference button clicked");
}

function addContextMenu(inputElement) {
    inputElement.addEventListener('contextmenu', function(event) {
        event.preventDefault();
        const contextMenu = document.createElement('div');
        contextMenu.className = 'context-menu';
        contextMenu.style.position = 'absolute';
        contextMenu.style.top = `${event.clientY}px`;
        contextMenu.style.left = `${event.clientX}px`;
        contextMenu.style.backgroundColor = '#fff';
        contextMenu.style.border = '1px solid #ccc';
        contextMenu.style.boxShadow = '0 0 10px rgba(0, 0, 0, 0.1)';
        contextMenu.style.zIndex = 1000;

        const cutOption = document.createElement('div');
        cutOption.textContent = 'Cut';
        cutOption.addEventListener('click', function() {
            document.execCommand('cut');
            document.body.removeChild(contextMenu);
        });
        contextMenu.appendChild(cutOption);

        const copyOption = document.createElement('div');
        copyOption.textContent = 'Copy';
        copyOption.addEventListener('click', function() {
            document.execCommand('copy');
            document.body.removeChild(contextMenu);
        });
        contextMenu.appendChild(copyOption);

        const pasteOption = document.createElement('div');
        pasteOption.textContent = 'Paste';
        pasteOption.addEventListener('click', function() {
            document.execCommand('paste');
            document.body.removeChild(contextMenu);
        });
        contextMenu.appendChild(pasteOption);

        const selectAllOption = document.createElement('div');
        selectAllOption.textContent = 'Select All';
        selectAllOption.addEventListener('click', function() {
            document.execCommand('selectAll');
            document.body.removeChild(contextMenu);
        });
        contextMenu.appendChild(selectAllOption);

        document.body.appendChild(contextMenu);

        document.addEventListener('click', function() {
            if (contextMenu) {
                document.body.removeChild(contextMenu);
            }
        }, { once: true });
    });
}

// ...existing code...
