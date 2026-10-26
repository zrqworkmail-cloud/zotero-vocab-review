const test = require('node:test');
const assert = require('node:assert/strict');
const { createHarness } = require('./harness.cjs');

test('startup registers a working observer and visible menu labels', async () => {
  const h = createHarness();
  await h.run('startup()');
  for (const menu of h.menus[0].menus) {
    const attrs = {};
    menu.onShowing?.({}, {menuElem:{setAttribute:(key,val)=>attrs[key]=val},setVisible:()=>{}});
    assert.ok(attrs.label, 'Each menu must have a visible label without missing Fluent resources');
  }
  h.annotation(1, 'Research', 'underline');
  await h.emit('add', 'item', [1]);
  await h.settle();
  assert.equal(h.getData().research.count, 1);
  assert.equal(h.notes.size, 1);
  h.run('shutdown()');
});

test('distinct highlight/underline captures deduplicate case and repeated notifier events', async () => {
  const h = createHarness();
  h.annotation(1, 'Research');
  await h.run('captureAnnotation(1)'); await h.settle();
  h.annotation(2, 'research', 'underline');
  await h.run('captureAnnotation(2)'); await h.settle();
  await h.run('captureAnnotation(2)'); await h.settle();
  assert.equal(h.getData().research.count, 2);
  assert.equal(h.notes.size, 1);
  assert.match([...h.notes.values()][0].fields['Back'].value, /收录次数：2/);
  assert.ok(h.notifications.some(n => /第 2 次/.test(n.details)));
});

test('auto sync off persists local words without touching Anki', async () => {
  const h = createHarness();
  h.run('disableAutoSync()'); h.annotation(1, 'local');
  await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.calls.length, 0);
  assert.equal(h.getData().local.syncStatus, 'pending');
  assert.ok(h.notifications.some(n => /已关闭/.test(n.details)));
});

test('offline failure is visible, retained and retried without a second card', async () => {
  const h = createHarness(); h.fail(true); h.annotation(1, 'retry');
  await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.getData().retry.syncStatus, 'error');
  assert.ok(h.notifications.some(n => /同步失败/.test(n.details)));
  h.fail(false); await h.run('retryPending()'); await h.settle();
  assert.equal(h.getData().retry.syncStatus, 'synced');
  assert.equal(h.notes.size, 1);
  await h.run('retryPending()'); assert.equal(h.notes.size, 1);
});

test('malformed local storage is reported instead of overwritten', async () => {
  const h = createHarness(); h.prefs.set('extensions.zotero.vocabReview.data', '{broken');
  h.annotation(1, 'preserve');
  await assert.rejects(h.run('captureAnnotation(1)'), /词库|数据/);
  assert.equal(h.prefs.get('extensions.zotero.vocabReview.data'), '{broken');
});

test('ordinary words matching Object prototype properties are safely captured', async () => {
  const h = createHarness(); h.run('disableAutoSync()'); h.annotation(1, 'constructor');
  await h.run('captureAnnotation(1)');
  assert.equal(h.getData().constructor.count, 1);
});

test('long passages are skipped with one clear notification per annotation', async () => {
  const h = createHarness(); h.annotation(1, 'one two three four five six');
  await h.run('captureAnnotation(1)'); await h.run('captureAnnotation(1)');
  assert.equal(Object.keys(h.getData()).length, 0);
  assert.equal(h.notifications.length, 1);
});

test('an edit during an in-flight request reaches Anki before being marked synced', async () => {
  let release, reached;
  const added = new Promise(resolve => reached = resolve);
  const gate = new Promise(resolve => release = resolve);
  let paused = false;
  const h = createHarness({beforeRequest: async body => {
    if (body.action === 'addNote' && !paused) { paused = true; reached(); await gate; }
  }});
  h.annotation(1, 'concurrent'); await h.run('captureAnnotation(1)');
  await added;
  h.annotation(2, 'Concurrent', 'underline'); await h.run('captureAnnotation(2)');
  release(); await h.settle();
  assert.equal(h.getData().concurrent.count,2);
  assert.equal(h.getData().concurrent.syncStatus,'synced');
  assert.equal(h.notes.size,1);
  assert.match([...h.notes.values()][0].fields['Back'].value,/收录次数：2/);
});

test('turning auto sync off cancels requests that have not begun', async () => {
  const h = createHarness(); h.annotation(1,'cancelled');
  await h.run('captureAnnotation(1); disableAutoSync()'); await h.settle();
  assert.equal(h.calls.length,0);
  assert.equal(h.getData().cancelled.syncStatus,'pending');
  assert.ok(!h.notifications.some(n => /^已添加到 Anki/.test(n.headline)));
});

