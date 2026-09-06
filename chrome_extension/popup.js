chrome.runtime.sendMessage({ type: 'get_status' }, (res) => {
    if (!res) return;
    const dot = document.getElementById('dot');
    const status = document.getElementById('status');
    const cmds = document.getElementById('cmds');
    const err = document.getElementById('err');

    dot.className = 'dot ' + (res.connected ? 'on' : 'off');
    status.textContent = res.connected ? 'Connected' : 'Offline';
    cmds.textContent = res.commandsExecuted;
    if (res.lastError) err.textContent = res.lastError;
});

document.getElementById('pair').addEventListener('click', async () => {
    const input = document.getElementById('token');
    const token = input.value.trim();
    if (!/^[0-9a-f]{64}$/.test(token)) {
        document.getElementById('err').textContent = 'Paste the 64-character extension-token.';
        return;
    }
    await chrome.storage.local.set({ bridgeToken: token });
    input.value = '';
    document.getElementById('err').textContent = 'Pairing saved. Reconnecting...';
});
