// Isolated-profile runtime check; never shipped in the release XPI.
var actualStartup = startup;
startup = async function (...args) {
  await actualStartup(...args);
  const root = PathUtils.parent(Services.dirsvc.get('ProfD', Components.interfaces.nsIFile).path);
  const checks = {version: PLUGIN_VERSION, running, listenerRegistered: !!notifierID,
    inflected: originalWord('leveraging'), ambiguous: originalWord('saw'), phrase: originalWord('running water')};
  await IOUtils.writeUTF8(PathUtils.join(root, 'lemma-runtime.json'), JSON.stringify(checks));
};
