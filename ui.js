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

    // Add event listener for the "Split View" button
    document.getElementById('splitViewButton').addEventListener('click', splitView);

    // Add event listener for the "Teleconference" button
    document.getElementById('teleconferenceButton').addEventListener('click', startTeleconference);
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
});

// ...existing code...

function splitView() {
    // Implement split view logic here
    console.log("Split View button clicked");
}

function startTeleconference() {
    // Implement teleconference logic here
    console.log("Teleconference button clicked");
}

// ...existing code...
