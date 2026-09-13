(function () {
  const sessionId = window.SESSION_ID && window.SESSION_ID !== "__SESSION_ID__"
    ? window.SESSION_ID
    : new URLSearchParams(location.search).get("session_id");
  const statusEl = document.getElementById("status");
  const selectionEl = document.getElementById("selection-status");
  const selectionMessageEl = document.getElementById("selection-message");
  const fullscreenButton = document.getElementById("fullscreen-button");
  const questionInput = document.getElementById("question-input");
  const askButton = document.getElementById("ask-button");
  const chatList = document.getElementById("chat-list");
  const previewList = document.getElementById("preview-list");
  const previewCount = document.getElementById("preview-count");
  const outputEl = document.getElementById("output");
  const cursorKey = `lastEventId:${sessionId || "missing"}`;
  let lastEventId = Number(localStorage.getItem(cursorKey) || 0);
  let reconnectMs = 1000;
  let buffer = "";
  let socket = null;
  let activeChatRequestId = null;
  let activeAssistantBubble = null;
  let screenshots = [];
  const maxScreenshots = 5;

  function setConnectionStatus(value, online) {
    statusEl.textContent = value;
    statusEl.classList.toggle("online", Boolean(online));
    fullscreenButton.disabled = !online;
    updateAskButton();
  }

  function updateAskButton() {
    const online = socket && socket.readyState === WebSocket.OPEN;
    askButton.disabled = !online || screenshots.length === 0;
  }

  function setSelectionStatus(state, message) {
    selectionEl.className = `selection-status ${state || "waiting"}`;
    selectionMessageEl.textContent = message || "等待操作";
  }

  function clearEmptyChat() {
    const empty = chatList.querySelector(".empty-chat");
    if (empty) {
      empty.remove();
    }
  }

  function renderPreviewList() {
    previewCount.textContent = `已截图：${screenshots.length}张`;
    previewList.textContent = "";
    screenshots.forEach(function (screenshot, index) {
      const item = document.createElement("div");
      item.className = "preview-item";
      const image = document.createElement("img");
      image.src = screenshot.image;
      image.alt = `截图 ${index + 1}`;
      const remove = document.createElement("button");
      remove.className = "preview-remove";
      remove.type = "button";
      remove.setAttribute("aria-label", `删除截图 ${index + 1}`);
      remove.textContent = "×";
      remove.addEventListener("click", function () {
        screenshots.splice(index, 1);
        renderPreviewList();
        updateAskButton();
      });
      item.appendChild(image);
      item.appendChild(remove);
      previewList.appendChild(item);
    });
  }

  function appendMessage(role, text, imageCount) {
    clearEmptyChat();
    const item = document.createElement("div");
    item.className = `chat-message ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    if (imageCount) {
      const attachment = document.createElement("div");
      attachment.className = "attachment-chip";
      attachment.textContent = `已附带 ${imageCount} 张截图`;
      bubble.appendChild(attachment);
    }
    const content = document.createElement("div");
    content.className = "chat-content";
    content.textContent = text;
    bubble.appendChild(content);
    item.appendChild(bubble);
    chatList.appendChild(item);
    chatList.scrollTop = chatList.scrollHeight;
    return content;
  }

  function startAssistantMessage(requestId) {
    activeChatRequestId = requestId;
    activeAssistantBubble = appendMessage("assistant", "分析中…", 0);
  }

  function appendAssistantDelta(requestId, delta) {
    if (!activeAssistantBubble || requestId !== activeChatRequestId) {
      return false;
    }
    if (activeAssistantBubble.textContent === "分析中…") {
      activeAssistantBubble.textContent = "";
    }
    activeAssistantBubble.textContent += delta || "";
    chatList.scrollTop = chatList.scrollHeight;
    return true;
  }

  function completeAssistantMessage(requestId, text) {
    if (!activeAssistantBubble || requestId !== activeChatRequestId) {
      return false;
    }
    activeAssistantBubble.textContent = text || activeAssistantBubble.textContent || "分析完成";
    activeChatRequestId = null;
    activeAssistantBubble = null;
    chatList.scrollTop = chatList.scrollHeight;
    return true;
  }

  function failAssistantMessage(message) {
    if (activeAssistantBubble) {
      activeAssistantBubble.textContent = `错误：${message || "模型调用失败"}`;
      activeChatRequestId = null;
      activeAssistantBubble = null;
      chatList.scrollTop = chatList.scrollHeight;
    }
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    if (event.type === "selection.status") {
      setSelectionStatus(payload.state, payload.message);
    } else if (event.type === "answer.started") {
      buffer = "";
      setSelectionStatus("analyzing", "AI 正在分析，请稍候");
      if (payload.chat) {
        startAssistantMessage(event.request_id);
        outputEl.textContent = "聊天请求分析中…";
      } else {
        outputEl.textContent = "分析中…";
      }
    } else if (event.type === "answer.delta") {
      buffer += payload.delta || "";
      if (!appendAssistantDelta(event.request_id, payload.delta || "")) {
        outputEl.textContent = buffer || "分析中…";
      }
    } else if (event.type === "answer.completed") {
      const result = payload.result || {};
      buffer = result.text || buffer || "分析完成";
      if (!completeAssistantMessage(event.request_id, buffer)) {
        outputEl.textContent = buffer;
      }
      setSelectionStatus("completed", "答案已生成，可以继续框选或全屏截题");
    } else if (event.type === "screenshot.captured") {
      if (payload.image) {
        screenshots.push({ image: payload.image, size: payload.size || 0 });
        if (screenshots.length > maxScreenshots) {
          screenshots = screenshots.slice(screenshots.length - maxScreenshots);
        }
        renderPreviewList();
        updateAskButton();
        setSelectionStatus("completed", `已添加截图 ${screenshots.length}/${maxScreenshots}，可继续截图或发送`);
      }
    } else if (event.type === "answer.error") {
      buffer = "";
      failAssistantMessage(payload.message);
      outputEl.textContent = `错误：${payload.message || "模型调用失败"}`;
      setSelectionStatus("error", "分析失败，可以重新框选或全屏截题");
    }
  }

  function connect() {
    if (!sessionId) {
      setConnectionStatus("缺少配对会话", false);
      return;
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws/mobile/${sessionId}?last_event_id=${lastEventId}`);
    socket.onopen = function () {
      reconnectMs = 1000;
      setConnectionStatus("电脑已连接", true);
    };
    socket.onmessage = function (message) {
      const event = JSON.parse(message.data);
      if (event.event_id && event.event_id > lastEventId) {
        lastEventId = event.event_id;
        localStorage.setItem(cursorKey, String(lastEventId));
      }
      handleEvent(event);
    };
    socket.onclose = function () {
      socket = null;
      setConnectionStatus("正在重连", false);
      setTimeout(connect, reconnectMs);
      reconnectMs = Math.min(Math.floor(reconnectMs * 2), 30000);
    };
  }

  fullscreenButton.addEventListener("click", function () {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    fullscreenButton.disabled = true;
    setSelectionStatus("capturing", "已请求电脑截全屏并添加到缓冲区");
    socket.send(JSON.stringify({ type: "command.capture_fullscreen" }));
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        fullscreenButton.disabled = false;
      }
    }, 1500);
  });

  questionInput.addEventListener("input", updateAskButton);

  askButton.addEventListener("click", function () {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const text = questionInput.value.trim();
    if (screenshots.length === 0) {
      updateAskButton();
      return;
    }
    const images = screenshots.map(function (screenshot) { return screenshot.image; });
    appendMessage("user", text || "请根据截图作答", images.length);
    fullscreenButton.disabled = true;
    askButton.disabled = true;
    setSelectionStatus("analyzing", `正在发送 ${images.length} 张截图给 AI`);
    socket.send(JSON.stringify({
      type: "command.submit_screenshots",
      payload: {
        text,
        images,
        conversation: true,
        chat: true
      }
    }));
    questionInput.value = "";
    screenshots = [];
    renderPreviewList();
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        fullscreenButton.disabled = false;
        updateAskButton();
      }
    }, 1500);
  });

  renderPreviewList();
  connect();
})();
