
async function sendTabActivity(tab) {
    if (!tab || !tab.url) return;

    // Ignore browser internal pages
    if (
        tab.url.startsWith("chrome://") ||
        tab.url.startsWith("brave://") ||
        tab.url.startsWith("edge://") ||
        tab.url.startsWith("about:")
    ) {
        return;
    }

    try {
        const url = new URL(tab.url);

        const activity = {
            browser: "Chromium Browser",
            title: tab.title || "Unknown",
            url: tab.url,
            domain: url.hostname
        };

        await fetch("http://127.0.0.1:8765/activity", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(activity)
        });

        console.log("LabSphere activity sent:", activity);

    } catch (error) {
        console.error("LabSphere browser error:", error);
    }
}

// Detect tab switching
chrome.tabs.onActivated.addListener(async (info) => {
    const tab = await chrome.tabs.get(info.tabId);
    sendTabActivity(tab);
});

// Detect navigation within an active tab
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (
        changeInfo.status === "complete" &&
        tab.active
    ) {
        sendTabActivity(tab);
    }
});
