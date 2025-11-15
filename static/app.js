const MAX_URLS = 100;

const form = document.getElementById("download-form");
const textarea = document.getElementById("urls");
const fileInput = document.getElementById("file-input");
const statusMessage = document.getElementById("status-message");
const summaryTotal = document.getElementById("summary-total");
const summarySuccess = document.getElementById("summary-success");
const summaryFailed = document.getElementById("summary-failed");
const urlCount = document.getElementById("url-count");
const submitBtn = document.getElementById("submit-btn");

const setStatus = (message, type = "") => {
  statusMessage.textContent = message;
  statusMessage.classList.remove("error", "success");
  if (type) {
    statusMessage.classList.add(type);
  }
};

const getUrlsFromTextarea = () => {
  return (textarea.value || "")
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const updateCount = () => {
  const urls = getUrlsFromTextarea();
  urlCount.textContent = `${urls.length}件`;
};

textarea.addEventListener("input", updateCount);

fileInput.addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  try {
    const text = await file.text();
    const fileUrls = text
      .split(/[\r\n,]+/)
      .map((line) => line.trim())
      .filter(Boolean);

    const existing = new Set(getUrlsFromTextarea());
    fileUrls.forEach((url) => {
      if (!existing.has(url)) {
        existing.add(url);
      }
    });

    textarea.value = Array.from(existing).join("\n");
    updateCount();
    setStatus(`ファイルから${fileUrls.length}件のURLを取り込みました。`, "success");
  } catch (error) {
    console.error(error);
    setStatus("ファイルの読み込みに失敗しました。", "error");
  } finally {
    event.target.value = "";
  }
});

const prepareBody = (urls) => JSON.stringify({ urls });

const toFilename = (disposition) => {
  if (!disposition) {
    return `tiktok_videos_${Date.now()}.zip`;
  }
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] ?? `tiktok_videos_${Date.now()}.zip`;
};

const downloadBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  setTimeout(() => {
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, 0);
};

const updateSummary = (summary) => {
  summaryTotal.textContent = summary.total ?? 0;
  summarySuccess.textContent = summary.success ?? 0;
  summaryFailed.textContent = summary.failed ?? 0;
};

const parseErrorMessage = async (response) => {
  try {
    const data = await response.json();
    if (data?.detail) {
      if (typeof data.detail === "string") {
        return data.detail;
      }
      if (Array.isArray(data.detail) && data.detail[0]?.msg) {
        return data.detail.map((item) => item.msg).join("\n");
      }
    }
  } catch (error) {
    // ignore parse errors
  }
  return `サーバーエラー: ${response.status}`;
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const urls = getUrlsFromTextarea();

  if (!urls.length) {
    setStatus("URLを入力してください。", "error");
    return;
  }

  if (urls.length > MAX_URLS) {
    setStatus(`URLは最大${MAX_URLS}件まで指定できます。`, "error");
    return;
  }

  submitBtn.disabled = true;
  setStatus("サーバーで動画を取得しています。完了までお待ちください...");

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/zip",
      },
      body: prepareBody(urls),
    });

    if (!response.ok) {
      const message = await parseErrorMessage(response);
      throw new Error(message);
    }

    const blob = await response.blob();
    const filename = toFilename(response.headers.get("content-disposition"));

    const summaryHeader = response.headers.get("x-download-summary");
    if (summaryHeader) {
      try {
        updateSummary(JSON.parse(summaryHeader));
      } catch {
        updateSummary({ total: urls.length, success: urls.length, failed: 0 });
      }
    }

    downloadBlob(blob, filename);
    setStatus("ダウンロードが完了しました。", "success");
  } catch (error) {
    console.error(error);
    setStatus(error.message ?? "処理中にエラーが発生しました。", "error");
    updateSummary({ total: urls.length, success: 0, failed: urls.length });
  } finally {
    submitBtn.disabled = false;
  }
});

// 初期表示の更新
updateCount();

