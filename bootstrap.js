const PLUGIN_VERSION = "0.4.0-beta.7";
const PLUGIN_ID = "zotero-vocab-review@local";
const STATUS_PATH = "/vocab-review/status";
const MENU_ID = "zotero-vocab-review-tools";
const PREF_KEY = "extensions.zotero.vocabReview.data";
const PREF_PREFIX = "extensions.zotero.vocabReview.";
const DEFAULT_ANKI = {
  endpoint: "http://127.0.0.1:8765",
  deckName: "Zotero Vocabulary",
  modelName: "",
  frontField: "",
  backField: "",
};
const ANKI_TAG = "zotero_vocab_review";
const DICTIONARY_TAG = "zotero_highlight";
const PICK2ANKI_SOURCE = "https://github.com/soyami/zotero-pick2anki";

let notifierID = null;
let menuRegistrationID = null;
let captureQueue = Promise.resolve();
let syncQueue = Promise.resolve();
let popupTimer = null;
let retryTimer = null;
let retryInProgress = false;
let configDetection = null;
let ankiRecovery = null;
let ankiPathPicker = null;
let ankiPathPrompted = false;
let generation = 0;
let running = false;
let lastCaptureAt = null;
const queuedSyncs = new Map();
const notificationTimers = new Set();
const dictionaryLookups = new Map();
const literatureLookups = new Set();
const ignoredHighlights = new Set();

function loadData() {
  try {
    const data = JSON.parse(Zotero.Prefs.get(PREF_KEY, true) || "{}");
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("词库格式无效");
    if (Object.values(data).some(entry => !entry || typeof entry !== "object" || Array.isArray(entry))) {
      throw new Error("词条格式无效");
    }
    const entries = Object.assign(Object.create(null), data);
    for (const entry of Object.values(entries)) {
      if (!entry.meaningSource && cleanMeaning(entry.meaning)) entry.meaningSource = "manual";
    }
    return entries;
  } catch (error) {
    Zotero.debug(`[VocabReview] Could not read saved vocabulary: ${error}`);
    throw new Error("本地词库数据无法读取，已停止写入以保护原数据。请查看状态与连接诊断。");
  }
}

function saveData(data) {
  const previous = Zotero.Prefs.get(PREF_KEY, true);
  if (previous) {
    // Preserve the previous valid snapshot before replacing it.
    JSON.parse(previous);
    Zotero.Prefs.set(PREF_PREFIX + "dataBackup", previous, true);
  }
  Zotero.Prefs.set(PREF_KEY, JSON.stringify(data), true);
}

function markPending(entry) {
  entry.revision = (entry.revision || 0) + 1;
  entry.syncStatus = "pending";
  entry.syncError = "";
}

function getAnkiConfig() {
  return Object.fromEntries(Object.entries(DEFAULT_ANKI).map(([key, fallback]) => [
    key,
    Zotero.Prefs.get(PREF_PREFIX + key, true) || fallback,
  ]));
}

function saveAnkiConfig(config) {
  for (const [key, value] of Object.entries(config)) {
    Zotero.Prefs.set(PREF_PREFIX + key, value, true);
  }
}

async function ensureAnkiConfig() {
  const saved = getAnkiConfig();
  if (saved.modelName && saved.frontField && saved.backField) return saved;
  if (configDetection) return configDetection;
  configDetection = detectAnkiConfig().finally(() => { configDetection = null; });
  return configDetection;
}

async function detectAnkiConfig() {
  const config = getAnkiConfig();
  const models = await requestAnki("modelNames");
  // Recover the mapping used by older local versions before selecting a new template.
  const ids = await requestAnki("findNotes", { query: `tag:${ANKI_TAG}` });
  if (ids?.length) {
    const notes = await requestAnki("notesInfo", { notes: ids });
    const names = [...new Set(notes.map(note => note.modelName))];
    if (names.length !== 1) throw new Error("已有词汇卡片使用多个模板，请从工具菜单指定 Anki 模板与字段。");
    const fields = await requestAnki("modelFieldNames", { modelName: names[0] });
    if (fields.length < 2) throw new Error("已有词汇模板不足两个字段，请从工具菜单配置。");
    config.modelName = names[0];
    config.frontField = config.frontField || fields[0];
    config.backField = config.backField || fields[1];
    if (!Zotero.Prefs.get(PREF_PREFIX + "deckName", true) && notes[0].cards?.length) {
      const cards = await requestAnki("cardsInfo", { cards: [notes[0].cards[0]] });
      if (cards[0]?.deckName) config.deckName = cards[0].deckName;
    }
  } else {
    const dedicated = "Zotero Vocabulary Review";
    const basicNames = ["Basic", "问答题", "基本", "基础", "基礎"];
    const candidates = models.includes(dedicated) ? [dedicated] :
      basicNames.filter(name => models.includes(name));
    for (const modelName of candidates) {
      const fields = await requestAnki("modelFieldNames", { modelName });
      if (fields.length === 2) {
        config.modelName = modelName;
        config.frontField = fields[0];
        config.backField = fields[1];
        break;
      }
    }
    if (!config.modelName) {
      if (models.includes(dedicated)) throw new Error("插件专用模板字段不匹配，请从工具菜单指定模板；现有模板未被修改。");
      await requestAnki("createModel", {
        modelName: dedicated, inOrderFields: ["Word", "Meaning"],
        css: ".card { font-family: sans-serif; font-size: 22px; text-align: left; line-height: 1.6; }",
        cardTemplates: [{ Name: "Vocabulary", Front: "{{Word}}", Back: "{{FrontSide}}<hr id=answer>{{Meaning}}" }],
      });
      config.modelName = dedicated;
      config.frontField = "Word";
      config.backField = "Meaning";
    }
  }
  const fields = await requestAnki("modelFieldNames", { modelName: config.modelName });
  if (fields[0] !== config.frontField || !fields.includes(config.backField) || config.frontField === config.backField) {
    throw new Error("自动识别的 Anki 字段不匹配，请从工具菜单配置；尚未保存该配置。");
  }
  saveAnkiConfig(config);
  return config;
}

function isAutoSyncEnabled() {
  return Zotero.Prefs.get(PREF_PREFIX + "autoSync", true) !== false;
}

function setAutoSyncEnabled(enabled) {
  Zotero.Prefs.set(PREF_PREFIX + "autoSync", enabled, true);
}

