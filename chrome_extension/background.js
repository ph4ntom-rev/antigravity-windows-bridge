const BRIDGE = 'http://127.0.0.1:13371';
const POLL_MS = 300;
const OFFLINE_POLL_MS = 2000;

let connected = false;
let commandsExecuted = 0;
let lastError = null;
let polling = false;
let token = '';
chrome.storage.local.setAccessLevel({ accessLevel: 'TRUSTED_CONTEXTS' });
chrome.storage.local.get('bridgeToken').then(v => { token = v.bridgeToken || ''; });
chrome.storage.onChanged.addListener(changes => { if (changes.bridgeToken) token = changes.bridgeToken.newValue || ''; });

function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
}

async function postResult(cmdId, result) {
    const response = await fetch(`${BRIDGE}/api/ext/result`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ id: cmdId, result }),
        signal: AbortSignal.timeout(5000)
    });
    if (!response.ok) throw new Error(`Result rejected (${response.status}); inspect state before retrying`);
}

async function executeCommand(cmd) {
    try {
        if (!Number.isFinite(cmd.deadline_ms) || Date.now() >= cmd.deadline_ms) throw new Error("Command expired before execution");
        switch (cmd.type) {
            case 'list_tabs': {
                const tabs = await chrome.tabs.query({});
                return {
                    tabs: tabs.map(t => ({
                        id: t.id, url: t.url, title: t.title,
                        active: t.active, windowId: t.windowId,
                        index: t.index, pinned: t.pinned, status: t.status
                    })),
                    count: tabs.length
                };
            }
            case 'eval_js': {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: cmd.tab_id },
                    world: 'MAIN',
                    func: (code) => {
                        try {
                            const r = eval(code);
                            if (r === undefined) return { type: 'undefined' };
                            if (r instanceof Element) return { type: 'element', tag: r.tagName, id: r.id, text: r.innerText?.substring(0, 2000) };
                            return { type: typeof r, value: r };
                        } catch (e) {
                            return { type: 'error', error: e.message };
                        }
                    },
                    args: [cmd.js_code]
                });
                return { success: true, result: results[0]?.result };
            }
            case 'capture_tab': {
                const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 85 });
                return { success: true, screenshot: dataUrl };
            }
            case 'navigate': {
                const tab = await chrome.tabs.update(cmd.tab_id, { url: cmd.url });
                return { success: true, tab: { id: tab.id, url: tab.url, title: tab.title } };
            }
            case 'create_tab': {
                const tab = await chrome.tabs.create({ url: cmd.url || 'about:blank' });
                return { success: true, tab: { id: tab.id, url: tab.url } };
            }
            case 'close_tab': {
                await chrome.tabs.remove(cmd.tab_id);
                return { success: true };
            }
            default:
                return { __error__: `Unknown command: ${cmd.type}` };
        }
    } catch (e) {
        return { __error__: e.message };
    }
}

async function startPolling() {
    if (polling) return;
    polling = true;
    console.log('[Antigravity] Polling started');

    while (polling) {
        try {
            if (!token) throw new Error('Pair this extension with its extension-token file');
            const resp = await fetch(`${BRIDGE}/api/ext/poll`, {
                headers: { Authorization: `Bearer ${token}` },
                signal: AbortSignal.timeout(2000)
            });
            if (!resp.ok) throw new Error(`Bridge rejected connection (${resp.status})`);
            const data = await resp.json();
            connected = true;
            lastError = null;

            if (data.command) {
                const result = await executeCommand(data.command);
                await postResult(data.command.id, result);
                commandsExecuted++;
            }
            await sleep(POLL_MS);
        } catch (e) {
            connected = false;
            lastError = e.message;
            await sleep(OFFLINE_POLL_MS);
        }
    }
}

// Status for popup
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'get_status') {
        sendResponse({ connected, lastError, commandsExecuted });
    }
    return true;
});

// Keepalive — restart polling if SW was killed
chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener(() => startPolling());
chrome.runtime.onStartup.addListener(() => startPolling());
chrome.runtime.onInstalled.addListener(() => startPolling());

startPolling();
