(function () {
  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (err) {}
  }

  const params = new URLSearchParams(location.search);
  const hostKey = location.host || "local";
  const storedPairKey = `pairToken:${hostKey}`;
  const injectedSession = window.SESSION_ID && window.SESSION_ID !== "__SESSION_ID__"
    ? window.SESSION_ID
    : "";
  const injectedPair = window.PAIR_TOKEN && window.PAIR_TOKEN !== "__PAIR_TOKEN__"
    ? window.PAIR_TOKEN
    : "";
  let pairToken = injectedPair || params.get("t") || storageGet(storedPairKey) || "";
  let sessionId = injectedSession || params.get("session_id") || "";
  if (pairToken) {
    storageSet(storedPairKey, pairToken);
  }
  if (pairToken && (location.pathname !== "/pair" || params.get("t") !== pairToken)) {
    history.replaceState(null, "", `/pair?t=${encodeURIComponent(pairToken)}`);
  }
  const statusEl = document.getElementById("status");
  const selectionEl = document.getElementById("selection-status");
  const selectionMessageEl = document.getElementById("selection-message");
  const fullscreenButton = document.getElementById("fullscreen-button");
  const chatCaptureButton = document.getElementById("chat-capture-button");
  const questionInput = document.getElementById("question-input");
  const askButton = document.getElementById("ask-button");
  const clearChatButton = document.getElementById("clear-chat-button");
  const chatList = document.getElementById("chat-list");
  const previewList = document.getElementById("preview-list");
  const previewCount = document.getElementById("preview-count");
  const saveAlbumButton = document.getElementById("save-album-button");
  const selectAllAlbumButton = document.getElementById("select-all-album");
  const albumSheet = document.getElementById("album-sheet");
  const albumSheetImages = document.getElementById("album-sheet-images");
  const albumSheetClose = document.getElementById("album-sheet-close");
  const outputEl = document.getElementById("output");
  const modelHint = document.getElementById("model-hint");
  const modelRoute = document.getElementById("model-route");
  const cursorKey = `lastEventId:${sessionId || "missing"}`;
  const modelTierKey = `modelTier:${pairToken || sessionId || "missing"}`;
  let lastEventId = Number(storageGet(cursorKey) || 0);
  let reconnectMs = 1000;
  let reconnectTimer = null;
  let buffer = "";
  let socket = null;
  let activeChatRequestId = null;
  let activeAssistantBubble = null;
  let activeAssistantText = "";
  let activeDirectRequestId = null;
  let renderScheduled = false;
  let albumItems = [];
  let nextAlbumId = 1;
  let requestCounter = 0;
  const routeAliases = {
    good: "openrouter-qwen-235b",
    high: "openrouter-qwen-235b",
    best: "openrouter-qwen-235b",
    "好": "openrouter-qwen-235b",
    medium: "openrouter-qwen-32b",
    mid: "openrouter-qwen-32b",
    "中等": "openrouter-qwen-32b",
    simple: "deepseek-flash",
    low: "deepseek-flash",
    easy: "deepseek-flash",
    "简单": "deepseek-flash",
    doubao: "doubao-seed-vision",
    "豆包": "doubao-seed-vision",
    "doubao-seed-1-6-vision": "doubao-seed-vision",
    "doubao-seed-1-6-vision-250815": "doubao-seed-vision"
  };
  const knownRoutes = {
    "doubao-seed-vision": "豆包 / doubao-seed-1-6-vision-250815",
    "openrouter-qwen-235b": "OpenRouter / qwen/qwen3-vl-235b-a22b-thinking",
    "openrouter-qwen-32b": "OpenRouter / qwen/qwen3-vl-32b-instruct",
    "openrouter-qwen-8b": "OpenRouter / qwen/qwen3-vl-8b-instruct",
    "deepseek-flash": "DeepSeek / deepseek-flash"
  };
  let currentTier = normalizeRoute(storageGet(modelTierKey) || "openrouter-qwen-235b");
  const maxScreenshots = 5;
  const maxAlbumItems = 12;
  const maxChatMessages = 40;
  const maxRenderChars = 40000;

  function normalizeRoute(value) {
    const key = String(value || "").trim();
    if (knownRoutes[key]) {
      return key;
    }
    if (routeAliases[key]) {
      return routeAliases[key];
    }
    const lowered = key.toLowerCase();
    if (knownRoutes[lowered]) {
      return lowered;
    }
    return routeAliases[lowered] || "openrouter-qwen-235b";
  }

  function nextRequestId(prefix) {
    requestCounter += 1;
    return `${prefix}-${Date.now()}-${requestCounter}`;
  }

  function extensionForMime(mime) {
    if (mime === "image/jpeg") {
      return "jpg";
    }
    if (mime === "image/webp") {
      return "webp";
    }
    return "png";
  }

  function isAppleMobile() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function screenshotFileName(mime) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    return `QQMusic-${stamp}.${extensionForMime(mime)}`;
  }

  function dataUrlToBlob(dataUrl) {
    const match = String(dataUrl || "").match(/^data:([^;]+);base64,(.+)$/);
    if (!match) {
      throw new Error("截图数据无效");
    }
    const mime = match[1];
    const binary = atob(match[2]);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return { blob: new Blob([bytes], { type: mime }), mime: mime };
  }

  function dataUrlToJpegFile(dataUrl, filename) {
    const parsed = dataUrlToBlob(dataUrl);
    if (parsed.mime === "image/jpeg") {
      return Promise.resolve(new File([parsed.blob], filename, { type: "image/jpeg" }));
    }
    return new Promise(function (resolve, reject) {
      const image = new Image();
      image.onload = function () {
        const canvas = document.createElement("canvas");
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0);
        canvas.toBlob(function (blob) {
          if (!blob) {
            reject(new Error("转码失败"));
            return;
          }
          resolve(new File([blob], filename, { type: "image/jpeg" }));
        }, "image/jpeg", 0.92);
      };
      image.onerror = function () {
        reject(new Error("截图无法打开"));
      };
      image.src = dataUrl;
    });
  }

  function shareFilesToAlbum(files) {
    return navigator.share({
      files: files,
      title: "保存到相册"
    }).then(function () {
      return "shared";
    });
  }

  function showAlbumLongPressSheet(dataUrls) {
    if (!albumSheet || !albumSheetImages) {
      return;
    }
    albumSheetImages.textContent = "";
    dataUrls.forEach(function (dataUrl, index) {
      const image = document.createElement("img");
      image.src = dataUrl;
      image.alt = `待存入相册的截图 ${index + 1}`;
      albumSheetImages.appendChild(image);
    });
    albumSheet.hidden = false;
  }

  function hideAlbumLongPressSheet() {
    if (albumSheet) {
      albumSheet.hidden = true;
    }
    if (albumSheetImages) {
      albumSheetImages.textContent = "";
    }
  }

  function saveImagesToAlbum(dataUrls) {
    const names = dataUrls.map(function () {
      return screenshotFileName("image/jpeg");
    });
    return dataUrls.reduce(function (chain, dataUrl, index) {
      return chain.then(function (files) {
        return dataUrlToJpegFile(dataUrl, names[index]).then(function (file) {
          files.push(file);
          return files;
        });
      });
    }, Promise.resolve([])).then(function (files) {
      const shareAttempt = navigator.share
        ? shareFilesToAlbum(files).catch(function (error) {
          if (error && error.name === "AbortError") {
            throw error;
          }
          if (files.length <= 1) {
            throw error;
          }
          return files.reduce(function (next, file) {
            return next.then(function () {
              return shareFilesToAlbum([file]);
            });
          }, Promise.resolve("shared"));
        })
        : Promise.reject(new Error("当前浏览器不能分享到相册"));
      return shareAttempt.catch(function (error) {
        if (error && error.name === "AbortError") {
          throw error;
        }
        if (isAppleMobile()) {
          showAlbumLongPressSheet(dataUrls);
          return "longpress";
        }
        throw error;
      });
    });
  }

  function chatScreenshots() {
    return albumItems.filter(function (item) {
      return item.forChat;
    });
  }

  function removeSentChatScreenshots(sentItems) {
    const sentIds = {};
    sentItems.forEach(function (item) {
      sentIds[item.id] = true;
    });
    albumItems = albumItems.filter(function (item) {
      return !sentIds[item.id];
    });
  }

  function selectedAlbumItems() {
    return albumItems.filter(function (item) {
      return item.selected;
    });
  }

  function updateSaveAlbumButton() {
    const selected = selectedAlbumItems().length;
    if (saveAlbumButton) {
      saveAlbumButton.disabled = selected === 0;
      saveAlbumButton.textContent = selected > 1 ? `保存到相册（${selected}）` : "保存到相册";
    }
    if (selectAllAlbumButton) {
      const allSelected = albumItems.length > 0 && selected === albumItems.length;
      selectAllAlbumButton.textContent = allSelected ? "取消全选" : "全选";
      selectAllAlbumButton.disabled = albumItems.length === 0;
    }
  }

  function addAlbumItem(image, size, forChat) {
    albumItems.push({
      id: nextAlbumId,
      image: image,
      size: size || 0,
      selected: true,
      forChat: Boolean(forChat)
    });
    nextAlbumId += 1;
    if (forChat) {
      const extra = chatScreenshots().length - maxScreenshots;
      let remaining = extra;
      albumItems.forEach(function (item) {
        if (remaining > 0 && item.forChat) {
          item.forChat = false;
          remaining -= 1;
        }
      });
    }
    if (albumItems.length > maxAlbumItems) {
      albumItems = albumItems.slice(albumItems.length - maxAlbumItems);
    }
  }

  function saveSelectedToAlbum() {
    const selected = selectedAlbumItems();
    if (!selected.length) {
      return;
    }
    saveImagesToAlbum(selected.map(function (item) {
      return item.image;
    })).then(function (method) {
      if (method === "shared") {
        setSelectionStatus("completed", "请在菜单中点「存储图像 / 添加到照片」，不要选存储到文件");
      } else if (method === "longpress") {
        setSelectionStatus("completed", "请长按图片存入相册，不要选存储到文件");
      }
    }).catch(function (error) {
      if (error && error.name === "AbortError") {
        return;
      }
      showAlbumLongPressSheet(selected.map(function (item) {
        return item.image;
      }));
      setSelectionStatus("error", "无法直接写入相册，请长按图片选择添加到照片");
    });
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
    clearChatButton.disabled = !online;
    updateAskButton();
  }

  function updateAskButton() {
    const online = socket && socket.readyState === WebSocket.OPEN;
    askButton.disabled = !online || (chatScreenshots().length === 0 && !questionInput.value.trim());
  }

  function setSelectionStatus(state, message) {
    selectionEl.className = `selection-status ${state || "waiting"}`;
    selectionMessageEl.textContent = message || "等待操作";
  }

  function resetChatUi() {
    activeChatRequestId = null;
    activeAssistantBubble = null;
    activeAssistantText = "";
    activeDirectRequestId = null;
    buffer = "";
    albumItems = [];
    hideAlbumLongPressSheet();
    renderPreviewList();
    chatList.textContent = "";
    const empty = document.createElement("div");
    empty.className = "empty-chat";
    empty.textContent = "可以只截图不输入文字；多张截图会和可选文字一起发送给 AI。";
    chatList.appendChild(empty);
    setOutput("等待电脑端发送题目…");
    updateAskButton();
  }

  function setActiveTier(tier, persist) {
    const next = normalizeRoute(tier);
    currentTier = next;
    if (modelRoute && modelRoute.value !== next) {
      modelRoute.value = next;
    }
    if (modelHint) {
      modelHint.textContent = knownRoutes[next] || next;
    }
    if (persist !== false) {
      storageSet(modelTierKey, next);
    }
  }

  function sendModelTier(tier) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const route = normalizeRoute(tier);
    socket.send(JSON.stringify({
      type: "command.set_model_tier",
      payload: { tier: route, route: route }
    }));
  }

  function clearEmptyChat() {
    const empty = chatList.querySelector(".empty-chat");
    if (empty) {
      empty.remove();
    }
  }

  function renderPreviewList() {
    const selected = selectedAlbumItems().length;
    previewCount.textContent = albumItems.length
      ? `已截图：${albumItems.length}张，已选 ${selected} 张`
      : "已截图：0张";
    previewList.textContent = "";
    albumItems.forEach(function (screenshot, index) {
      const item = document.createElement("div");
      item.className = "preview-item" + (screenshot.selected ? " selected" : "");
      const image = document.createElement("img");
      image.src = screenshot.image;
      image.alt = `截图 ${index + 1}`;
      const check = document.createElement("input");
      check.type = "checkbox";
      check.className = "preview-check";
      check.checked = screenshot.selected;
      check.setAttribute("aria-label", `选择截图 ${index + 1} 保存到相册`);
      check.addEventListener("click", function (event) {
        event.stopPropagation();
      });
      check.addEventListener("change", function () {
        screenshot.selected = check.checked;
        renderPreviewList();
      });
      const remove = document.createElement("button");
      remove.className = "preview-remove";
      remove.type = "button";
      remove.setAttribute("aria-label", `删除截图 ${index + 1}`);
      remove.textContent = "×";
      remove.addEventListener("click", function (event) {
        event.stopPropagation();
        albumItems = albumItems.filter(function (entry) {
          return entry.id !== screenshot.id;
        });
        renderPreviewList();
        updateAskButton();
      });
      item.addEventListener("click", function () {
        screenshot.selected = !screenshot.selected;
        renderPreviewList();
      });
      item.appendChild(image);
      item.appendChild(check);
      item.appendChild(remove);
      previewList.appendChild(item);
    });
    updateSaveAlbumButton();
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
        const forChat = payload.add_to_buffer !== false;
        addAlbumItem(payload.image, payload.size || 0, forChat);
        renderPreviewList();
        updateAskButton();
        const selected = selectedAlbumItems().length;
        if (forChat) {
          setSelectionStatus("completed", `已添加截图，已选 ${selected} 张，可勾选后保存到相册或发送`);
        } else {
          setSelectionStatus("completed", `截图已到达手机，已选 ${selected} 张，可勾选后保存到相册`);
        }
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
    } else if (event.type === "conversation.cleared") {
      resetChatUi();
    } else if (event.type === "model.changed") {
      setActiveTier(payload.route || payload.tier || currentTier, true);
      if (payload.display_name && modelHint) {
        modelHint.textContent = payload.display_name;
      }
    }
  }

  function pairUrl() {
    return "/pair?t=" + encodeURIComponent(pairToken);
  }

  function lookupSession() {
    if (!pairToken) {
      return Promise.resolve(null);
    }
    return fetch("/session?t=" + encodeURIComponent(pairToken), { cache: "no-store" })
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        if (data && data.ok && data.session_id) {
          return String(data.session_id);
        }
        return null;
      })
      .catch(function () {
        return null;
      });
  }

  function adoptSession(nextId) {
    if (!nextId) {
      return false;
    }
    if (nextId !== sessionId) {
      location.replace(pairUrl());
      return true;
    }
    return false;
  }

  function scheduleReconnect() {
    if (reconnectTimer) {
      return;
    }
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      lookupSession().then(function (nextId) {
        if (!adoptSession(nextId)) {
          connect();
        }
      });
    }, reconnectMs);
    reconnectMs = Math.min(Math.floor((reconnectMs || 1000) * 1.6), 8000);
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    if (!sessionId) {
      setConnectionStatus(pairToken ? "等待电脑端启动，可直接刷新" : "缺少配对会话", false);
      scheduleReconnect();
      return;
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws/mobile/${sessionId}?last_event_id=${lastEventId}`);
    socket.onopen = function () {
      reconnectMs = 1000;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      setConnectionStatus("电脑已连接", true);
      sendModelTier(currentTier);
    };
    socket.onmessage = function (message) {
      const event = JSON.parse(message.data);
      if (event.event_id && event.event_id > lastEventId) {
        lastEventId = event.event_id;
        storageSet(cursorKey, String(lastEventId));
      }
      handleEvent(event);
    };
    socket.onclose = function () {
      socket = null;
      setConnectionStatus("正在重连", false);
      scheduleReconnect();
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

  if (modelRoute) {
    modelRoute.addEventListener("change", function () {
      const route = modelRoute.value || "openrouter-qwen-235b";
      setActiveTier(route, true);
      sendModelTier(route);
    });
  }

  if (saveAlbumButton) {
    saveAlbumButton.addEventListener("click", saveSelectedToAlbum);
  }
  if (selectAllAlbumButton) {
    selectAllAlbumButton.addEventListener("click", function () {
      const selectAll = selectedAlbumItems().length !== albumItems.length;
      albumItems.forEach(function (item) {
        item.selected = selectAll;
      });
      renderPreviewList();
    });
  }
  if (albumSheetClose) {
    albumSheetClose.addEventListener("click", hideAlbumLongPressSheet);
  }
  if (albumSheet) {
    albumSheet.addEventListener("click", function (event) {
      if (event.target === albumSheet) {
        hideAlbumLongPressSheet();
      }
    });
  }

  clearChatButton.addEventListener("click", function () {
    resetChatUi();
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify({ type: "command.clear_conversation" }));
  });

  askButton.addEventListener("click", function () {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    const chatImages = chatScreenshots();
    const text = questionInput.value.trim();
    if (chatImages.length === 0 && !text) {
      updateAskButton();
      return;
    }
    const images = chatImages.map(function (screenshot) { return screenshot.image; });
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
    removeSentChatScreenshots(chatImages);
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
  setActiveTier(currentTier, false);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") {
      return;
    }
    reconnectMs = 1000;
    lookupSession().then(function (nextId) {
      if (!adoptSession(nextId)) {
        connect();
      }
    });
  });
  connect();
})();
