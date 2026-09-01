(function () {
  const sessionId = window.SESSION_ID && window.SESSION_ID !== "__SESSION_ID__"
    ? window.SESSION_ID
    : new URLSearchParams(location.search).get("session_id");
  const statusEl = document.getElementById("status");
  const outputEl = document.getElementById("output");
  const cursorKey = `lastEventId:${sessionId || "missing"}`;
  let lastEventId = Number(localStorage.getItem(cursorKey) || 0);
  let reconnectMs = 1000;
  let buffer = "";

  function setStatus(value, online) {
    statusEl.textContent = value;
    statusEl.classList.toggle("online", Boolean(online));
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    if (event.type === "answer.started") {
      buffer = "";
      outputEl.textContent = "分析中…";
    } else if (event.type === "answer.delta") {
      buffer += payload.delta || "";
      outputEl.textContent = buffer || "分析中…";
    } else if (event.type === "answer.completed") {
      const result = payload.result || {};
      buffer = result.text || buffer || "分析完成";
      outputEl.textContent = buffer;
    } else if (event.type === "answer.error") {
      buffer = "";
      outputEl.textContent = `错误：${payload.message || "模型调用失败"}`;
    }
  }

  function connect() {
    if (!sessionId) {
      setStatus("缺少配对会话", false);
      return;
    }
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${protocol}://${location.host}/ws/mobile/${sessionId}?last_event_id=${lastEventId}`);
    socket.onopen = function () {
      reconnectMs = 1000;
      setStatus("电脑已连接", true);
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
      setStatus("正在重连", false);
      setTimeout(connect, reconnectMs);
      reconnectMs = Math.min(Math.floor(reconnectMs * 2), 30000);
    };
  }

  connect();
})();