test('manual batch sync reports partial failure and still processes later words', async () => {
  const h = createHarness({beforeRequest: async body => {
    if (body.action === 'addNote' && body.params.note.fields['Front'] === 'bad') throw new Error('reject bad');
  }});
  h.run('disableAutoSync()'); h.annotation(1,'bad'); h.annotation(2,'good');
  await h.run('captureAnnotation(1)'); await h.run('captureAnnotation(2)');
  await h.run('syncAll(Zotero.getMainWindow())');
  assert.equal(h.getData().bad.syncStatus,'error');
  assert.equal(h.getData().good.syncStatus,'synced');
  assert.match(h.alerts.at(-1),/成功 1 个，失败 1 个/);
});

test('same-word note outside plugin ownership keeps its explanation and is adopted safely', async () => {
  const h = createHarness();
  h.notes.set(1,{noteId:1,modelName:'Basic',tags:[],cards:[1001],fields:{'Front':{value:'owned',order:0},'Back':{value:'keep this',order:1}}});
  h.annotation(1,'owned'); await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.notes.size,1);
  assert.match(h.notes.get(1).fields['Back'].value,/^keep this/);
  assert.ok(h.notes.get(1).tags.includes('zotero_vocab_review'));
  assert.equal(h.getData().owned.syncStatus,'synced');
});

test('dictionary enrichment is not lost when matching an untagged card during an in-flight sync', async () => {
  let release, reached;
  const blocked = new Promise(resolve => reached=resolve);
  const gate = new Promise(resolve => release=resolve);
  let once=false;
  const h=createHarness({models:{'词汇模板':['正面','解释','例句','音标']},beforeRequest:async body=>{
    if(body.action==='findNotes' && body.params.query==='tag:zotero_vocab_review' && !once) {
      once=true; reached(); await gate;
    }
  }});
  h.run('saveAnkiConfig({endpoint:"http://127.0.0.1:8765",deckName:"Words",modelName:"词汇模板",frontField:"正面",backField:"解释"})');
  h.notes.set(7,{noteId:7,modelName:'词汇模板',tags:[],cards:[1007],fields:{
    '正面':{value:'racing',order:0},'解释':{value:'Keep this',order:1},'例句':{value:'',order:2},'音标':{value:'',order:3},
  }});
  h.annotation(1,'racing');
  await h.run('captureAnnotation(1)');
  await blocked;
  await h.run('Promise.allSettled([...dictionaryLookups.values()])');
  release();
  await h.settle();
  assert.match(h.notes.get(7).fields['例句'].value,/This is a test/);
  assert.match(h.notes.get(7).fields['音标'].value,/ˈtɛst/);
  assert.equal(h.getData().racing.syncStatus,'synced');
});

test('more encounters shorten review growth without trapping a remembered word at one day', () => {
  function review(count) {
    const h = createHarness(); h.run('disableAutoSync()');
    h.prefs.set('extensions.zotero.vocabReview.data',JSON.stringify({term:{word:'term',meaning:'含义',count,reviews:0,intervalDays:10,dueAt:0}}));
    h.win.prompt = () => '含义'; h.run('reviewOne(Zotero.getMainWindow())');
    return h.getData().term.intervalDays;
  }
  assert.ok(review(5)>10);
  assert.ok(review(5)<review(1));
});

test('backup preserves previous snapshot and exported JSON retains review/sync state', async () => {
  const h = createHarness(); h.run('disableAutoSync()'); h.annotation(1,'backup');
  await h.run('captureAnnotation(1)');
  h.annotation(2,'Backup'); await h.run('captureAnnotation(2)');
  const previous = JSON.parse(h.prefs.get('extensions.zotero.vocabReview.dataBackup'));
  assert.equal(previous.backup.count,2);
  const exported=JSON.parse(h.run('exportData()'));
  assert.equal(exported.words.backup.count,2);
  assert.equal(exported.words.backup.syncStatus,'pending');
});

test('local health endpoint exposes aggregate status and is removed at shutdown', async () => {
  const h=createHarness(); await h.run('startup()');
  const value=JSON.parse(h.run('new StatusEndpoint().init()[2]'));
  assert.equal(value.version,'0.4.0-beta.3');
  assert.equal(value.listenerRegistered,true);
  assert.equal(value.words,0);
  assert.equal(value.autoSync,true);
  h.run('shutdown()');
  assert.equal(h.run('Zotero.Server.Endpoints[STATUS_PATH]'),undefined);
});

test('first use automatically configures the available standard Basic template', async () => {
  const h=createHarness(); h.annotation(1,'onboarding');
  await h.run('captureAnnotation(1)'); await h.settle();
  const config=h.run('getAnkiConfig()');
  assert.equal(config.deckName,'Zotero Vocabulary');
  assert.equal(config.modelName,'Basic');
  assert.equal(config.frontField,'Front');
  assert.equal(h.notes.size,1);
  assert.ok(!h.calls.some(call => call.action==='createModel'));
});

test('first use detects localized field names without depending on English fields', async () => {
  const h=createHarness({models:{'问答题':['正面','背面']}}); h.annotation(1,'localized');
  await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.getData().localized.syncStatus,'synced');
  assert.equal(h.run('getAnkiConfig().backField'),'背面');
  assert.ok([...h.notes.values()][0].fields['正面']);
});

