// BigThinkers — individual chat (direct messages)
document.addEventListener("DOMContentLoaded", function () {
  const chatWindow = document.getElementById("btChatWindow");
  const form = document.getElementById("btChatForm");
  const input = document.getElementById("btChatInput");
  if (!chatWindow || !form) return;

  const partnerId = chatWindow.dataset.partnerId;
  const currentUserId = chatWindow.dataset.currentUserId;
  let lastId = parseInt(chatWindow.dataset.lastId || "0", 10);

  chatWindow.scrollTop = chatWindow.scrollHeight;

  function appendMessage(msg) {
    if (chatWindow.querySelector('[data-id="' + msg.id + '"]')) return;

    const emptyNotice = chatWindow.querySelector(".bt-empty");
    if (emptyNotice) emptyNotice.remove();

    const div = document.createElement("div");
    const isMine = String(msg.sender_id) === String(currentUserId);
    div.className = "bt-ai-message " + (isMine ? "bt-ai-user" : "bt-ai-bot");
    div.setAttribute("data-id", msg.id);

    const p = document.createElement("p");
    p.textContent = msg.content;
    div.appendChild(p);

    const time = document.createElement("span");
    time.className = "bt-chat-time";
    time.textContent = msg.created_at;
    div.appendChild(time);

    chatWindow.appendChild(div);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    if (msg.id > lastId) lastId = msg.id;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const content = input.value.trim();
    if (!content) return;
    input.value = "";

    try {
      const res = await fetch("/messages/" + partnerId + "/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content }),
      });
      const data = await res.json();
      if (data.id) appendMessage(data);
    } catch (err) {
      console.error("Failed to send message:", err);
    }
  });

  async function poll() {
    try {
      const res = await fetch("/messages/" + partnerId + "/poll?after=" + lastId);
      const data = await res.json();
      (data.messages || []).forEach(appendMessage);
    } catch (err) {
      // silent — will retry on next interval
    }
  }

  const pollTimer = setInterval(poll, 4000);
  window.addEventListener("beforeunload", function () { clearInterval(pollTimer); });
});