function notifyUser(headline, details = "") {
  try {
    const notification = new Zotero.ProgressWindow({ closeOnClick: true });
    notification.changeHeadline(headline);
    if (details) notification.addDescription(details);
    notification.show();
    const timer = setTimeout(() => {
      notificationTimers.delete(timer);
      try { notification.close(); } catch (_) { /* The window may already be closed. */ }
    }, getNotificationSeconds() * 1000);
    notificationTimers.add(timer);
  } catch (error) {
    Zotero.debug(`[VocabReview] Could not show notification: ${error}`);
    Zotero.getMainWindow()?.alert(`${headline}${details ? `\n${details}` : ""}`);
  }
}

function getNotificationSeconds() {
  const value = Number(Zotero.Prefs.get(PREF_PREFIX + "notificationSeconds", true));
  return Number.isInteger(value) && value >= 1 && value <= 120 ? value : 5;
}

function setNotificationSeconds(win) {
  const current = getNotificationSeconds();
  const value = win.prompt("通知弹窗显示几秒？请输入 1–120 的整数：", String(current));
  if (value === null) return;
  const seconds = Number(value);
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 120) {
    win.alert("请输入 1–120 之间的整数秒数。");
    return;
  }
  Zotero.Prefs.set(PREF_PREFIX + "notificationSeconds", seconds, true);
  notifyUser("通知时长已更新", `弹窗将在 ${seconds} 秒后自动关闭。`);
}

function cleanMeaning(value) {
  return String(value || "").replace(/^[\s🔤]+|[\s🔤]+$/gu, "").trim();
}

function dictionaryText(value) {
  return String(Array.isArray(value) ? value.join(" ") : (value || "")).replace(/<[^>]*>/g, " ").replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ").trim();
}

async function lookupYoudao(word) {
  const url = `https://dict.youdao.com/jsonapi?q=${encodeURIComponent(word)}&doctype=json&jsonversion=2`;
  const response = await Zotero.HTTP.request("GET", url, { responseType: "text", timeout: 8000 });
  const root = JSON.parse(response.response);
  const definitions = [];
  const examples = [];
  const authoritativeExamples = [];
  const phonetics = [];
  const cp = root.collins_primary || {};
  for (const group of Array.isArray(cp.gramcat) ? cp.gramcat : []) {
    const pos = dictionaryText(group.partofspeech);
    const phonetic = dictionaryText(group.pronunciation);
    if (phonetic && !phonetics.includes(phonetic)) phonetics.push(phonetic);
    for (const sense of Array.isArray(group.senses) ? group.senses : []) {
      const meaning = dictionaryText(sense.word);
      if (meaning) definitions.push(`${pos ? `${pos} ` : ""}${meaning}`);
      for (const example of Array.isArray(sense.examples) ? sense.examples : []) {
        const en = dictionaryText(example.example || example.sentence);
        const zh = dictionaryText(example.sense?.word || example.translation);
        if (en) examples.push(`${en}${zh ? ` — ${zh}` : ""}`);
      }
    }
  }
  const simple = (root.simple?.word || [])[0] || {};
  for (const value of [simple.ukphone, simple.usphone]) {
    const phonetic = dictionaryText(value);
    if (phonetic && !phonetics.includes(phonetic)) phonetics.push(phonetic);
  }
  if (!definitions.length) {
    const wordEntry = (root.ec?.word || [])[0] || {};
    for (const group of Array.isArray(wordEntry.trs) ? wordEntry.trs : []) {
      for (const translation of Array.isArray(group.tr) ? group.tr : []) {
        const meaning = dictionaryText(translation.l?.i);
        if (meaning) definitions.push(`${dictionaryText(group.pos) ? `${dictionaryText(group.pos)} ` : ""}${meaning}`);
      }
    }
  }
  for (const group of Array.isArray(root.expand_ec?.word) ? root.expand_ec.word : []) {
    for (const translation of Array.isArray(group.transList) ? group.transList : []) {
      const content = translation.content || {};
      const pos = dictionaryText(content.detailPos);
      const meaning = dictionaryText(translation.trans || translation.tran);
      if (meaning && !definitions.includes(`${pos ? `${pos} ` : ""}${meaning}`)) {
        definitions.push(`${pos ? `${pos} ` : ""}${meaning}`);
      }
      for (const sentence of Array.isArray(content.sents) ? content.sents : []) {
        const en = dictionaryText(sentence.sentSpeech || sentence.sentOrig);
        const zh = dictionaryText(sentence.sentTrans);
        if (!en) continue;
        const line = `${en}${zh ? ` — ${zh}` : ""}`;
        if (sentence.sourceType === "权威") authoritativeExamples.push(line);
        examples.push(line);
      }
    }
  }
  const synonyms = (root.syno?.synos || []).flatMap(group => group.syno?.ws || [])
    .map(value => dictionaryText(value.w)).filter(Boolean);
  const etymology = (root.etym?.etyms?.en || []).map(value => {
    const source = dictionaryText(value.source);
    const text = dictionaryText(value.value);
    return text ? `${source ? `${source}：` : ""}${text}` : "";
  }).filter(Boolean).slice(0, 3).join("<br>");
  const audioPart = simple.usspeech || simple.ukspeech || "";
  const audioURL = audioPart
    ? `https://dict.youdao.com/dictvoice?audio=${encodeURIComponent(String(audioPart).split("&type=")[0])}&type=${String(audioPart).split("&type=")[1] || "2"}`
    : "";
  return { meaning: definitions.slice(0, 8).join("\n"),
    examples: [...new Set(examples)].slice(0, 8).join("\n"),
    authoritativeExamples: [...new Set(authoritativeExamples)].slice(0, 5).join("\n"),
    synonyms: [...new Set(synonyms)].slice(0, 8).join("；"), etymology: etymology.replace(/<br>/g, "\n"),
    phonetic: phonetics.slice(0, 3).join(" · "), audioURL };
}

