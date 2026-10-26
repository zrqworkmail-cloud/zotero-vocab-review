// Appended only to the test XPI in a separate profile. Never shipped in the release XPI.
var productionStartup = startup;
startup = async function (...args) {
  await productionStartup(...args);
  setTimeout(() => void verifyInZotero(), 500);
};
async function verifyInZotero() {
  const profileDir = Services.dirsvc.get('ProfD', Components.interfaces.nsIFile).path;
  const base = PathUtils.parent(profileDir);
  const report = {at:new Date().toISOString(),pluginVersion:PLUGIN_VERSION,checks:[],cleanup:{}};
  const deck = 'ZVR-Runtime-' + Date.now();
  const word = 'thoroughly';
  let isolated = false, deckCreated = false;
  let testNoteID = null;
  const assert = (value,message) => { if (!value) throw new Error(message); };
  const settle = async () => { await Zotero.Promise.delay(150); await captureQueue;
    await Promise.allSettled([...dictionaryLookups.values()]); await syncQueue.catch(() => {}); await Zotero.Promise.delay(150); };
  try {
    report.profile = Services.dirsvc.get('ProfD', Components.interfaces.nsIFile).path;
    report.dataDir = Zotero.DataDirectory.dir;
    isolated = PathUtils.filename(profileDir) === 'profile' &&
      await Zotero.File.getContentsAsync(PathUtils.join(base,'.zvr-isolated-profile')) === 'ZVR_ISOLATED_RUNTIME_TEST';
    assert(isolated && report.dataDir.toLowerCase() === PathUtils.join(base,'data').toLowerCase(), 'Refusing to test outside the isolated profile/data directory');
    report.zoteroVersion = Zotero.version;
    const healthResponse = await Zotero.HTTP.request('GET','http://127.0.0.1:23129/vocab-review/status',{responseType:'text',headers:{'Zotero-Allowed-Request':'true'}});
    const health = JSON.parse(healthResponse.response);
    assert(health.running && health.listenerRegistered && health.version===PLUGIN_VERSION,'Actual local health endpoint did not confirm startup');
    report.checks.push('Actual local HTTP health endpoint confirmed plugin startup and listener registration');
    Zotero.Prefs.set(PREF_PREFIX+'deckName',deck,true);
    const config=await ensureAnkiConfig();
    report.checks.push('Actual first-use automatic model and field detection completed');
    assert(!(await findPluginNote(word)),"Test word already exists in the user's plugin-tagged Anki notes; refusing to modify it");
    assert(!(await requestAnki('deckNames')).includes(deck),'Test deck unexpectedly already exists');
    await requestAnki('createDeck',{deck}); deckCreated=true;
    const modelFields=await requestAnki('modelFieldNames',{modelName:config.modelName});
    const manualFields=Object.fromEntries(modelFields.map(field=>[field,'']));
    manualFields[config.frontField]=word;
    manualFields[config.backField]='Runtime manual test explanation';
    testNoteID=await requestAnki('addNote',{note:{deckName:deck,modelName:config.modelName,fields:manualFields,
      tags:['zvr_runtime_unowned'],options:{allowDuplicate:false}}});
    const attachment = new Zotero.Item('attachment');
    attachment.setField('title','Temporary vocabulary runtime verification');
    attachment.attachmentLinkMode = Zotero.Attachments.LINK_MODE_LINKED_FILE;
    attachment.attachmentPath = PathUtils.join(base,'fixture.pdf');
    attachment.attachmentContentType = 'application/pdf';
    await attachment.saveTx();
    async function addAnnotation(type,text,index) {
      const item = new Zotero.Item('annotation');
      item.libraryID=attachment.libraryID;
      item.parentID=attachment.id;
      item.annotationType=type;
      item.annotationText=text;
      item.annotationComment='临时隔离验证';
      item.annotationColor='#ffd400';
      item.annotationPageLabel='1';
      item.annotationSortIndex=`00000|00000${index}|00000`;
      item.annotationPosition=JSON.stringify({pageIndex:0,rects:[[10,10+index*10,70,20+index*10]]});
      await item.saveTx();
      await settle();
    }
    await addAnnotation('highlight',word,1);
    assert(loadData()[word]?.count===1,'Real Zotero item notification did not capture highlight');
    assert(loadData()[word].syncStatus==='synced','Real Zotero HTTP sync did not complete');
    assert(loadData()[word]?.dictionaryLookup==='done','Live Youdao lookup did not complete');
    let liveNotes=await requestAnki('findNotes',{query:`deck:"${deck}"`});
    assert(liveNotes.length===1 && liveNotes[0]===testNoteID,'Plugin created a duplicate instead of adopting the temporary untagged note');
    let liveInfo=(await requestAnki('notesInfo',{notes:liveNotes}))[0];
    assert(liveInfo.fields[config.backField].value.includes('Runtime manual test explanation'),'Existing note explanation was overwritten');
    assert(liveInfo.tags.includes('zotero_vocab_review'),'Existing note was not adopted for repeat-count updates');
    for(const field of ['音标','例句','权威例句','词根','近义词','英语发音'])
      assert(liveInfo.fields[field]?.value,`Live Youdao data did not populate Anki field ${field}`);
    report.checks.push('Live Youdao data populated pronunciation, examples, word history, synonyms, authoritative example, and audio-link fields');
    report.checks.push('Actual Zotero Notifier captured a saved PDF highlight and synced it through Zotero.HTTP to real Anki');
    await addAnnotation('underline',word.toUpperCase(),2);
    assert(loadData()[word]?.count===2,'Real underline did not increment capture count');
    const notes=await requestAnki('findNotes',{query:`deck:"${deck}"`});
    assert(notes.length===1,'Repeated annotation created a duplicate note');
    const info=(await requestAnki('notesInfo',{notes}))[0];
    assert(info.fields[config.backField].value.includes('收录次数：2'),'Anki note did not retain updated capture count');
    report.checks.push('Actual Zotero underline updated the same Anki note and capture count');
    const win=Zotero.getMainWindow();
    const popup=win.document.getElementById('menu_ToolsPopup');
    popup.dispatchEvent(new win.Event('popupshowing',{bubbles:true}));
    const labels=Array.from(popup.querySelectorAll('.zotero-custom-menu-item')).map(e=>e.getAttribute('label'));
    assert(labels.includes('词汇：状态与连接诊断') && labels.includes('词汇：设置通知弹窗时长'),'Actual Tools menu label is missing');
    report.checks.push('Actual Zotero Tools menu populated visible vocabulary menu labels');
    const windows=Services.wm.getEnumerator(null);
    let notification=false;
    while(windows.hasMoreElements()) {
      const w=windows.getNext();
      if (String(w.location?.href).includes('progressWindow.xhtml') && w.document.readyState==='complete') {
        const labels=Array.from(w.document.querySelectorAll('[value]')).map(e=>e.getAttribute('value')).join(' ');
        const text=labels+' '+w.document.documentElement.textContent;
        if(text.includes('Anki') || text.includes('词汇插件')) notification=true;
      }
    }
    assert(notification,'No loaded Zotero feedback window was found');
    report.checks.push('Actual Zotero notification window opened with vocabulary/Anki feedback');
    assert(getNotificationSeconds()===5,'Default notification duration is not five seconds');
    await Zotero.Promise.delay(5500);
    const remaining=Services.wm.getEnumerator(null);
    let vocabularyToastRemains=false;
    while(remaining.hasMoreElements()) {
      const w=remaining.getNext();
      if(String(w.location?.href).includes('progressWindow.xhtml') && w.document.readyState==='complete'
          && /词汇|Anki/.test(w.document.documentElement.textContent)) vocabularyToastRemains=true;
    }
    assert(!vocabularyToastRemains,'A vocabulary feedback window remained open beyond the default five seconds');
    report.checks.push('Actual Zotero feedback window closed automatically after the five-second default');
    disableAutoSync();
    await addAnnotation('highlight','localonly'+Date.now(),3);
    const after=await requestAnki('findNotes',{query:`deck:"${deck}"`});
    assert(after.length===1,'Auto sync off still created an Anki note');
    report.checks.push('Actual Zotero auto sync switch retained local-only capture');
    report.passed=true;
  } catch(error) { report.passed=false; report.error=String(error)+"\n"+String(error.stack || ""); }
  finally {
    try {
      if(deckCreated) {
        if(testNoteID) await requestAnki('deleteNotes',{notes:[testNoteID]});
        assert((await requestAnki('findCards',{query:`deck:"${deck}"`})).length===0,'Unexpected cards in temporary deck');
        await requestAnki('deleteDecks',{decks:[deck],cardsToo:true});
        report.cleanup.temporaryDeckRemoved=!(await requestAnki('deckNames')).includes(deck);
      }
    } catch(error) {report.passed=false;report.cleanup.error=String(error);}
    await Zotero.File.putContentsAsync(PathUtils.join(base,'ZOTERO_RUNTIME_VERIFICATION.json'),JSON.stringify(report,null,2));
    if(isolated) {
      shutdown();
      Zotero.ProgressWindowSet.closeAll();
      Services.startup.quit(Components.interfaces.nsIAppStartup.eAttemptQuit);
    }
  }
}
