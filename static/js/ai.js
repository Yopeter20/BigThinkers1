// BigThinkers AI — chat.js
document.addEventListener("DOMContentLoaded", function () {
  const chat = document.getElementById("btAiChat");
  const form = document.getElementById("btAiForm");
  const input = document.getElementById("btAiInput");
  const loading = document.getElementById("btAiLoading");
  const clearBtn = document.getElementById("btAiClear");

  if (!form) return;

  function addMessage(text, sender) {
    const msg = document.createElement("div");
    msg.className = "bt-ai-message " + (sender === "user" ? "bt-ai-user" : "bt-ai-bot");
    const p = document.createElement("p");
    p.textContent = text;
    msg.appendChild(p);
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    addMessage(message, "user");
    input.value = "";
    loading.style.display = "flex";

    try {
      const response = await fetch("/ai/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message }),
      });
      const data = await response.json();
      loading.style.display = "none";

      if (data.reply) {
        addMessage(data.reply, "bot");
      } else if (data.error) {
        addMessage(data.error, "bot");
      }
    } catch (err) {
      loading.style.display = "none";
      addMessage("Something went wrong. Please try again.", "bot");
    }
  });

  if (clearBtn) {
    clearBtn.addEventListener("click", function () {
      chat.innerHTML = "";
      addMessage("Conversation cleared. How can I help you now?", "bot");
    });
  }
});