function enrichFromDictionary(word) {
  const data = loadData();
  const entry = data[word];
  if (!entry || entry.dictionaryLookup === "done" || dictionaryLookups.has(word)
      || !/^[a-z][a-z'’ -]{0,59}$/i.test(entry.word || word)) return;
  const task = lookupYoudao(entry.word || word).then((result) => {
    const latest = loadData();
    const current = latest[word];
    if (!current) return;
    if (!cleanMeaning(current.meaning) && result.meaning) {
      current.meaning = result.meaning;
      current.meaningSource = "dictionary";
    }
    current.examples = current.examples || result.examples;
    current.authoritativeExamples = current.authoritativeExamples || result.authoritativeExamples;
    current.synonyms = current.synonyms || result.synonyms;
    current.etymology = current.etymology || result.etymology;
    current.phonetic = current.phonetic || result.phonetic;
    current.audioURL = current.audioURL || result.audioURL;
    current.dictionarySource = PICK2ANKI_SOURCE;
    current.dictionaryLookup = "done";
    if (result.meaning || result.examples || result.phonetic || result.authoritativeExamples || result.synonyms || result.etymology || result.audioURL) {
      markPending(current);
      saveData(latest);
      void enqueueSync(word, true).catch(reportBackgroundError);
    } else saveData(latest);
  }).catch((error) => {
    Zotero.debug(`[VocabReview] Dictionary lookup failed for ${word}: ${error}`);
    const latest = loadData();
    if (latest[word]) { latest[word].dictionaryLookup = "failed"; saveData(latest); }
  }).finally(() => dictionaryLookups.delete(word));
  dictionaryLookups.set(word, task);
}

function normalizeWord(text) {
  return String(text || "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim()
    .replace(/^[\p{P}\p{S}]+|[\p{P}\p{S}]+$/gu, "")
    .replace(/\s+/g, " ")
    .toLowerCase();
}

function escapeHTML(text) {
  return String(text || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function normalizeAnkiField(text) {
  const decoded = String(text || "").replace(/&lt;|&gt;|&quot;|&#39;|&amp;/g, (entity) => ({
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&amp;": "&",
  })[entity]);
  return normalizeWord(decoded);
}

function countWords(text) {
  return String(text || "").match(/[\p{L}\p{N}]+(?:['’\-][\p{L}\p{N}]+)*/gu)?.length || 0;
}

function getSource(item) {
  const { parent, page } = getAnnotationSource(item);
  const title = parent?.getField?.("title") || "Zotero PDF";
  const creator = parent?.getField?.("firstCreator") || "";
  const year = parent?.getField?.("year") || "";
  const citation = [creator && (year ? `${creator} (${year})` : creator), title].filter(Boolean).join(". ");
  return page ? `${citation} (p. ${page})` : citation;
}

function getAnnotationSource(item) {
  const attachment = item.parentID ? Zotero.Items.get(item.parentID) : null;
  const parent = attachment?.isAttachment?.() && attachment.parentID
    ? Zotero.Items.get(attachment.parentID) : attachment;
  return { attachment, parent, page: String(item.annotationPageLabel || "").trim() };
}

function extractLiteratureSentence(text, word) {
  const escapedWord = String(word).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pattern = new RegExp(`(^|[^\\p{L}\\p{N}])${escapedWord}($|[^\\p{L}\\p{N}])`, "iu");
  const sentences = String(text || "").replace(/\s+/g, " ").match(/[^.!?]+(?:[.!?]+|$)/gu) || [];
  const sentence = sentences.map(value => value.trim()).find(value => pattern.test(value));
  return sentence ? sentence.slice(0, 600) : "";
}

function formatLiteratureExample(example) {
  return `“${example.sentence}” —— ${example.source}`;
}

async function enrichFromLiterature(word, item) {
  const data = loadData();
  const entry = data[word];
  const { attachment } = getAnnotationSource(item);
  const key = `${word}:${item.libraryID}:${item.key}`;
  if (!entry || !attachment?.isAttachment?.() || literatureLookups.has(key)
      || (entry.literatureExamples || []).some(example => example.annotationID === `${item.libraryID}:${item.key}`)) return;
  literatureLookups.add(key);
  try {
    const text = await attachment.attachmentText;
    const position = JSON.parse(item.annotationPosition || "{}");
    const pageIndex = Number.isInteger(position.pageIndex) ? position.pageIndex : -1;
    const pages = String(text || "").split("\f");
    const pageText = pageIndex >= 0 && pages.length > 1 ? pages[pageIndex] : text;
    const sentence = extractLiteratureSentence(pageText, item.annotationText || entry.word);
    if (!sentence) return;
    const latest = loadData();
    const current = latest[word];
    if (!current) return;
    const { parent, page } = getAnnotationSource(item);
    const title = parent?.getField?.("title") || "Zotero PDF";
    const creator = parent?.getField?.("firstCreator") || "";
    const year = parent?.getField?.("year") || "";
    const source = [creator && (year ? `${creator} (${year})` : creator), title].filter(Boolean).join(". ");
    const citation = page ? `${source} (p. ${page})` : source;
    current.literatureExamples = [...(current.literatureExamples || []), {
      sentence, source: citation, annotationID: `${item.libraryID}:${item.key}`,
    }].slice(-20);
    markPending(current);
    saveData(latest);
    void enqueueSync(word, true).catch(reportBackgroundError);
  } catch (error) {
    Zotero.debug(`[VocabReview] Literature example extraction failed for ${word}: ${error}`);
  } finally {
    literatureLookups.delete(key);
  }
}

async function captureAnnotation(itemID) {
  const item = Zotero.Items.get(itemID);
  if (!item || !item.isAnnotation?.() || !["highlight", "underline"].includes(item.annotationType)) return;

  const original = String(item.annotationText || "").trim();
  const word = normalizeWord(original);
  const annotationID = `${item.libraryID}:${item.key}`;
  if (!word) return;
  if (original.length > 60 || countWords(original) > 5) {
    if (!ignoredHighlights.has(annotationID)) {
      ignoredHighlights.add(annotationID);
      notifyUser("这段高亮未收录", "词汇插件仅收录不超过 5 个词、60 个字符的高亮。可重新只高亮目标单词或短语。");
    }
    return;
  }

  lastCaptureAt = Date.now();
  const data = loadData();
  const existingEntry = Object.entries(data).find(([, entry]) => entry.annotationIDs?.includes(annotationID));
  const comment = cleanMeaning(item.annotationComment);
  if (existingEntry) {
    const [existingKey, existing] = existingEntry;
    if (comment && existing.meaningSource !== "manual" && cleanMeaning(existing.meaning) !== comment) {
      existing.meaning = comment;
      existing.meaningSource = "annotation";
      markPending(existing);
      saveData(data);
      syncCapturedWord(existingKey, "释义已更新。");
    }
    if (!cleanMeaning(existing.meaning)) enrichFromDictionary(existingKey);
    return;
  }

  const now = Date.now();
  const source = getSource(item);
  const entry = data[word];
  if (entry) {
    entry.word = entry.word || original;
    entry.count = (entry.count || 1) + 1;
    if (comment && !cleanMeaning(entry.meaning)) {
      entry.meaning = comment;
      entry.meaningSource = "annotation";
    }
    entry.annotationIDs = [...(entry.annotationIDs || []), annotationID];
    entry.sources = [...new Set([...(entry.sources || []), source])].slice(-30);
    entry.lastCaptured = now;
    entry.dueAt = Math.min(entry.dueAt || now, now);
  } else {
    data[word] = {
      word: original, meaning: comment, meaningSource: comment ? "annotation" : "", count: 1, reviews: 0,
      intervalDays: 0, dueAt: now, lastCaptured: now,
      annotationIDs: [annotationID], sources: [source],
    };
  }
  markPending(data[word]);
  saveData(data);
  void enrichFromLiterature(word, item);
  enrichFromDictionary(word);
  const details = entry
    ? `之前收录过，本次为第 ${data[word].count} 次；复习优先级已提高。`
    : "首次收录。";
  syncCapturedWord(word, details);
}

function syncCapturedWord(word, details) {
  const entry = loadData()[word];
  if (!isAutoSyncEnabled()) {
    notifyUser(`已收录：${entry.word}`, `${details}已保存在 Zotero；自动同步到 Anki 已关闭。`);
    return;
  }
  notifyUser(`已收录：${entry.word}`, `${details}正在同步到 Anki…`);
  enqueueSync(word, true)
    .then((result) => {
      if (result?.skipped) return;
      notifyUser(`${result?.pending ? "部分更新待同步" : result?.duplicate ? "发现并保留已有卡片" : result?.updated ? "已更新 Anki" : "已添加到 Anki"}：${entry.word}`,
        `${details}${result?.duplicate ? "已有卡片已保留原释义，并补充空白字段。" : `牌组：${getAnkiConfig().deckName}`}${result?.pending ? "；新的修改已保留，稍后重试。" : ""}`);
    })
    .catch((error) => notifyUser(`已保存在 Zotero：${entry.word}`,
      `Anki 同步失败：${error.message || error}。开启自动同步时会定期重试，也可手动同步。`));
}

function enableAutoSync() {
  setAutoSyncEnabled(true);
  void retryPending().catch(reportBackgroundError);
  notifyUser("标记自动同步已开启", `符合条件的高亮和下划线将自动同步到 Anki 的“${getAnkiConfig().deckName}”牌组。`);
}

function disableAutoSync() {
  setAutoSyncEnabled(false);
  notifyUser("标记自动同步已关闭", "之后的高亮和下划线仍会保存到 Zotero 词库；需要时可手动同步到 Anki。");
}

function getEnvironment(name) {
  try {
    const environment = Components.classes["@mozilla.org/process/environment;1"]
      .getService(Components.interfaces.nsIEnvironment);
    return environment.get(name) || "";
  } catch (_) { return ""; }
}

function existingLauncher(path) {
  if (!path) return null;
  try {
    const file = Zotero.File.pathToFile(path);
    if (!file.exists()) return null;
    const appBundle = Zotero.isMac && file.isDirectory() && /\.app$/i.test(file.leafName);
    return file.isFile() || appBundle ? file : null;
  } catch (_) { return null; }
}

function findAnkiStartMenuShortcut(rootPath, depth = 4) {
  let root;
  try { root = Zotero.File.pathToFile(rootPath); }
  catch (_) { return null; }
  try { if (!root.exists() || !root.isDirectory()) return null; }
  catch (_) { return null; }
  const search = (directory, remaining) => {
    let entries;
    try { entries = directory.directoryEntries; } catch (_) { return null; }
    const subdirectories = [];
    while (entries.hasMoreElements()) {
      let entry;
      try { entry = entries.getNext().QueryInterface(Components.interfaces.nsIFile); }
      catch (_) { continue; }
      if (entry.isFile() && /anki.*\.lnk$/i.test(entry.leafName)) return entry;
      if (remaining > 0 && entry.isDirectory()) subdirectories.push(entry);
    }
    for (const subdirectory of subdirectories) {
      const found = search(subdirectory, remaining - 1);
      if (found) return found;
    }
    return null;
  };
  return search(root, depth);
}

function findAnkiLauncher() {
  const saved = Zotero.Prefs.get(PREF_PREFIX + "ankiExecutablePath", true);
  const savedFile = existingLauncher(saved);
  if (savedFile) return savedFile;

  let candidates = [];
  if (Zotero.isWin) {
    const appData = getEnvironment("APPDATA");
    const programData = getEnvironment("PROGRAMDATA");
    for (const startMenu of [appData, programData].filter(Boolean)) {
      const shortcut = findAnkiStartMenuShortcut(`${startMenu}\\Microsoft\\Windows\\Start Menu\\Programs`);
      if (shortcut) return shortcut;
    }
    candidates = [
      `${getEnvironment("LOCALAPPDATA")}\\Programs\\Anki\\anki.exe`,
      `${getEnvironment("LOCALAPPDATA")}\\Programs\\Anki\\Anki.exe`,
      `${getEnvironment("LOCALAPPDATA")}\\Anki\\anki.exe`,
      `${getEnvironment("ProgramFiles")}\\Anki\\anki.exe`,
      `${getEnvironment("ProgramFiles(x86)")}\\Anki\\Anki.exe`,
    ];
  } else if (Zotero.isMac) {
    const home = getEnvironment("HOME");
    candidates = ["/Applications/Anki.app", `${home}/Applications/Anki.app`];
  } else {
    const home = getEnvironment("HOME");
    candidates = ["/usr/bin/anki", "/usr/local/bin/anki", `${home}/.local/bin/anki`, `${home}/Applications/Anki/anki`];
  }
  return candidates.map(existingLauncher).find(Boolean) || null;
}

async function chooseAnkiExecutable() {
  if (ankiPathPicker) return ankiPathPicker;
  if (ankiPathPrompted) {
    throw new Error("尚未设置 Anki 程序位置。可手动打开 Anki 完成同步；如需再次选择程序，请重启 Zotero 后重试。");
  }
  ankiPathPrompted = true;
  ankiPathPicker = new Promise((resolve, reject) => {
    try {
      const picker = Components.classes["@mozilla.org/filepicker;1"]
        .createInstance(Components.interfaces.nsIFilePicker);
      picker.init(Zotero.getMainWindow(), "首次启动 Anki：请选择 Anki 程序", Components.interfaces.nsIFilePicker.modeOpen);
      if (Zotero.isWin) picker.appendFilter("Anki 程序", "*anki*.exe");
      picker.open(result => {
        const file = picker.file;
        if (result !== Components.interfaces.nsIFilePicker.returnOK || !file) {
          reject(new Error("未选择 Anki 程序。词条已保存在 Zotero，可稍后重试同步。"));
          return;
        }
        if (Zotero.isWin && !/anki.*\.exe$/i.test(file.leafName)) {
          reject(new Error("请选择 Anki.exe。词条已保存在 Zotero，可稍后重试同步。"));
          return;
        }
        Zotero.Prefs.set(PREF_PREFIX + "ankiExecutablePath", file.path, true);
        resolve(file);
      });
    } catch (error) { reject(error); }
  }).finally(() => { ankiPathPicker = null; });
  return ankiPathPicker;
}

async function requestAnkiHTTP(action, params, endpoint, timeout = 5000) {
  let xhr;
  try {
    xhr = await Zotero.HTTP.request("POST", endpoint, {
      body: JSON.stringify({ action, version: 6, params }),
      headers: { "Content-Type": "application/json" },
      responseType: "text",
      timeout,
    });
  } catch (_) {
    const error = new Error("无法连接 AnkiConnect。");
    error.ankiUnavailable = true;
    throw error;
  }
  let response;
  try {
    response = JSON.parse(xhr.response);
  } catch (_) {
    throw new Error("AnkiConnect 返回了无效响应，请检查端口和服务。");
  }
  if (!response || typeof response !== "object" || !("result" in response)) {
    throw new Error("该地址未返回 AnkiConnect API 响应。");
  }
  if (response.error) throw new Error(response.error);
  return response.result;
}

async function ensureAnkiAvailable(endpoint) {
  if (ankiRecovery) return ankiRecovery;
  ankiRecovery = (async () => {
    let launcher = findAnkiLauncher();
    if (!launcher) launcher = await chooseAnkiExecutable();
    notifyUser("正在启动 Anki", "检测到 Anki 未运行；启动后会自动重试同步。");
    try { Zotero.launchFile(launcher.path); }
    catch (error) { throw new Error(`启动 Anki 失败：${error.message || error}`); }

    const deadline = Date.now() + 30000;
    while (Date.now() < deadline) {
      try {
        await requestAnkiHTTP("version", {}, endpoint, 1500);
        return;
      } catch (error) {
        if (!error.ankiUnavailable) throw error;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error("Anki 已启动，但等待 30 秒后仍无法连接 AnkiConnect。请确认 AnkiConnect 已安装并启用；本次词条仍保存在 Zotero，可稍后重试同步。");
  })().finally(() => { ankiRecovery = null; });
  return ankiRecovery;
}

async function requestAnki(action, params = {}, endpointOverride = null) {
  const config = getAnkiConfig();
  const endpoint = endpointOverride || config.endpoint;
  const match = /^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):(\d{1,5})\/?$/i.exec(endpoint);
  if (!match || Number(match[1]) < 1 || Number(match[1]) > 65535) {
    throw new Error("AnkiConnect 地址必须是本机地址，例如 http://127.0.0.1:8765。");
  }
  try {
    return await requestAnkiHTTP(action, params, endpoint);
  } catch (error) {
    if (!error.ankiUnavailable) throw error;
    await ensureAnkiAvailable(endpoint);
    try { return await requestAnkiHTTP(action, params, endpoint); }
    catch (retryError) {
      if (retryError.ankiUnavailable) {
        retryError.message = `Anki 已启动，但仍无法连接 AnkiConnect。请确认 AnkiConnect 已启用；${retryError.message}`;
      }
      throw retryError;
    }
  }
}

function buildBack(entry, existingBack = "") {
  const oldMeaning = String(existingBack)
    .split(/(?:<br\s*\/?\s*>|\r?\n){2}\s*Zotero 收录次数：/i)[0]
    .trim();
  const cleanedMeaning = cleanMeaning(entry.meaning);
  const existingHumanMeaning = oldMeaning && oldMeaning !== "（待填写释义）";
  const meaning = existingHumanMeaning && (entry.meaningSource === "dictionary" || entry.preserveAnkiMeaning)
    ? oldMeaning
    : cleanedMeaning
    ? escapeHTML(cleanedMeaning).replace(/\r?\n/g, "<br>")
    : (existingHumanMeaning ? oldMeaning : "（待填写释义）");
  const sources = escapeHTML((entry.sources || []).join("；"));
  return `${meaning}<br><br>Zotero 收录次数：${entry.count}<br>来源：${sources}`;
}

async function findPluginNote(word) {
  const ids = await requestAnki("findNotes", { query: `tag:${ANKI_TAG}` });
  if (!ids?.length) return null;
  const notes = await requestAnki("notesInfo", { notes: ids });
  const key = normalizeWord(word);
  return notes.find((note) => Object.values(note.fields || {}).some(
    (field) => field.order === 0 && normalizeAnkiField(field.value) === key,
  )) || null;
}

async function findMatchingNote(word, modelName, frontField) {
  const owned = await findPluginNote(word);
  if (owned) return { note: owned, owned: true };
  const queryWord = String(word).replace(/\\/g, "\\\\").replace(/"/g, "\\\"");
  const ids = await requestAnki("findNotes", { query: `"${queryWord}"` });
  if (!ids?.length) return null;
  const notes = await requestAnki("notesInfo", { notes: ids });
  const key = normalizeWord(word);
  const note = notes.find((candidate) => candidate.modelName === modelName &&
    normalizeAnkiField(candidate.fields?.[frontField]?.value) === key);
  return note ? { note, owned: false } : null;
}

function appendCaptureMetadata(existingBack, entry) {
  const base = String(existingBack || "")
    .split(/(?:<br\s*\/?\s*>|\r?\n){2}\s*Zotero 收录次数：/i)[0].trim();
  const meaning = base && base !== "（待填写释义）" ? base :
    (cleanMeaning(entry.meaning) ? escapeHTML(cleanMeaning(entry.meaning)).replace(/\r?\n/g, "<br>") : "（待填写释义）");
  const sources = escapeHTML((entry.sources || []).join("；"));
  return `${meaning}<br><br>Zotero 收录次数：${entry.count}<br>来源：${sources}`;
}

async function syncWord(word) {
  const data = loadData();
  const entry = data[word];
  if (!entry) return;

  const config = await ensureAnkiConfig();
  const fields = await requestAnki("modelFieldNames", { modelName: config.modelName });
  if (!fields?.includes(config.frontField) || !fields?.includes(config.backField)) {
    throw new Error(`Anki 笔记类型“${config.modelName}”中找不到字段“${config.frontField}”或“${config.backField}”。`);
  }
  if (fields[0] !== config.frontField) {
    throw new Error(`“${config.frontField}”必须是 Anki 笔记类型的第一个字段，才能正确拦截重复卡片。`);
  }
  await requestAnki("createDeck", { deck: config.deckName });
  const match = await findMatchingNote(entry.word, config.modelName, config.frontField);
  const note = match?.note || null;
  const optionalFields = {
    "例句": entry.examples,
    "权威例句": [entry.authoritativeExamples, ...(entry.literatureExamples || []).map(formatLiteratureExample)].filter(Boolean).join("\n"),
    "词根": entry.etymology ? `词源：${entry.etymology}` : "",
    "近义词": entry.synonyms,
    "音标": entry.phonetic,
    "英语发音": entry.audioURL ? `<a href="${escapeHTML(entry.audioURL)}">🔊 在线发音</a>` : "",
    "标签": "Zotero 高亮收录",
  };
  const mappedFields = Object.fromEntries(Object.entries(optionalFields)
    .filter(([field, value]) => fields.includes(field) && value)
    .map(([field, value]) => [field, escapeHTML(value).replace(/\r?\n/g, "<br>")]));
  if (note) {
    if (note.modelName !== config.modelName) {
      throw new Error(`Anki 中已有“${entry.word}”卡片，使用笔记类型“${note.modelName}”；请先把设置改回该类型。`);
    }
    if (match.owned && note.cards?.length) {
      await requestAnki("changeDeck", { cards: note.cards, deck: config.deckName });
    }
    if (!match.owned) {
      entry.preserveAnkiMeaning = true;
      const latestData = loadData();
      if (latestData[word]) {
        latestData[word].preserveAnkiMeaning = true;
        saveData(latestData);
      }
    }
    const optionalUpdates = Object.fromEntries(Object.entries(mappedFields)
      .filter(([field]) => !String(note.fields?.[field]?.value || "").trim()));
    if (fields.includes("权威例句") && entry.literatureExamples?.length) {
      const existingExamples = String(note.fields?.["权威例句"]?.value || "");
      const additions = entry.literatureExamples.map(formatLiteratureExample)
        .filter(value => !existingExamples.includes(escapeHTML(value)));
      if (additions.length) {
        const appended = additions.map(value => escapeHTML(value).replace(/\r?\n/g, "<br>")).join("<br><br>");
        optionalUpdates["权威例句"] = existingExamples ? `${existingExamples}<br><br>${appended}` : mappedFields["权威例句"];
      }
    }
    await requestAnki("updateNoteFields", {
      note: {
        id: note.noteId,
        fields: {
          [config.frontField]: escapeHTML(entry.word),
          [config.backField]: match.owned
            ? buildBack(entry, note.fields?.[config.backField]?.value)
            : appendCaptureMetadata(note.fields?.[config.backField]?.value, entry),
          ...optionalUpdates,
        },
      },
    });
    if (!match.owned) await requestAnki("addTags", { notes: [note.noteId], tags: `${ANKI_TAG} ${DICTIONARY_TAG}` });
  } else {
    let noteID;
    try { noteID = await requestAnki("addNote", {
      note: {
        deckName: config.deckName,
        modelName: config.modelName,
        fields: { [config.frontField]: escapeHTML(entry.word), [config.backField]: buildBack(entry), ...mappedFields },
        tags: [ANKI_TAG, DICTIONARY_TAG],
        options: { allowDuplicate: false },
      },
    }); } catch (error) {
      if (!/duplicate/i.test(String(error.message || error))) throw error;
      const latest = loadData();
      if (latest[word]) {
        latest[word].syncStatus = "duplicate";
        latest[word].syncError = "";
        saveData(latest);
      }
      return { duplicate: true, pending: false };
    }
    if (!noteID) throw new Error(`Anki 已有“${entry.word}”卡片，未覆盖现有笔记。`);
  }
  const latest = loadData();
  if (latest[word]) {
    latest[word].lastSyncedAt = Date.now();
    if (latest[word].revision === entry.revision) {
      latest[word].syncStatus = "synced";
      latest[word].syncError = "";
    }
    saveData(latest);
  }
  return { updated: !!note, duplicate: !!note && !match.owned, pending: latest[word]?.syncStatus !== "synced" };
}

function enqueueSync(word, automatic = false) {
  // Manual requests also wait for any already scheduled update of this word.
  const existing = queuedSyncs.get(word);
  if (existing && automatic) return existing;
  const currentGeneration = generation;
  const task = syncQueue.catch(() => {}).then(async () => {
    if (currentGeneration !== generation || (automatic && !isAutoSyncEnabled())) return { skipped: true };
    try {
      let result;
      for (let attempt = 0; attempt < 3; attempt++) {
        result = await syncWord(word);
        if (!result?.pending || currentGeneration !== generation || (automatic && !isAutoSyncEnabled())) break;
      }
      return result;
    } catch (error) {
      const data = loadData();
      if (data[word]) {
        data[word].syncStatus = "error";
        data[word].syncError = String(error.message || error);
        saveData(data);
      }
      throw error;
    }
  });
  syncQueue = task;
  queuedSyncs.set(word, task);
  const clear = () => { if (queuedSyncs.get(word) === task) queuedSyncs.delete(word); };
  task.then(clear, clear);
  return task;
}

async function retryPending() {
  if (!isAutoSyncEnabled() || retryInProgress) return;
  retryInProgress = true;
  try {
    const words = Object.entries(loadData())
      .filter(([, entry]) => !["synced", "duplicate"].includes(entry.syncStatus))
      .slice(0, 10).map(([word]) => word);
    let synced = 0;
    for (const word of words) {
      try {
        const result = await enqueueSync(word, true);
        if (!result?.skipped && !result?.pending) synced++;
      } catch (error) {
        reportBackgroundError(error);
        if (error.ankiUnavailable) break;
      }
    }
    if (synced) notifyUser("待同步词汇已补发", `已同步 ${synced} 个词条到 Anki。`);
  } finally {
    retryInProgress = false;
  }
}

function reportBackgroundError(error) {
  Zotero.debug(`[VocabReview] ${error.message || error}`);
}

async function syncAll(win) {
  const words = Object.keys(loadData());
  if (!words.length) {
    win.alert("词库还是空的。请先在 PDF 中高亮或给单词加下划线。");
    return;
  }
  let succeeded = 0;
  const errors = [];
  for (const word of words) {
    try { await enqueueSync(word); succeeded++; }
    catch (error) { errors.push(`${word}：${error.message || error}`); }
  }
  win.alert(`同步完成：成功 ${succeeded} 个，失败 ${errors.length} 个。` +
    (errors.length ? `\n失败词条仍保存在 Zotero：\n${errors.slice(0, 5).join("\n")}` : ""));
}

async function diagnose(win) {
  let config = getAnkiConfig();
  let detectionError = "";
  try { config = await ensureAnkiConfig(); }
  catch (error) { detectionError = String(error.message || error); }
  const lines = [`插件版本：${PLUGIN_VERSION}`, `监听器：${notifierID ? "已注册" : "未注册"}`,
    `自动同步：${isAutoSyncEnabled() ? "开启" : "关闭"}；定时复习：${isPopupEnabled() ? "开启" : "暂停"}`,
    `牌组：${config.deckName}`, `笔记类型：${config.modelName}`,
    `字段：${config.frontField} → ${config.backField}`,
    `最近捕获：${lastCaptureAt ? new Date(lastCaptureAt).toLocaleString() : "本次启动尚未捕获"}`];
  try {
    const data = Object.values(loadData());
    lines.push(`本地词条：${data.length}；待同步/失败：${data.filter(e => !["synced", "duplicate"].includes(e.syncStatus)).length}`);
    const failed = data.find(e => e.syncError);
    if (failed) lines.push(`最近同步错误：${failed.syncError}`);
  } catch (error) { lines.push(error.message); }
  if (detectionError) lines.push(`自动配置尚未完成：${detectionError}`);
  try {
    const version = await requestAnki("version");
    const fields = await requestAnki("modelFieldNames", { modelName: config.modelName });
    if (fields[0] !== config.frontField || !fields.includes(config.backField)) {
      throw new Error("笔记字段不匹配");
    }
    lines.push(`AnkiConnect：连接正常（API ${version}），字段检查通过`);
  } catch (error) { lines.push(`AnkiConnect 检查失败：${error.message || error}`); }
  win.alert(lines.join("\n"));
}

async function configureAnki(win) {
  try {
    let current = getAnkiConfig();
    try { current = await ensureAnkiConfig(); } catch (_) { /* Manual setup remains available offline. */ }
    const endpoint = win.prompt("AnkiConnect 本机地址：", current.endpoint);
    if (endpoint === null) return;
    const deckName = win.prompt("Anki 牌组名称：", current.deckName);
    if (deckName === null) return;
    const modelName = win.prompt("Anki 笔记类型名称：", current.modelName);
    if (modelName === null) return;
    const frontField = win.prompt("单词字段名称：", current.frontField);
    if (frontField === null) return;
    const backField = win.prompt("释义/语境字段名称：", current.backField);
    if (backField === null) return;
    if (!endpoint.trim() || !deckName.trim() || !modelName.trim() || !frontField.trim()
        || !backField.trim() || frontField.trim() === backField.trim()) {
      win.alert("配置无效：请填写所有项目，并为单词和释义选择不同的字段。");
      return;
    }

    const config = {
      endpoint: endpoint.trim(),
      deckName: deckName.trim(),
      modelName: modelName.trim(),
      frontField: frontField.trim(),
      backField: backField.trim(),
    };
    const modelNames = await requestAnki("modelNames", {}, config.endpoint);
    if (!modelNames?.includes(config.modelName)) {
      throw new Error(`Anki 中找不到笔记类型“${config.modelName}”。`);
    }
    const fields = await requestAnki("modelFieldNames", { modelName: config.modelName }, config.endpoint);
    if (!fields?.includes(config.frontField) || !fields?.includes(config.backField)) {
      throw new Error(`笔记类型“${config.modelName}”缺少字段“${config.frontField}”或“${config.backField}”。`);
    }
    if (fields[0] !== config.frontField) {
      throw new Error(`“${config.frontField}”必须是笔记类型的第一个字段，才能正确拦截重复卡片。`);
    }
    await requestAnki("createDeck", { deck: config.deckName }, config.endpoint);
    saveAnkiConfig(config);
    win.alert(`Anki 目标已保存：${config.deckName} / ${config.modelName}。`);
  } catch (error) {
    win.alert(`Anki 配置失败：${error.message || error}`);
  }
}

function nextReview(data) {
  const now = Date.now();
  return Object.entries(data)
    .filter(([, entry]) => (entry.dueAt || 0) <= now)
    .sort((a, b) => {
      const priorityA = (a[1].count || 1) / (1 + (a[1].reviews || 0));
      const priorityB = (b[1].count || 1) / (1 + (b[1].reviews || 0));
      return priorityB - priorityA || (a[1].dueAt || 0) - (b[1].dueAt || 0);
    })[0] || null;
}

function reviewOne(win) {
  const data = loadData();
  const selected = nextReview(data);
  if (!selected) {
    win.alert("当前没有到期词条。");
    return;
  }
  const [key, entry] = selected;
  const recall = win.prompt(`请先回想这个词的释义：\n\n${entry.word}`, "");
  if (recall === null) return;

  if (!entry.meaning) {
    const meaning = win.prompt(`“${entry.word}”还没有保存释义。请填写核对后的释义（可留空，之后再补）：`, "");
    if (meaning === null) return;
    if (meaning.trim()) { entry.meaning = meaning.trim(); entry.meaningSource = "manual"; }
  }
  win.alert(`你的答案：${recall || "（未填写）"}\n\n保存的释义：${entry.meaning || "（尚未填写）"}`);
  const remembered = win.confirm("这次你记得这个词吗？\n确定：记得　取消：不记得");
  entry.reviews = (entry.reviews || 0) + 1;
  if (remembered) {
    const growth = 2 - 0.15 * (Math.min(entry.count || 1, 5) - 1);
    entry.intervalDays = entry.intervalDays
      ? Math.max(entry.intervalDays + 1, Math.round(entry.intervalDays * growth)) : 1;
    entry.dueAt = Date.now() + entry.intervalDays * 24 * 60 * 60 * 1000;
  } else {
    entry.intervalDays = 0;
    entry.dueAt = Date.now() + 10 * 60 * 1000;
  }
  markPending(entry);
  saveData(data);
  if (isAutoSyncEnabled()) {
    enqueueSync(key, true).catch((error) => notifyUser("复习已保存，Anki 同步失败", String(error.message || error)));
  }
}

function listWords(win) {
  const data = loadData();
  const lines = Object.values(data)
    .sort((a, b) => b.count - a.count)
    .slice(0, 40)
    .map((entry) => `${entry.word} — 收录 ${entry.count} 次 — ${entry.syncStatus === "synced" ? "已同步" : entry.syncStatus === "duplicate" ? "发现已有卡片" : entry.syncStatus === "error" ? "同步失败" : "待同步"} — ${entry.meaning || "待填写释义"}`);
  win.alert(lines.length ? lines.join("\n") : "词库还是空的。");
}

function isPopupEnabled() {
  return Zotero.Prefs.get(PREF_PREFIX + "reviewPopups", true) !== false;
}

function setPopupEnabled(enabled) {
  Zotero.Prefs.set(PREF_PREFIX + "reviewPopups", enabled, true);
  schedulePopup();
  notifyUser(enabled ? "定时复习提醒已开启" : "定时复习提醒已暂停", "仍可从“工具”菜单手动复习。");
}

function schedulePopup() {
  clearTimeout(popupTimer);
  if (!isPopupEnabled()) return;
  const delay = (30 + Math.random() * 60) * 60 * 1000;
  popupTimer = setTimeout(() => {
    try {
      const win = Zotero.getMainWindow();
      if (win?.document?.hasFocus?.()) {
        const selected = nextReview(loadData());
        if (selected) reviewOne(win);
      }
    } catch (error) {
      reportBackgroundError(error);
      notifyUser("复习提醒暂时无法显示", String(error.message || error));
    } finally {
      if (running) schedulePopup();
    }
  }, delay);
}

function exportData() {
  return JSON.stringify({ format: "zotero-vocab-review", version: 1,
    exportedAt: new Date().toISOString(), words: loadData() }, null, 2);
}

async function exportVocabulary(win) {
  const text = exportData();
  const { FilePicker } = ChromeUtils.importESModule("chrome://zotero/content/modules/filePicker.mjs");
  const picker = new FilePicker();
  picker.init(win, "导出词库备份", picker.modeSave);
  picker.defaultString = `zotero-vocabulary-${new Date().toISOString().slice(0, 10)}.json`;
  picker.defaultExtension = "json";
  picker.appendFilter("JSON 词库", "*.json");
  if (await picker.show() === picker.returnCancel) return;
  await Zotero.File.putContentsAsync(picker.file, text);
  notifyUser("词库备份已导出", picker.file);
}

function StatusEndpoint() {}
StatusEndpoint.prototype = {
  supportedMethods: ["GET"],
  supportedDataTypes: ["application/json"],
  permitBookmarklet: false,
  init(_request) {
    const status = { version: PLUGIN_VERSION, running, listenerRegistered: !!notifierID,
      autoSync: isAutoSyncEnabled(), reviewPopups: isPopupEnabled(), lastCaptureAt };
    try {
      const entries = Object.values(loadData());
      status.words = entries.length;
      status.pending = entries.filter(entry => !["synced", "duplicate"].includes(entry.syncStatus)).length;
      status.failed = entries.filter(entry => entry.syncStatus === "error").length;
    } catch (_) { status.storageError = true; }
    // Only aggregate health information is returned; word text and meanings stay private.
    return [200, "application/json", JSON.stringify(status)];
  },
};

function menuItem(label, onCommand, visible = () => true) {
  return {
    menuType: "menuitem",
    onShowing: (_event, context) => {
      context.menuElem.setAttribute("label", label);
      context.setVisible(visible());
    },
    onCommand: () => {
      Promise.resolve().then(onCommand).catch((error) => notifyUser("词汇插件操作失败", String(error.message || error)));
    },
  };
}

function registerMenus() {
  menuRegistrationID = Zotero.MenuManager.registerMenu({
    menuID: MENU_ID, pluginID: PLUGIN_ID, target: "main/menubar/tools",
    menus: [
      menuItem("词汇：状态与连接诊断", () => diagnose(Zotero.getMainWindow())),
      menuItem("词汇：复习到期单词", () => reviewOne(Zotero.getMainWindow())),
      menuItem("词汇：同步词库到 Anki", () => syncAll(Zotero.getMainWindow())),
      menuItem("词汇：开启标记自动同步到 Anki", enableAutoSync, () => !isAutoSyncEnabled()),
      menuItem("词汇：关闭标记自动同步到 Anki", disableAutoSync, isAutoSyncEnabled),
      menuItem("词汇：查看词库与同步状态", () => listWords(Zotero.getMainWindow())),
      menuItem("词汇：开启定时复习提醒", () => setPopupEnabled(true), () => !isPopupEnabled()),
      menuItem("词汇：暂停定时复习提醒", () => setPopupEnabled(false), isPopupEnabled),
      menuItem("词汇：导出词库备份", () => exportVocabulary(Zotero.getMainWindow())),
      menuItem("词汇：配置 Anki 牌组与字段", () => configureAnki(Zotero.getMainWindow())),
      menuItem("词汇：设置通知弹窗时长", () => setNotificationSeconds(Zotero.getMainWindow())),
    ],
  });
}

async function startup() {
  const currentGeneration = ++generation;
  await Zotero.initializationPromise;
  await Zotero.uiReadyPromise;
  if (currentGeneration !== generation) return;
  running = true;
  notifierID = Zotero.Notifier.registerObserver(
    {
      notify(event, type, ids) {
        if (type !== "item" || !["add", "modify"].includes(event)) return;
        captureQueue = captureQueue
          .then(async () => {
            for (const id of ids) await captureAnnotation(id);
          })
          .catch((error) => {
            Zotero.debug(`[VocabReview] Capture failed: ${error}`);
            notifyUser("高亮处理失败", `词汇未能正常收录：${error.message || error}`);
          });
      },
    },
    ["item"],
    "zotero-vocab-review",
  );
  try {
    registerMenus();
      await Zotero.PreferencePanes.register({
        pluginID: PLUGIN_ID, id: "zotero-vocab-review-preferences", label: "Zotero 划词同步到 Anki",
        src: "prefs.xhtml",
      });
    Zotero.Server.Endpoints[STATUS_PATH] = StatusEndpoint;
    schedulePopup();
  } catch (error) {
    shutdown();
    notifyUser("词汇插件启动失败", String(error.message || error));
    throw error;
  }
  Zotero.Prefs.set(PREF_PREFIX + "lastStartup", JSON.stringify({ version: PLUGIN_VERSION, at: Date.now() }), true);
  void retryPending().catch(reportBackgroundError);
  retryTimer = setInterval(() => { void retryPending().catch(reportBackgroundError); }, 60000);
  notifyUser(`词汇插件已启动（${PLUGIN_VERSION}）`, `已监听高亮和下划线；自动同步${isAutoSyncEnabled() ? "开启" : "关闭"}。可在“工具 → 词汇：状态与连接诊断”查看详情。`);
}


function shutdown() {
  generation++;
  running = false;
  if (Zotero.Server.Endpoints[STATUS_PATH] === StatusEndpoint) delete Zotero.Server.Endpoints[STATUS_PATH];
  if (notifierID) Zotero.Notifier.unregisterObserver(notifierID);
  notifierID = null;
  if (menuRegistrationID) Zotero.MenuManager.unregisterMenu(menuRegistrationID);
  menuRegistrationID = null;
  clearTimeout(popupTimer);
  for (const timer of notificationTimers) clearTimeout(timer);
  notificationTimers.clear();
  clearInterval(retryTimer);
  retryTimer = null;
}
