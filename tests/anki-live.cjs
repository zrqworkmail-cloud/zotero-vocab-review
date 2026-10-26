// Runs the plugin's real sync code against a temporary Anki deck, then removes only its own notes/deck.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createHarness } = require('./harness.cjs');
if (!process.argv.includes('--live')) {
  console.error('Use --live to authorize temporary test notes in your running local Anki.'); process.exit(2);
}
const endpoint = process.env.ZVR_ANKI_ENDPOINT || 'http://127.0.0.1:8765';
const suffix = crypto.randomBytes(6).toString('hex');
const deck = 'ZVR-Verification-' + suffix;
const word = 'zvrverify' + suffix;
const createdNotes = [];
const report = { at: new Date().toISOString(), pluginVersion: JSON.parse(fs.readFileSync(path.join(__dirname,'..','manifest.json'))).version, checks: [], cleanup: {} };
let deckCreated = false;
let simulateOffline = false;
async function call(action, params = {}) {
  const response = await fetch(endpoint, { method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({action,version:6,params}), signal:AbortSignal.timeout(8000) });
  const body = await response.json();
  if (body.error) throw new Error(body.error);
  return body.result;
}
(async () => {
  try {
    assert.equal(await call('version'), 6);
    await call('createDeck', {deck}); deckCreated = true;
    const h = createHarness({httpRequest: async (_method,_url,request) => {
      if (simulateOffline) throw new Error('simulated offline');
      const {action, params} = JSON.parse(request.body);
      const result = await call(action, params);
      if (action === 'addNote' && result) createdNotes.push(result);
      return {response:JSON.stringify({result,error:null})};
    }});
    const prefix = 'extensions.zotero.vocabReview.';
    h.prefs.set(prefix+'deckName',deck);
    h.prefs.set(prefix+'endpoint',endpoint);
    const config = await h.run('ensureAnkiConfig()');
    assert.ok(config.modelName && config.frontField && config.backField);
    report.checks.push('First-use automatic Anki template/field configuration completed');
    const fields = await call('modelFieldNames',{modelName:config.modelName});
    const initialFields = Object.fromEntries(fields.map(field => [field,'']));
    initialFields[config.frontField]=word;
    initialFields[config.backField]='Pre-existing manual test explanation';
    const preexistingID = await call('addNote',{note:{deckName:deck,modelName:config.modelName,fields:initialFields,
      tags:['zvr_unowned_test'],options:{allowDuplicate:false}}});
    createdNotes.push(preexistingID);
    h.annotation(1,word,'highlight','临时验证释义');
    await h.run('captureAnnotation(1)'); await h.settle();
    assert.equal(h.getData()[word].syncStatus,'synced'); assert.equal(createdNotes.length,1);
    let note = (await call('notesInfo',{notes:[preexistingID]}))[0];
    assert.match(note.fields[config.backField].value,/Pre-existing manual test explanation/);
    assert.ok(note.tags.includes('zotero_vocab_review'));
    report.checks.push('Plugin adopted an existing untagged note, preserved its explanation, and filled only blank fields');
    h.annotation(2,word.toUpperCase(),'underline');
    await h.run('captureAnnotation(2)'); await h.settle();
    assert.equal(h.getData()[word].count,2); assert.equal(createdNotes.length,1);
    note = (await call('notesInfo',{notes:createdNotes}))[0];
    assert.match(note.fields[config.backField].value,/收录次数：2/);
    assert.match(note.fields[config.backField].value,/Pre-existing manual test explanation/);
    report.checks.push('Underline/case variant updated the existing real note without duplication');
    simulateOffline = true;
    h.annotation(3,word,'highlight');
    await h.run('captureAnnotation(3)'); await h.settle();
    assert.equal(h.getData()[word].syncStatus,'error');
    simulateOffline = false;
    await h.run('retryPending()'); await h.settle();
    assert.equal(h.getData()[word].syncStatus,'synced');
    note = (await call('notesInfo',{notes:createdNotes}))[0];
    assert.match(note.fields[config.backField].value,/收录次数：3/);
    assert.equal(createdNotes.length,1);
    report.checks.push('Offline failure persisted locally; retry updated the same real Anki note');
    h.run('disableAutoSync()');
    h.annotation(4,word,'underline'); const before = h.calls.length;
    await h.run('captureAnnotation(4)'); await h.settle();
    assert.equal(h.calls.length,before);
    assert.equal(h.getData()[word].syncStatus,'pending');
    report.checks.push('Auto sync switch prevented network writes while retaining local count');
    report.passed = true;
  } catch (error) { report.passed = false; report.error = String(error.stack || error); process.exitCode=1; }
  finally {
    try {
      if (createdNotes.length) {
        await call('deleteNotes',{notes:createdNotes});
        report.cleanup.createdNotesRemoved = (await call('notesInfo',{notes:createdNotes})).every(note => !note || Object.keys(note).length===0);
      }
      if (deckCreated) {
        const cards = await call('findCards',{query:`deck:"${deck}"`});
        assert.equal(cards.length,0,'Refusing to remove deck containing unexpected cards');
        await call('deleteDecks',{decks:[deck],cardsToo:true});
        report.cleanup.temporaryDeckRemoved = !(await call('deckNames')).includes(deck);
      }
    } catch (error) { report.cleanup.error=String(error); report.passed=false; process.exitCode=1; }
    fs.mkdirSync(path.join(__dirname,'..','.verification'),{recursive:true});
    fs.writeFileSync(path.join(__dirname,'..','.verification','anki-live.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  }
})();
