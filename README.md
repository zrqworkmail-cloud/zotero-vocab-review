# Zotero 划词同步到 Anki

A Zotero 10 plugin that records highlighted or underlined English words, syncs them to Anki through AnkiConnect, counts repeat captures, and gives frequently encountered words higher review priority.

## Anki fields

When the detected note type has these exact field names, the plugin fills them automatically:

- `正面`: the highlighted word.
- `解释`: a valid Zotero annotation translation, or a Youdao dictionary definition when the annotation has no usable translation.
- `例句`: bilingual examples returned by Youdao, when available.
- `权威例句`: dictionary examples plus a sentence containing the highlighted word from the current PDF page, labeled with the paper citation and page number.
- `音标`: pronunciation transcription returned by Youdao, when available.
- `标签`: `Zotero 高亮收录`.
- Anki note tags: `zotero_vocab_review` and `zotero_highlight`.

## Settings

Open Zotero's **Edit → Settings → Zotero 划词同步到 Anki** page to configure automatic Anki sync, review popups, notification duration, and AnkiConnect deck/note fields. If Anki is closed when a word is synced, the plugin tries its Start Menu shortcut or a standard install location, waits for AnkiConnect, and retries. This works across computers with standard installations; if it cannot locate Anki, it asks once for the program and remembers that computer's path. The “权威例句” field includes a document sentence formatted as `“Sentence.” —— Author (Year). Paper title (p. 12)`.

Other fields such as `词根`, `近义词`, and `英语发音` are left empty when no verified source data is available. Document examples are extracted locally from the PDF text already available to Zotero and are not sent to Youdao. Dictionary failures do not block word capture or Anki sync. If an exact matching note already exists without this plugin tag, the plugin adopts it, preserves its existing explanation and deck, and fills only empty optional fields; new literature examples are appended to `权威例句` without replacing existing content.

The dictionary integration was informed by [zotero-pick2anki](https://github.com/soyami/zotero-pick2anki), an MIT-licensed Zotero and Anki vocabulary plugin. See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Privacy

For dictionary enrichment, only the highlighted English word is sent to Youdao. Zotero document text, title, authors, and library data are not sent to the dictionary service. Anki sync uses the local AnkiConnect endpoint at `127.0.0.1:8765`.

## Windows global selection capture

The companion Anki add-on in [`anki-global-addon/`](anki-global-addon/) captures selected text from other Windows applications while Anki is running. It sends the selected word to Youdao for dictionary details and writes the card through AnkiConnect. It does not send surrounding document text.

Extract `zotero_global_capture.zip` into `%APPDATA%\Anki2\addons21\`, then restart Anki. In Anki, open **Tools → 全局划词入 Anki 设置…** to choose a capture mode or record a different shortcut. The default shortcut is **Ctrl+Shift+F10**. Preview mode is the default: the first press shows the definition; press again or click Add to confirm.

The same add-on can show a non-modal vocabulary quiz while Anki runs in the background. Choose the interval, screen position, question type, and optional Windows login startup in its settings. Grading uses AnkiConnect and only occurs after a rating is selected. Its optional desktop card styling is scoped to the configured deck and note type; it does not overwrite the shared Anki template. See [the companion guide](anki-global-addon/README.md).

The add-on shows a topmost progress and result notice so feedback remains visible over the source application. Automatic mouse-drag mode is optional and may not work in applications that block copying. See [`anki-global-addon/README.md`](anki-global-addon/README.md) for setup and behavior details.

## Build

```sh
python3 build.py --repository OWNER/REPOSITORY
python3 anki-global-addon/build.py
node --test tests/plugin.test.cjs
python3 -m unittest discover -s tests -p 'test_build.py'
```
