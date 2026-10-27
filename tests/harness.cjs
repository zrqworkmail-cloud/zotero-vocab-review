const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function createHarness(options = {}) {
  const prefs = new Map();
  const items = new Map();
  const notes = new Map();
  const models = new Map(Object.entries(options.models || { Basic: ['Front', 'Back'] }));
  const notifications = [];
  const menus = [];
  const calls = [];
  const alerts = [];
  let nextID = 100;
  let fail = false;
  let observer;
  let nextTimer = 0;
  const timers = new Map();
  const win = {
    alert: text => alerts.push(text),
    prompt: () => null,
    confirm: () => true,
    document: { hasFocus: () => true },
  };
  const context = vm.createContext({
    console,
    setTimeout: (callback, delay = 0) => { const id = ++nextTimer; timers.set(id, {callback, delay}); return id; },
    clearTimeout: id => timers.delete(id),
    setInterval: () => 2, clearInterval: () => {},
    Zotero: {
      Server: { Endpoints: {} },
      locale: 'zh-CN', initializationPromise: Promise.resolve(), uiReadyPromise: Promise.resolve(),
      Prefs: { get: key => prefs.get(key), set: (key, val) => prefs.set(key, val) },
      Items: { get: id => items.get(id) },
      PreferencePanes: { register: async () => {} },
      Notifier: {
        registerObserver: ref => { observer = ref; return 'observer'; },
        unregisterObserver: () => { observer = null; },
      },
      MenuManager: { registerMenu: value => { menus.push(value); return 'menu'; }, unregisterMenu: () => {} },
      getMainWindow: () => win,
      debug: () => {}, logError: () => {},
      ProgressWindow: class {
        constructor() { this.notification = {closed:false}; notifications.push(this.notification); }
        changeHeadline(value) { this.notification.headline = value; }
        addDescription(value) { this.notification.details = value; }
        show() {} startCloseTimer() {}
        close() { this.notification.closed = true; }
      },
      HTTP: {
        request: async (method, url, request) => {
          if (method === 'GET') {
            if (options.dictionaryFailure) throw new Error('dictionary offline');
            return {response:JSON.stringify(options.dictionaryResponse || {
              collins_primary: { gramcat: [{
                partofspeech: 'adv.', pronunciation: '/ˈtɛst/',
                senses: [{ word: '测试释义', examples: [{ example: 'This is a test.', sense: { word: '这是一个测试。' } }] }],
              }] },
              simple: {word:[{ukphone:'/ˈtɛst/',usspeech:'test&type=2'}]},
              expand_ec: {word:[{transList:[{trans:'经过验证的释义',content:{detailPos:'adv.',sents:[
                {sentSpeech:'A trusted example.',sentTrans:'可靠例句',sourceType:'权威'},
                {sentSpeech:'Another example.',sentTrans:'另一个例句',sourceType:'例句'},
              ]}}]}]},
              syno:{synos:[{syno:{ws:[{w:'verified synonym'}]}}]},
              etym:{etyms:{en:[{source:'Wiktionary',value:'A verified word history.'}]}},
            })};
          }
          const body = JSON.parse(request.body);
          calls.push(body);
          if (options.beforeRequest) await options.beforeRequest(body);
          if (options.httpRequest) return options.httpRequest(method, url, request);
          if (fail) throw new Error('offline');
          const p = body.params;
          let result = null;
          if (body.action === 'version') result = 6;
          else if (body.action === 'modelNames') result = [...models.keys()];
          else if (body.action === 'modelFieldNames') {
            if (!models.has(p.modelName)) return {response:JSON.stringify({result:null,error:'model not found'})};
            result = models.get(p.modelName);
          } else if (body.action === 'createModel') {
            models.set(p.modelName,p.inOrderFields); result={name:p.modelName};
          } else if (body.action === 'cardsInfo') result=p.cards.map(() => ({deckName:'Legacy Vocabulary'}));
          else if (body.action === 'createDeck') result = 1;
          else if (body.action === 'findNotes') {
            if (p.query.startsWith('tag:')) result = [...notes.values()].filter(n => n.tags?.includes(p.query.slice(4))).map(n => n.noteId);
            else {
              const needle = p.query.slice(1,-1).replace(/\\"/g,'"').replace(/\\\\/g,'\\');
              result = [...notes.values()].filter(n => {
                const front = Object.values(n.fields).find(field => field.order === 0)?.value || '';
                return String(front).replace(/<[^>]*>/g,'').replace(/&amp;/g,'&').toLowerCase() === needle.toLowerCase();
              }).map(n => n.noteId);
            }
          }
          else if (body.action === 'notesInfo') result = p.notes.map(id => notes.get(id)).filter(Boolean);
          else if (body.action === 'addNote') {
            if ([...notes.values()].some(n => Object.values(n.fields)[0].value === Object.values(p.note.fields)[0])) {
              return { response: JSON.stringify({ error: 'duplicate', result: null }) };
            }
            result = ++nextID;
            const modelFields = models.get(p.note.modelName) || Object.keys(p.note.fields);
            notes.set(result, {noteId: result, modelName: p.note.modelName, tags: p.note.tags,
              fields: Object.fromEntries(modelFields.map((key,order) => [key,{value:p.note.fields[key] || '',order}])),
              cards: [result + 1000]});
          } else if (body.action === 'updateNoteFields') {
            const note = notes.get(p.note.id);
            for (const [key,value] of Object.entries(p.note.fields)) {
              if (!note.fields[key]) note.fields[key] = {value:'',order:Object.keys(note.fields).length};
              note.fields[key].value = value;
            }
          } else if (body.action === 'addTags') {
            for (const id of p.notes) {
              const note=notes.get(id);
              note.tags=[...new Set([...(note.tags || []), ...p.tags.split(/\s+/).filter(Boolean)])];
            }
          } else if (body.action !== 'changeDeck') throw new Error('Unexpected action: ' + body.action);
          return { response: JSON.stringify({ error: null, result }) };
        },
      },
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'bootstrap.js'), 'utf8'), context);
  return {
    context, prefs, items, notes, models, notifications, calls, alerts, menus, win,
    run: expr => vm.runInContext(expr, context),
    getData: () => JSON.parse(prefs.get('extensions.zotero.vocabReview.data') || '{}'),
    settle: async () => {
      await vm.runInContext('captureQueue', context);
      await vm.runInContext('Promise.allSettled([...dictionaryLookups.values()])', context);
      await vm.runInContext('syncQueue.catch(() => {})', context);
      await Promise.resolve();
    },
    fireTimers: delay => {
      for (const [id, timer] of [...timers]) if (timer.delay === delay) { timers.delete(id); timer.callback(); }
    },
    fail: value => { fail = value; },
    emit: (...args) => observer.notify(...args),
    annotation: (id, text, type = 'highlight', comment = '') => items.set(id, {
      key: 'K' + id, libraryID: 1, annotationText: text, annotationType: type,
      annotationComment: comment, isAnnotation: () => true,
    }),
  };
}
module.exports = { createHarness };
