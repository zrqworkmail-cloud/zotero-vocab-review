# Third party notices

## zotero-pick2anki

This plugin's dictionary enrichment was developed with reference to the MIT-licensed project [soyami/zotero-pick2anki](https://github.com/soyami/zotero-pick2anki), especially its documented Youdao dictionary data shape and Anki field mapping. The Zotero capture counter, duplicate handling, spaced review, and sync queue remain part of Zotero Vocabulary Review.

The referenced project lists its source code under the MIT License, copyright (c) 2026 soyami. Its MIT notice is reproduced here:

> MIT License
>
> Copyright (c) 2026 soyami
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Dictionary lookups send only the highlighted English word to Youdao's dictionary endpoint. Zotero document text and bibliographic metadata are not sent to that service.

## LemmInflect word-form data

`lemma-data.js` is a filtered lookup table generated from LemmInflect 0.2.3's `lemma_lu.csv.gz`, derived from the NIH SPECIALIST Lexicon. It contains only unambiguous single-word mappings. Source: https://github.com/bjascob/LemmInflect. Copyright (C) 2019 Brad Jascob. Distributed under the MIT License:

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## CET core vocabulary

The bundled community CET-6 Top 500 list is derived from [cet6-vocabulary](https://github.com/wangjiuyi543-ui/cet6-vocabulary), revision 6399f6cad57b66f86aa781827f0ac38a337ad214, MIT licensed. Unverified truncated forms were excluded; unambiguous forms were normalized. CET-4 overlap is derived from [ECDICT](https://github.com/skywind3000/ECDICT), revision bc015ed2e24a7abef49fc6dbbb7fe32c1dadaf8b, MIT licensed. Full license notices are bundled in `anki-global-addon/zotero_global_capture/lexicon/`. This is a community list, not an official frequency ranking.

## Word segmentation references

The individually curated `morphology.py` entries were informed by the hand-checked segmentation examples in [LexiRoot](https://github.com/tcyeee/lexiroot), revision 04d5f00e12ac8c78e111810229e5dec047a7672e, MIT licensed. LexiRoot's license and third-party notices are included in the add-on's `lexicon/` directory. The asynchrony family was checked against [Etymonline](https://www.etymonline.com/word/asynchronous); its prose was not copied.

## Syllable reference

`anki-global-addon/zotero_global_capture/lexicon/syllables.txt` comes from [25000-syllabified-words-list](https://github.com/gautesolheim/25000-syllabified-words-list), revision 607740452a3ab042de0248dcab1ff0fbe54fcae0, Unlicense. Its syllabification is based on Grady Ward's public-domain Moby Hyphenator, distributed by Project Gutenberg. The source's license is included as `SYLLABLES_LICENSE`. Syllable boundaries are displayed as spelling aids, not etymological analysis.

## CET-6 complete wordbook

`lexicon/cet6_full.json` is a compact conversion of the CET-6 wordbook from [WordTyper Vocabularies](https://github.com/grhliu/wordtyper-vocabularies), source blob `bb72953d15e0878af8963569162b38018ede35ba`. The source derives its entries from [ECDICT](https://github.com/skywind3000/ECDICT), MIT License, Copyright (c) 2025 Linwei; the full license is included in `lexicon/ECDICT_LICENSE`. The list is a community vocabulary collection, not a verified complete official examination syllabus.