test('no recognized basic model creates an isolated vocabulary template once', async () => {
  const h=createHarness({models:{Cloze:['Text','Extra']}}); h.annotation(1,'dedicated');
  await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.run('getAnkiConfig().modelName'),'Zotero Vocabulary Review');
  assert.deepEqual(h.models.get('Zotero Vocabulary Review'),['Word','Meaning']);
  h.annotation(2,'again'); await h.run('captureAnnotation(2)'); await h.settle();
  assert.equal(h.calls.filter(call => call.action==='createModel').length,1);
  assert.equal(h.notes.size,2);
});

test('explicit existing custom configuration takes precedence over automatic defaults', async () => {
  const h=createHarness({models:{Custom:['Term','Definition','Example']}});
  h.run('saveAnkiConfig({endpoint:"http://127.0.0.1:8765",deckName:"Existing Deck",modelName:"Custom",frontField:"Term",backField:"Definition"})');
  h.annotation(1,'custom'); await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.run('getAnkiConfig().deckName'),'Existing Deck');
  assert.equal(h.calls.filter(call => call.action==='modelNames').length,0);
  assert.equal(h.getData().custom.syncStatus,'synced');
});

test('legacy plugin-tagged cards recover their model and deck without creating duplicates', async () => {
  const h=createHarness({models:{Legacy:['Term','Definition','Example']}});
  h.notes.set(1,{noteId:1,modelName:'Legacy',tags:['zotero_vocab_review'],cards:[1001],fields:{Term:{value:'legacy',order:0},Definition:{value:'existing meaning',order:1}}});
  h.annotation(1,'legacy'); await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.run('getAnkiConfig().deckName'),'Legacy Vocabulary');
  assert.equal(h.run('getAnkiConfig().modelName'),'Legacy');
  assert.equal(h.notes.size,1);
  assert.match(h.notes.get(1).fields.Definition.value,/existing meaning/);
});

test('incompatible dedicated model is reported without editing it or silently choosing fields', async () => {
  const h=createHarness({models:{'Zotero Vocabulary Review':['Word']}});
  h.annotation(1,'mismatch'); await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.getData().mismatch.syncStatus,'error');
  assert.equal(h.calls.filter(call => call.action==='createModel').length,0);
  assert.equal(h.prefs.has('extensions.zotero.vocabReview.modelName'),false);
});

test('completed annotation translations replace empty glyph placeholders and map available dictionary fields', async () => {
  const h=createHarness({models:{'词汇模板':['正面','解释','例句','权威例句','词根','近义词','音标','英语发音','标签']}});
  h.run('saveAnkiConfig({endpoint:"http://127.0.0.1:8765",deckName:"Words",modelName:"词汇模板",frontField:"正面",backField:"解释"})');
  h.annotation(1,'carefully','highlight','🔤🔤');
  await h.run('captureAnnotation(1)'); await h.settle();
  let note=[...h.notes.values()][0];
  assert.match(note.fields['解释'].value,/测试释义/);
  assert.match(note.fields['例句'].value,/This is a test\. — 这是一个测试。/);
  assert.equal(note.fields['音标'].value,'/ˈtɛst/');
  assert.match(note.fields['权威例句'].value,/A trusted example\./);
  assert.match(note.fields['词根'].value,/A verified word history/);
  assert.equal(note.fields['近义词'].value,'verified synonym');
  assert.match(note.fields['英语发音'].value,/dictvoice/);
  assert.ok(note.tags.includes('zotero_highlight'));
  h.annotation(1,'carefully','highlight','🔤');
  await h.run('captureAnnotation(1)');
  h.annotation(1,'carefully','highlight','小心地；仔细地');
  await h.run('captureAnnotation(1)'); await h.settle();
  note=[...h.notes.values()][0];
  assert.match(note.fields['解释'].value,/小心地；仔细地/);
  assert.doesNotMatch(note.fields['解释'].value,/🔤/);
});

test('dictionary failure does not prevent adding a word to Anki', async () => {
  const h=createHarness({dictionaryFailure:true}); h.annotation(1,'resilient');
  await h.run('captureAnnotation(1)'); await h.settle();
  assert.equal(h.getData().resilient.syncStatus,'synced');
  assert.equal(h.notes.size,1);
});

test('notification closes after five seconds by default and accepts a saved duration', async () => {
  const h=createHarness();
  h.run('notifyUser("notice")');
  assert.equal(h.run('getNotificationSeconds()'),5);
  assert.equal(h.notifications.at(-1).closed,false);
  h.fireTimers(5000);
  assert.equal(h.notifications.at(-1).closed,true);
  h.win.prompt=()=>"9";
  h.run('setNotificationSeconds(Zotero.getMainWindow())');
  assert.equal(h.run('getNotificationSeconds()'),9);
});
