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
