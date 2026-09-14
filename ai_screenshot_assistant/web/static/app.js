(function () {
  const sessionId = window.SESSION_ID && window.SESSION_ID !== "__SESSION_ID__"
    ? window.SESSION_ID
    : new URLSearchParams(location.search).get("session_id");
  const statusEl = document.getElementById("status");
  const selectionEl = document.getElementById("selection-status");
  const selectionMessageEl = document.getElementById("selection-message");
  const fullscreenButton = document.getElementById("fullscreen-button");
  const chatCaptureButton = document.getElementById("chat-capture-button");
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
  let activeAssistantText = "";
  let activeDirectRequestId = null;
  let renderScheduled = false;
  let screenshots = [];
  let requestCounter = 0;
  const maxScreenshots = 5;
  const maxChatMessages = 80;
  const maxRenderChars = 100000;

  function nextRequestId(prefix) {
    requestCounter += 1;
    return `${prefix}-${Date.now()}-${requestCounter}`;
  }

  function capText(text) {
    const value = text || "";
    if (value.length <= maxRenderChars) {
      return value;
    }
    return `内容较长，仅显示最后 ${maxRenderChars} 个字符。\n\n` + value.slice(-maxRenderChars);
  }

  function appendTextBlock(container, text) {
    if (!text) {
      return;
    }
    const block = document.createElement("div");
    block.className = "text-block";
    block.textContent = text;
    container.appendChild(block);
  }

  function renderFormattedText(container, text) {
    const value = capText(text);
    container.textContent = "";
    const codePattern = /```([a-zA-Z0-9_+-]*)\s*\n?([\s\S]*?)```/g;
    let lastIndex = 0;
    let match = codePattern.exec(value);
    while (match) {
      appendTextBlock(container, value.slice(lastIndex, match.index));
      const pre = document.createElement("pre");
      pre.className = "code-block";
      const code = document.createElement("code");
      if (match[1]) {
        code.dataset.language = match[1].toLowerCase();
      }
      code.textContent = match[2].trimEnd();
      pre.appendChild(code);
      container.appendChild(pre);
      lastIndex = codePattern.lastIndex;
      match = codePattern.exec(value);
    }
    appendTextBlock(container, value.slice(lastIndex));
  }

  function setOutput(text) {
    renderFormattedText(outputEl, text || "");
  }

  function trimChatMessages() {
    const messages = chatList.querySelectorAll(".chat-message");
    const extra = messages.length - maxChatMessages;
    for (let index = 0; index < extra; index += 1) {
      messages[index].remove();
    }
  }

  function setConnectionStatus(value, online) {
    statusEl.textContent = value;
    statusEl.classList.toggle("online", Boolean(online));
    fullscreenButton.disabled = !online;
    chatCaptureButton.disabled = !online;
    updateAskButton();
  }

  function updateAskButton() {
    const online = socket && socket.readyState === WebSocket.OPEN;
    askButton.disabled = !online || (screenshots.length === 0 && !questionInput.value.trim());
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
    renderFormattedText(content, text);
    bubble.appendChild(content);
    item.appendChild(bubble);
    chatList.appendChild(item);
    trimChatMessages();
    chatList.scrollTop = chatList.scrollHeight;
    return content;
  }

  function startAssistantMessage(requestId) {
    activeChatRequestId = requestId;
    activeAssistantText = "";
    activeAssistantBubble = appendMessage("assistant", "分析中…", 0);
  }

  function scheduleAssistantRender() {
    if (renderScheduled) {
      return;
    }
    renderScheduled = true;
    requestAnimationFrame(function () {
      renderScheduled = false;
      if (activeAssistantBubble) {
        renderFormattedText(activeAssistantBubble, activeAssistantText || "分析中…");
        chatList.scrollTop = chatList.scrollHeight;
      }
    });
  }

  function appendAssistantDelta(requestId, delta) {
    if (!activeAssistantBubble || requestId !== activeChatRequestId) {
      return false;
    }
    activeAssistantText += delta || "";
    scheduleAssistantRender();
    return true;
  }

  function completeAssistantMessage(requestId, text) {
    if (!activeAssistantBubble || requestId !== activeChatRequestId) {
      return false;
    }
    activeAssistantText = text || activeAssistantText || "分析完成";
    renderFormattedText(activeAssistantBubble, activeAssistantText);
    activeChatRequestId = null;
    activeAssistantBubble = null;
    activeAssistantText = "";
    chatList.scrollTop = chatList.scrollHeight;
    return true;
  }

  function failAssistantMessage(message) {
    if (activeAssistantBubble) {
      renderFormattedText(activeAssistantBubble, `错误：${message || "模型调用失败"}`);
      activeChatRequestId = null;
      activeAssistantBubble = null;
      activeAssistantText = "";
      chatList.scrollTop = chatList.scrollHeight;
    }
  }

  function isOutdatedAnswerEvent(event) {
    const requestId = String(event.request_id || "");
    if (requestId.startsWith("fullscreen-")) {
      return requestId !== activeDirectRequestId;
    }
    if (requestId.startsWith("chat-")) {
      return activeChatRequestId !== null && requestId !== activeChatRequestId;
    }
    return false;
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    if (event.type === "selection.status") {
      setSelectionStatus(payload.state, payload.message);
    } else if (event.type === "answer.started") {
      if (isOutdatedAnswerEvent(event)) {
        return;
      }
      buffer = "";
      setSelectionStatus("analyzing", "AI 正在分析，请稍候");
      if (payload.chat) {
        startAssistantMessage(event.request_id);
        setOutput("聊天请求分析中…");
      } else {
        setOutput("分析中…");
      }
    } else if (event.type === "answer.delta") {
      if (isOutdatedAnswerEvent(event)) {
        return;
      }
      buffer += payload.delta || "";
      if (!appendAssistantDelta(event.request_id, payload.delta || "")) {
        setOutput(buffer || "分析中…");
      }
    } else if (event.type === "answer.completed") {
      if (isOutdatedAnswerEvent(event)) {
        return;
      }
      const result = payload.result || {};
      buffer = result.text || buffer || "分析完成";
      if (!completeAssistantMessage(event.request_id, buffer)) {
        setOutput(buffer);
      }
      if (event.request_id === activeDirectRequestId) {
        activeDirectRequestId = null;
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
      if (isOutdatedAnswerEvent(event)) {
        return;
      }
      buffer = "";
      failAssistantMessage(payload.message);
      setOutput(`错误：${payload.message || "模型调用失败"}`);
      if (event.request_id === activeDirectRequestId) {
        activeDirectRequestId = null;
      }
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
    activeDirectRequestId = nextRequestId("fullscreen");
    buffer = "";
    setOutput("分析中…");
    fullscreenButton.disabled = true;
    setSelectionStatus("capturing", "已请求电脑截取全屏");
    socket.send(JSON.stringify({
      type: "command.fullscreen",
      payload: { client_request_id: activeDirectRequestId }
    }));
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        fullscreenButton.disabled = false;
      }
    }, 1500);
  });

  chatCaptureButton.addEventListener("click", function () {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    chatCaptureButton.disabled = true;
    setSelectionStatus("capturing", "已请求电脑截全屏并添加到对话缓冲区");
    socket.send(JSON.stringify({ type: "command.capture_fullscreen" }));
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        chatCaptureButton.disabled = false;
      }
    }, 1500);
  });

  questionInput.addEventListener("input", updateAskButton);

  askButton.addEventListener("click", function () {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const text = questionInput.value.trim();
    if (screenshots.length === 0 && !text) {
      updateAskButton();
      return;
    }
    const images = screenshots.map(function (screenshot) { return screenshot.image; });
    const requestId = nextRequestId("chat");
    activeChatRequestId = requestId;
    activeAssistantBubble = null;
    activeAssistantText = "";
    appendMessage("user", text || "请根据截图作答", images.length);
    fullscreenButton.disabled = true;
    chatCaptureButton.disabled = true;
    askButton.disabled = true;
    setSelectionStatus("analyzing", images.length ? `正在发送 ${images.length} 张截图给 AI` : "正在发送追问给 AI");
    socket.send(JSON.stringify({
      type: "command.submit_screenshots",
      payload: {
        text,
        images,
        conversation: true,
        chat: true,
        client_request_id: requestId
      }
    }));
    questionInput.value = "";
    screenshots = [];
    renderPreviewList();
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        fullscreenButton.disabled = false;
        chatCaptureButton.disabled = false;
        updateAskButton();
      }
    }, 1500);
  });

  renderPreviewList();
  connect();
})();
