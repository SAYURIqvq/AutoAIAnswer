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
  const outputEl = document.getElementById("output");
  const cursorKey = `lastEventId:${sessionId || "missing"}`;
  let lastEventId = Number(localStorage.getItem(cursorKey) || 0);
  let reconnectMs = 1000;
  let buffer = "";
  let socket = null;

  function setConnectionStatus(value, online) {
    statusEl.textContent = value;
    statusEl.classList.toggle("online", Boolean(online));
    fullscreenButton.disabled = !online;
    updateAskButton();
  }

  function updateAskButton() {
    const online = socket && socket.readyState === WebSocket.OPEN;
    askButton.disabled = !online || !questionInput.value.trim();
  }

  function setSelectionStatus(state, message) {
    selectionEl.className = `selection-status ${state || "waiting"}`;
    selectionMessageEl.textContent = message || "等待操作";
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    if (event.type === "selection.status") {
      setSelectionStatus(payload.state, payload.message);
    } else if (event.type === "answer.started") {
      buffer = "";
      setSelectionStatus("analyzing", "AI 正在分析，请稍候");
      outputEl.textContent = "分析中…";
    } else if (event.type === "answer.delta") {
      buffer += payload.delta || "";
      outputEl.textContent = buffer || "分析中…";
    } else if (event.type === "answer.completed") {
      const result = payload.result || {};
      buffer = result.text || buffer || "分析完成";
      outputEl.textContent = buffer;
      setSelectionStatus("completed", "答案已生成，可以继续框选或全屏截题");
    } else if (event.type === "answer.error") {
      buffer = "";
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
    setSelectionStatus("capturing", "已请求电脑截取全屏");
    socket.send(JSON.stringify({ type: "command.fullscreen" }));
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
    if (!text) {
      updateAskButton();
      return;
    }
    fullscreenButton.disabled = true;
    askButton.disabled = true;
    setSelectionStatus("capturing", "已请求电脑截全屏并发送追问");
    socket.send(JSON.stringify({
      type: "command.fullscreen",
      payload: {
        text,
        conversation: true
      }
    }));
    questionInput.value = "";
    setTimeout(function () {
      if (socket && socket.readyState === WebSocket.OPEN) {
        fullscreenButton.disabled = false;
        updateAskButton();
      }
    }, 1500);
  });

  connect();
})();
