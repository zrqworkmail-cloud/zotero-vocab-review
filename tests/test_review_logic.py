import importlib.util
import datetime
import random
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / 'anki-global-addon' / 'zotero_global_capture' / 'review_logic.py'
spec = importlib.util.spec_from_file_location('review_logic', MODULE)
logic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic)


def card(cid, word, meaning, queue=0, reps=0):
    return {'cardId': cid, 'modelName': 'Words', 'deckName': 'Literature',
            'queue': queue, 'due': cid, 'reps': reps, 'mod': 1,
            'fields': {'Front': {'value': word}, 'Back': {'value': meaning}}}


class FakeAnki:
    def __init__(self):
        self.cards = {1: card(1, 'notion', '概念', 2, 1),
                      2: card(2, 'method', '方法'), 3: card(3, 'signal', '信号'),
                      4: card(4, 'context', '语境'), 5: card(5, 'model', '模型')}
        self.stats = {'name': 'Literature', 'new_count': 2, 'learn_count': 0, 'review_count': 1}
        self.profile = 'Profile A'
        self.answered = []

    def __call__(self, action, params):
        if action == 'deckNames':
            return ['Literature', 'CET']
        if action == 'findNotes':
            return []
        if action == 'getActiveProfile':
            return self.profile
        if action == 'getDeckStats':
            return {'1': dict(self.stats)}
        if action == 'findCards':
            q = params['query']
            if 'cid:' in q:
                cid = int(q.split('cid:')[1].split()[0])
                if cid not in self.cards:
                    return []
                if 'is:learn' in q:
                    # Anki's own way of saying "still in its first steps"; the fake answers it
                    # from the queue column, the way the real scheduler does.
                    return [cid] if self.cards[cid]['queue'] == 1 else []
                return [cid]
            if 'is:due' in q:
                return [1] if self.stats['review_count'] else []
            if 'is:new' in q:
                return [2, 3, 4, 5]
            return list(self.cards)
        if action == 'cardsInfo':
            return [self.cards[cid] for cid in params['cards'] if cid in self.cards]
        if action == 'answerCards':
            self.answered.extend(params['answers'])
            self.cards[params['answers'][0]['cardId']]['reps'] += 1
            return [True]
        raise AssertionError(action)


# The catalogue is normally the real word lists; tests bring their own so they are not
# pinned to production tag names. A deck book whose deck equals cfg['deck'] keeps the
# generated queries identical to the pre-book ones.
CFG = {'deck': 'Literature', 'model': 'Words', 'front_field': 'Front', 'back_field': 'Back',
       'study_book': 'literature',
       'study_books': [{'id': 'literature', 'name': '文献单词', 'deck': 'Literature'},
                       {'id': 'cet', 'name': 'CET 标签范围', 'tag': 'zvr_cet6_core'}]}


def deck_stats(name, new=999, learn=0, review=999):
    """One getDeckStats answer, keyed by deck id the way Anki returns it."""
    return {'1': {'name': name, 'new_count': new, 'learn_count': learn, 'review_count': review}}


class ReviewLogicTests(unittest.TestCase):
    def test_capture_lookup_cache_expires_and_remains_optional(self):
        calls = []
        def api(action, params):
            calls.append(action)
            if action == 'findNotes': return [1]
            if action == 'notesInfo': return [{'fields': {'Front': {'value':'apple'}, 'Back': {'value':'Zotero 收录次数: 2'}}}]
            raise AssertionError(action)
        cache = {}
        cfg = dict(CFG, _capture_lookup_cache=cache)
        self.assertEqual(logic._captured_words(api, cfg)['apple'], 2)
        self.assertEqual(logic._captured_words(api, cfg)['apple'], 2)
        self.assertEqual(calls, ['findNotes', 'notesInfo'])
        cache['captured_at'] -= 16
        logic._captured_words(api, cfg)
        self.assertEqual(len(calls), 4)

    def test_book_card_can_be_graded_from_any_deck_it_spans(self):
        api = FakeAnki()
        api.stats['new_count'] = 0   # this test is about cross-deck grading, not the queue order
        api.cards[1]['deckName'] = 'CET'
        def scoped_api(action, params):
            if action == 'getDeckStats':
                return {'1': dict(api.stats, name=params['decks'][0])}
            return api(action, params)
        # A tag book is not the capture deck; the card it pulls from CET is still its own.
        cfg = dict(CFG, study_book='cet')
        question = logic.prepare_question(scoped_api, cfg, 'typing', random.Random(1))
        self.assertEqual(question['review_deck'], 'CET')
        logic.submit_review(scoped_api, cfg, question, 3)
        self.assertEqual(api.answered[-1]['cardId'], 1)
    def test_book_skips_decks_without_matching_cards(self):
        api = FakeAnki()
        def scoped_api(action, params):
            if action == 'deckNames': return ['Literature', 'Empty']
            if action == 'findCards' and 'deck:"Empty"' in params['query']: return []
            if action == 'getDeckStats' and params['decks'] == ['Empty']:
                raise AssertionError('empty deck should not be queried')
            return api(action, params)
        self.assertIsNotNone(logic.prepare_question(scoped_api, dict(CFG, review_book='cet4_kyle'), 'typing', random.Random(1)))
    def test_remaining_windows_excludes_elapsed_time_and_keeps_future_windows(self):
        windows = [{'start': '09:00', 'end': '12:00'}, {'start': '14:00', 'end': '18:00'}, {'start': '19:00', 'end': '22:00'}]
        self.assertEqual(logic.remaining_window_minutes(datetime.datetime(2026, 10, 29, 16, 0), windows), 300)
        self.assertEqual(logic.remaining_window_minutes(datetime.datetime(2026, 10, 29, 18, 30), windows), 180)
        self.assertEqual(logic.remaining_window_minutes(datetime.datetime(2026, 10, 29, 23, 0), windows), 0)

    def test_daily_plan_recalculates_group_target_without_restarting_batch(self):
        self.assertEqual(logic.updated_session_target(2, {'batch': 6}), 6)
        self.assertEqual(logic.updated_session_target(4, {'batch': 2}), 4)
        self.assertEqual(logic.updated_session_target(1, {'batch': 0}), 1)
        date = datetime.date(2026, 10, 30)
        self.assertEqual(logic.study_plan(date, '', 0, 8, 0, 0, 8, 15)['batch'], 3)
        self.assertEqual(logic.study_plan(date, '', 0, 1, 0, 0, 8, 15)['batch'], 1)

    def test_fixed_group_mode_is_not_capped_by_the_deadline_plan(self):
        # 12 new words spread over 44 days only suggests 1 word per day; that estimate
        # must not end a session the user sized at 3 cards per group.
        plan = logic.study_plan(datetime.date(2026, 10, 30), '2026-12-12', 12, 0, 0, 1, 7, 15, 1)
        self.assertEqual((plan['goal'], plan['new_remaining']), (1, 0))
        self.assertTrue(logic.plan_limits_new({'review_plan_mode': 'daily'}))
        self.assertFalse(logic.plan_limits_new({'review_plan_mode': 'fixed'}))

    def test_end_of_session_reason_names_the_real_cause(self):
        # The catch-all used to guess two causes in one sentence and was wrong for the case
        # the learner actually hit: a finished book. Each branch must name its own number.
        book = '六级核心'
        finished = {'new_remaining': 0, 'due': 0, 'remaining_new_total': 0, 'available_new': 0}
        said = logic.end_of_session_reason(finished, False, book, elsewhere_due=38)
        self.assertIn('已学完', said)
        self.assertIn(book, said)
        self.assertIn('38 张到期卡不在所选词组内', said)
        self.assertIn('再勾一本词组', said)
        self.assertNotIn('可能是', said)
        self.assertNotIn('已选题型', said)
        self.assertNotIn('挂起', said, 'a zero is never printed')

        # 「已学完」also has to say what is parked: on 2026-11-06 the book reported nothing left
        # while 247 cards sat in 挂起, and the only advice on offer was "勾一本词组".
        parked = logic.end_of_session_reason(finished, False, book, suspended=247)
        self.assertIn('247 张被你挂起', parked)
        self.assertIn('已学完', parked)

        capped = {'new_remaining': 0, 'due': 0, 'remaining_new_total': 468, 'available_new': 0}
        said = logic.end_of_session_reason(capped, False, book)
        self.assertIn('468 张新词', said)
        self.assertIn('明天', said)

        planned = logic.end_of_session_reason({'new_remaining': 0, 'due': 3,
                                               'remaining_new_total': 0, 'available_new': 0},
                                              True, book)
        self.assertIn('新词计划已完成', planned)
        self.assertIn('到期复习', planned)
        planned_empty = logic.end_of_session_reason({'new_remaining': 0, 'due': 0,
                                                     'remaining_new_total': 0,
                                                     'available_new': 0}, True, book)
        self.assertIn('也没有到期复习词', planned_empty)

        types = logic.end_of_session_reason({'new_remaining': 5, 'due': 0,
                                             'remaining_new_total': 40, 'available_new': 5},
                                            False, book,
                                            mode_labels=('例句填空', '听音拼写'))
        self.assertIn('例句填空、听音拼写', types)
        self.assertIn('换题型', types)

        self.assertIn('无法判断', logic.end_of_session_reason(None, True))

    def test_the_parked_count_is_counted_inside_the_selection_only_by_reading(self):
        seen = []

        def api(action, params):
            seen.append((action, params['query']))
            return [7, 8, 9]
        self.assertEqual(logic.book_suspended(api, dict(CFG)), 3)
        self.assertEqual([action for action, _query in seen], ['findCards'],
                         'one read-only search, nothing else')
        self.assertTrue(seen[0][1].startswith('is:suspended'), seen[0][1])

        def broken(action, params):
            raise RuntimeError('Anki is busy')
        self.assertEqual(logic.book_suspended(broken, dict(CFG)), 0,
                         'a missing number must not eat the end-of-session sentence')

    def test_a_group_mixes_old_cards_in_by_a_fixed_share(self):
        # Replaces "new words come before due reviews" (2026-11-05). Measured live on
        # 2026-11-06: 365 new cards still allowed, 250 cards sitting in Anki's learning
        # steps, 27 mature reviews -- under the old rule the learning steps waited behind
        # roughly 37 groups, turning a 10-minute step into tomorrow. The learner chose a
        # fixed share per group, so slots 0-1 of ten are old cards and the rest stay new.
        api = FakeAnki()
        opening = logic.prepare_question(api, dict(CFG, _review_group=(0, 10)),
                                         'typing', random.Random(2))
        self.assertEqual(opening['kind'], 'due')
        middle = logic.prepare_question(api, dict(CFG, _review_group=(3, 10)),
                                        'typing', random.Random(2))
        self.assertEqual(middle['kind'], 'new')
        # Nothing in the collection changed: the old pile is one card deep here, so the
        # second promised slot must fall back to new rather than invent a due card.
        second = logic.prepare_question(api, dict(CFG, _review_group=(1, 10)),
                                        'typing', random.Random(2))
        self.assertEqual(second['kind'], 'new',
                         'a promised slot must not outrun the due pile that exists')
        ungrouped = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        self.assertEqual(ungrouped['kind'], 'new',
                         'without group info the selector must not force an old card')

    def test_due_only_still_reaches_the_due_queue(self):
        api = FakeAnki()
        due_only = logic.prepare_question(api, dict(CFG, _review_exclude_cards={2, 3, 4, 5}),
                                          'typing', random.Random(2), due_only=True)
        self.assertEqual(due_only['kind'], 'due',
                         'due_only must still reach the due queue, not skip the whole loop')

    def test_the_eyebrow_names_the_queue_the_card_is_actually_in(self):
        # 2026-11-06: of the 253 cards due in 《六级全表》, 252 were still in Anki's first
        # learning steps, and every one of them read 到期复习 — which is how the user ended up
        # asking whether they had really studied a word they had seen once, yesterday.
        self.assertEqual(logic.study_state_label('new', False), '新词')
        self.assertEqual(logic.study_state_label('due', True), '刚学过')
        self.assertEqual(logic.study_state_label('due', False), '到期复习')
        for label in ('新词', '刚学过', '到期复习'):
            self.assertIn(label, logic.STUDY_STATE_NOTES, 'every eyebrow label needs a tooltip line')

    def test_a_card_reports_whether_it_is_still_in_its_learning_steps(self):
        api = FakeAnki()
        self.assertFalse(logic.card_is_learning(api, 1), 'card 1 sits in the review queue')
        api.cards[1]['queue'] = 1
        self.assertTrue(logic.card_is_learning(api, 1))

        def busy(action, params):
            raise RuntimeError('Anki is busy')
        self.assertFalse(logic.card_is_learning(busy, 1), 'a label is not worth losing the card')

    def test_the_question_carries_the_learning_flag_the_eyebrow_reads(self):
        api = FakeAnki()
        due = logic.prepare_question(api, dict(CFG, _review_exclude_cards={2, 3, 4, 5}),
                                     'typing', random.Random(2), due_only=True)
        self.assertEqual(due['kind'], 'due')
        self.assertFalse(due['learning'], 'a graduated card must read 到期复习, not 刚学过')

    def test_exam_labels_are_based_on_actual_wordlist_membership(self):
        labels = logic.exam_word_labels('increases')
        self.assertIn('四级词表', labels)
        self.assertIn('六级词表', labels)
        self.assertIn('六级核心', labels)
        self.assertEqual(logic.exam_word_labels('zzzxxyyqq'), [])

    def test_every_chip_label_names_its_own_source(self):
        # The card prints one pill per list, so provenance is per pill rather than one
        # joined sentence: 四级/六级词表 come from ECDICT, 六级核心 from the community list.
        self.assertEqual(logic.exam_word_sources(['四级词表', '六级词表', '六级核心']),
                         ['ECDICT 四六级词表', 'CET-6 Top 500 社区整理'])
        self.assertEqual(logic.exam_word_sources(['六级核心']), ['CET-6 Top 500 社区整理'])
        self.assertEqual(logic.exam_word_sources([]), [])
        self.assertEqual(logic.exam_word_sources(['没有这个表']), [])
        for label in logic.exam_word_labels('increases'):
            self.assertIn(label, logic.BOOK_LABEL_SOURCES)

    def test_cet_core_prefers_core_within_due_cards(self):
        api = FakeAnki()
        api.stats['new_count'] = 0   # the core-preference rule is about which due card, not the queue order
        api.cards[1]['fields']['Front']['value'] = 'increase'
        self.assertTrue(logic.is_core_word('increases'))
        q = logic.prepare_question(api, dict(CFG, review_core_enabled=True), 'typing', random.Random(1))
        self.assertEqual(q['word'], 'increase')
        self.assertEqual(q['kind'], 'due')

    def test_speaking_is_only_enabled_when_selected(self):
        self.assertEqual(logic.selected_review_modes(dict(CFG, review_modes=['speaking'])), ['speaking'])
        q = logic.prepare_question(FakeAnki(), dict(CFG, review_modes=['speaking']), 'mixed', random.Random(1))
        self.assertEqual(q['mode'], 'speaking')
    def test_answer_clues_mask_all_forms_without_masking_other_words(self):
        text = 'v. "differ"的现在分词 differing；Differed, different and differ.'
        masked = logic.mask_answer_clues(text, 'differ', 'differing')
        self.assertNotIn('differ"', masked.lower())
        self.assertNotIn('differing', masked.lower())
        self.assertNotIn('differed', masked.lower())
        self.assertIn('different', masked)

    def test_review_modes_migrate_legacy_and_honor_explicit_selection(self):
        self.assertEqual(logic.selected_review_modes(dict(CFG, review_mode='listening')), ['listening'])
        self.assertEqual(logic.selected_review_modes(dict(CFG, review_mode='mixed')), ['choice', 'reverse', 'typing', 'cloze'])
        self.assertEqual(logic.selected_review_modes(dict(CFG, review_mode='choice', review_modes=['typing', 'listening', 'typing'])), ['typing', 'listening'])
        self.assertEqual(logic.selected_review_modes(dict(CFG, review_modes=[])), [])

    def test_selected_modes_do_not_fall_back_to_unselected_type(self):
        api = FakeAnki()
        cfg = dict(CFG, review_modes=['cloze', 'listening'])
        for seed in range(4):
            self.assertEqual(logic.prepare_question(api, cfg, 'mixed', random.Random(seed))['mode'], 'listening')
        self.assertIsNone(logic.prepare_question(api, dict(CFG, review_modes=['cloze']), 'mixed', random.Random(1)))
        for cid in (2, 3, 4, 5):
            api.cards[cid]['fields']['Back']['value'] = '完全相同的释义' * 4
        self.assertIsNone(logic.prepare_question(api, dict(CFG, review_modes=['choice']), 'mixed', random.Random(3)))

    def test_cloze_only_selects_a_card_with_a_usable_sentence(self):
        api = FakeAnki()
        api.cards[1]['fields']['例句'] = {'value': 'This notion is useful.'}
        question = logic.prepare_question(api, dict(CFG, review_modes=['cloze']), 'mixed', random.Random(1))
        self.assertEqual((question['card_id'], question['mode']), (1, 'cloze'))

    def test_distractors_exclude_synonyms_inflections_and_overlapping_glosses(self):
        target = card(1, 'run', 'v. 跑步')
        target['fields']['近义词'] = {'value': 'sprint'}
        candidates = [card(2, 'ran', 'v. 奔跑'), card(3, 'sprint', 'v. 疾行'),
                      card(4, 'jog', 'v. 慢跑步'), card(5, 'read', 'v. 阅读'),
                      card(6, 'write', 'v. 写字'), card(7, 'walk', 'v. 行走')]
        values = logic.distractor_candidates(target, candidates, CFG, 'reverse', random.Random(1))
        self.assertEqual(set(values), {'read', 'write', 'walk'})

    def test_distractor_pairs_do_not_repeat_near_identical_glosses(self):
        target = card(1, 'apple', 'n. 苹果')
        options = [card(2, 'orange', 'n. 橙子'), card(3, 'tangerine', 'n. 橙子水果'),
                   card(4, 'pear', 'n. 梨子'), card(5, 'banana', 'n. 香蕉')]
        selected = logic.distractor_candidates(target, options, CFG, 'reverse', random.Random(1))
        self.assertEqual(len(selected), 3)
        self.assertFalse({'orange', 'tangerine'} <= set(selected))

    def test_judgment_question_keeps_true_and_false_answers_consistent(self):
        api = FakeAnki()
        seen = set()
        for seed in range(20):
            q = logic.prepare_question(api, dict(CFG, review_modes=['judgment']), 'mixed', random.Random(seed))
            self.assertEqual(q['options'], ['正确', '错误'])
            self.assertEqual(q['judgment_statement'] == q['meaning'], q['judgment_correct'])
            seen.add(q['judgment_correct'])
        self.assertEqual(seen, {True, False})

    def test_legacy_dictionary_lists_are_unwrapped_without_removing_real_brackets(self):
        raw = "[&#x27;vt. 加强，巩固&#x27;]<br>[&#x27;adj. 起加强作用的&#x27;]"
        result = logic.clean_detail(raw, '解释')
        self.assertEqual(result, 'vt. 加强，巩固\nadj. 起加强作用的')
        rendered = logic.meaning_table(result)
        self.assertNotIn('[', rendered)
        self.assertIn('加强，巩固', rendered)
        self.assertEqual(logic.clean_detail('[计算机] 保留含义', '解释'), '[计算机] 保留含义')
        self.assertEqual(logic.clean_detail('[broken', '解释'), '[broken')
        self.assertEqual(logic.normalize_meaning_lists('["alpha", "beta"]'), 'alpha\nbeta')

    def test_listening_mode_prepares_without_changing_answer_or_scheduler(self):
        question = logic.prepare_question(FakeAnki(), CFG, 'listening', random.Random(1))
        self.assertEqual(question['mode'], 'listening')
        self.assertEqual(question['answer_form'], question['word'])
        self.assertEqual(question['options'], [])

    def test_daily_plan_overrides_fixed_batch_including_manual_after_goal(self):
        cfg = dict(CFG, review_plan_mode='daily', review_batch_size=9)
        self.assertEqual(logic.session_batch_size(cfg, {'batch': 2}, manual=True), 2)
        self.assertEqual(logic.session_batch_size(cfg, {'batch': 0}, manual=True), 1)
        self.assertEqual(logic.session_batch_size(cfg, {'batch': 0}, manual=False), 0)
        self.assertEqual(logic.session_batch_size(dict(cfg, review_plan_mode='fixed'), {'batch': 2}), 9)

    def test_daily_goal_limits_recommended_new_and_reports_capacity(self):
        today = datetime.date(2026, 10, 29)
        plan = logic.study_plan(today, '2026-11-02', 100, 4, 10, 3, 1, 30)
        self.assertEqual(plan['new_remaining'], 3)
        no_deadline = logic.study_plan(today, '', 100, 4, 10, 3, 1, 30)
        self.assertEqual(no_deadline['new_remaining'], 3)
        reached = logic.study_plan(today, '2026-11-02', 100, 4, 10, 10, 1, 30)
        self.assertEqual(reached['new_remaining'], 0)
        overloaded = logic.study_plan(today, '', 100, 0, 100, 0, 1, 30)
        # A group is no longer capped at ten: two study windows split a hundred-card day in
        # two, and the shortfall is measured against what Anki will actually serve today.
        self.assertEqual(overloaded['batch'], 50)
        self.assertEqual(overloaded['capacity_shortfall'], 0)
        capped = logic.study_plan(today, '', 100, 0, 100, 0, 1, 30, available=(40, 4))
        self.assertEqual(capped['capacity_shortfall'], 56)

    def test_a_group_is_as_big_as_the_user_says(self):
        # The 10-card ceiling used to turn a 104-card day into eleven separate clicks and
        # capped the fixed setting in the dialog; nothing raises or limits it now.
        self.assertEqual(logic.session_batch_size(dict(CFG, review_plan_mode='fixed', review_batch_size=200)), 200)
        self.assertEqual(logic.session_batch_size(dict(CFG, review_plan_mode='fixed', review_batch_size=3),
                                                   {'batch': 7}), 3)
        self.assertEqual(logic.session_batch_size(dict(CFG, review_plan_mode='daily'), {'batch': 104}), 104)
        self.assertEqual(logic.updated_session_target(3, {'batch': 104}), 104)

    def test_beautify_applies_to_selected_decks_and_children(self):
        cfg = dict(CFG, study_book='cet', _book_decks=['Literature', 'CET'], _book_decks_key='cet')
        self.assertTrue(logic.should_style_card('CET::Level', 'Words', 'reviewAnswer', cfg))
        self.assertTrue(logic.should_style_card('Literature', 'Words', 'reviewAnswer', cfg))
        self.assertFalse(logic.should_style_card('Unselected', 'Words', 'reviewAnswer', cfg))
        self.assertFalse(logic.should_style_card('CET', 'Another model', 'reviewAnswer', cfg))
    def test_plan_queries_the_book_decks_and_reports_remaining_new(self):
        queries = []
        def api(action, params):
            if action == 'deckNames':
                return ['CET']
            if action == 'getDeckStats':
                return deck_stats(params['decks'][0])
            queries.append(params['query'])
            if 'is:new' in params['query'] and '-is:new' not in params['query']:
                return list(range(100))
            # No stage marker means resolve_book_decks is probing whether this deck
            # holds the book at all; an empty answer would drop the deck entirely.
            return [1] if not any(marker in params['query'] for marker in ('is:due', 'rated:', 'introduced:')) else []
        plan = logic.collection_plan(api, dict(CFG, study_book='cet',
                                               review_deadline='2026-11-02'), datetime.datetime(2026, 10, 30))
        self.assertEqual(plan['remaining_new_total'], 100)
        self.assertEqual(plan['new'], 25)
        self.assertTrue(all('deck:"CET"' in query for query in queries), queries)

    def test_a_card_outside_the_book_cannot_be_graded_from_it(self):
        api = FakeAnki()
        api.stats['new_count'] = 0   # subject: narrowing the book must refuse, not queue order
        api.cards[1]['deckName'] = 'Other'
        original = api.__call__
        def lookup(action, params):
            if action == 'deckNames':
                return ['Literature', 'CET', 'Other']
            if action == 'getDeckStats':
                deck = params['decks'][0]
                return {'1': dict(api.stats, name=deck, review_count=1 if deck == 'Other' else 0)}
            return original(action, params)
        cfg = dict(CFG, study_book='cet', _book_decks=['Literature', 'CET', 'Other'], _book_decks_key='cet')
        question = logic.prepare_question(lookup, cfg, 'typing', random.Random(2))
        self.assertEqual(question['review_deck'], 'Other')
        logic.submit_review(lookup, cfg, question, 3)
        self.assertEqual(api.answered[0]['cardId'], 1)
        # Narrowing the book so it no longer spans the deck the question came from must
        # refuse, rather than grade a card the user is no longer studying.
        with self.assertRaises(ValueError):
            logic.submit_review(lookup, dict(cfg, _book_decks=['Literature']), question, 3)
    def test_root_sections_keep_labels_inline_and_align_related_words(self):
        result = logic.root_detail_html('词根：\npriest\nadj.\npriestly 祭司的\npriestlike 僧侣般的\nn.\npriesthood 神职')
        self.assertIn('<td width="48" valign="top">词根：</td><td>priest</td>', result)
        self.assertIn('<td width="48" valign="top">adj.</td><td>priestly 祭司的</td>', result)
        self.assertIn('<td width="48" valign="top"></td><td>priestlike 僧侣般的</td>', result)
        self.assertIn('<td width="48" valign="top">n.</td><td>priesthood 神职</td>', result)
        self.assertIn('&lt;word&gt;', logic.root_detail_html('词根： <word>'))

    def test_lemma_requires_unambiguous_dictionary_entry(self):
        self.assertEqual(logic.unambiguous_lemma('leveraging'), 'leverage')
        self.assertEqual(logic.unambiguous_lemma('ran'), 'run')
        self.assertEqual(logic.unambiguous_lemma('saw'), 'saw')
        self.assertEqual(logic.unambiguous_lemma('consistency'), 'consistency')
        self.assertEqual(logic.unambiguous_lemma('made up'), 'made up')

    def test_example_hint_hides_each_inflection_and_rejects_unrelated_sentences(self):
        self.assertEqual(logic.masked_example('She runs and ran.', 'run'), 'She ____ and ___.')
        self.assertIsNone(logic.masked_example('The result is good.', 'run'))

    def test_spelling_question_uses_unambiguous_lemma_without_changing_card(self):
        fake = FakeAnki()
        fake.stats['new_count'] = 0   # the lemma check must run on the card it actually picked
        fake.cards[1]['fields']['Front']['value'] = 'leveraging'
        question = logic.prepare_question(fake, CFG, 'typing', random.Random(1))
        self.assertEqual((question['word'], question['source_form'], question['answer_form']), ('leverage', 'leveraging', 'leverage'))
        self.assertEqual(fake.cards[1]['fields']['Front']['value'], 'leveraging')

    def test_review_windows_validate_and_schedule_across_midnight(self):
        windows = [{'enabled': True, 'start': '09:00', 'end': '12:00'},
                   {'enabled': True, 'start': '14:00', 'end': '18:00'},
                   {'enabled': True, 'start': '19:00', 'end': '22:00'}]
        self.assertTrue(logic.validate_windows(windows))
        self.assertEqual(logic.window_minutes(windows), 600)
        self.assertEqual(logic.window_wait(datetime.datetime(2026, 10, 28, 10), windows), 0)
        self.assertEqual(logic.window_wait(datetime.datetime(2026, 10, 28, 12, 30), windows), 5400)
        self.assertEqual(logic.window_wait(datetime.datetime(2026, 10, 28, 23), windows), 36000)
        self.assertFalse(logic.validate_windows(windows + [{'start': '11:00', 'end': '13:00'}]))
        self.assertFalse(logic.validate_windows([{'start': '22:00', 'end': '01:00'}]))
        self.assertFalse(logic.validate_windows([{'enabled': False, 'start': '09:00', 'end': '12:00'}]))

    def test_deadline_plan_counts_inclusive_days_and_uses_daily_progress(self):
        plan = logic.study_plan(datetime.date(2026, 10, 28), '2026-11-01', 21, 8, 0, 3, 2, 30)
        self.assertEqual((plan['days'], plan['new'], plan['due'], plan['goal'], plan['batch']), (5, 5, 8, 16, 4))
        later = logic.study_plan(datetime.date(2026, 10, 28), '2026-11-01', 16, 0, 0, 8, 2, 30, 5)
        self.assertEqual((later['new'], later['goal'], later['batch']), (5, 8, 0))
        override = logic.study_plan(datetime.date(2026, 10, 28), '2026-11-01', 21, 8, 7, 7, 2, 30)
        self.assertEqual((override['goal'], override['batch']), (7, 0))

    def test_collection_plan_deduplicates_overlapping_decks(self):
        def api(action, params):
            if action == 'deckNames':
                return ['Literature', 'CET']
            if action == 'getDeckStats':
                return deck_stats(params['decks'][0])
            self.assertEqual(action, 'findCards')
            query = params['query']
            if 'is:new' in query and '-is:new' not in query:
                return [1, 2, 3]
            if 'is:due' in query:
                return [4, 5]
            return [4]
        plan = logic.collection_plan(api, dict(CFG, review_extra_deck='CET', review_daily_goal=10))
        self.assertEqual((plan['due'], plan['done'], plan['goal']), (2, 1, 10))

    def test_collection_plan_separates_new_and_review_progress(self):
        def api(action, params):
            if action == 'deckNames':
                # These two stubs used to pass only because an earlier test had written
                # `_book_decks` into the shared module CFG. Anki always answers deckNames,
                # so the stub has to as well.
                return ['Literature', 'CET']
            if action == 'getDeckStats':
                return deck_stats(params['decks'][0])
            query = params['query']
            if 'introduced:1' in query: return [1, 2]
            if 'rated:1' in query: return [1, 2, 3, 4]
            if 'is:due' in query: return [2, 4, 5]
            if 'is:new' in query: return [6, 7, 8, 9, 10]
            return []
        plan = logic.collection_plan(api, dict(CFG, review_daily_goal=10))
        self.assertEqual(plan['new_done'], 2)
        self.assertEqual(plan['review_done'], 2)
        self.assertEqual(plan['review_remaining'], 2)
        self.assertEqual(plan['review_goal'], 4)
        self.assertEqual(plan['new_goal'], plan['new_done'] + plan['new_remaining'])

    def test_a_caller_without_deck_stats_still_gets_a_plan(self):
        # The in-process dashboard speaks findCards only; the plan must degrade to "no claim
        # about today's ceiling" instead of raising KeyError and blanking the dashboard.
        def api(action, params):
            if action == 'deckNames':
                return ['Literature']
            if 'is:new' in params['query']:
                return [1, 2, 3]
            return []
        plan = logic.collection_plan(api, dict(CFG, review_daily_goal=50))
        self.assertNotIn('available_new', plan)
        self.assertEqual(plan['capacity_shortfall'], 0)
        self.assertEqual(plan['new_remaining'], 3)

    def test_hints_follow_last_correct_letter_and_skip_existing_hints(self):
        self.assertEqual(logic.next_hint_index('apple', ['a', 'p', '', '', ''], set()), 2)
        self.assertEqual(logic.next_hint_index('apple', ['a', 'x', 'p', '', ''], {3}), 4)
        self.assertEqual(logic.next_hint_index('cat', ['c', 'x', 't'], set()), 1)
        self.assertIsNone(logic.next_hint_index('cat', ['c', 'a', 't'], set()))

    def test_a_cloze_always_asks_the_base_form(self):
        # A sentence that uses an inflected form must still ask for the headword: the blank
        # is as long as the word to type, not as long as the word the sentence happened to use.
        self.assertEqual(logic.cloze_sentence('They follow a set patterns.', 'pattern'),
                         'They follow a set _______.')
        self.assertEqual(logic.cloze_sentence('She ran yesterday.', 'run'), 'She ___ yesterday.')
        self.assertEqual(logic.cloze_form('They follow a set patterns.', 'pattern'), 'patterns')

    def test_a_cloze_question_carries_the_base_form_and_shows_the_sentence_form(self):
        api = FakeAnki()
        api.cards[1]['fields']['例句'] = {'value': 'These notions are useful.'}
        question = logic.prepare_question(api, CFG, 'cloze', random.Random(2))
        self.assertEqual(question['mode'], 'cloze')
        self.assertEqual(question['answer_form'], 'notion', 'the user types the headword, not the plural')
        self.assertEqual(question['cloze_shown'], 'notions', 'the answer face still says what the sentence used')
        self.assertEqual(question['cloze'], 'These ______ are useful.')

    def test_cloze_uses_attested_inflection_and_preserves_word_boundaries(self):
        self.assertEqual(logic.cloze_form('She ran yesterday.', 'run'), 'ran')
        self.assertEqual(logic.cloze_sentence('She ran yesterday.', 'run'), 'She ___ yesterday.')
        self.assertEqual(logic.cloze_form('They studied.', 'study'), 'studied')
        self.assertEqual(logic.cloze_form('He went home.', 'go'), 'went')
        self.assertIsNone(logic.cloze_form('Be careful.', 'care'))

    def test_part_of_speech_formatting_preserves_content(self):
        self.assertEqual(logic.format_meaning('n.运动员；人vt.训练vi.活动'), 'n.  运动员；人\nvt.  训练\nvi.  活动')
        self.assertEqual(logic.format_meaning('adv.经常 adj.普通 n.人'), 'adv.  经常\nadj.  普通\nn.  人')
        self.assertEqual(logic.format_meaning('n. 已有空格'), 'n. 已有空格')
        self.assertEqual(logic.format_meaning('version 1.0 is stable'), 'version 1.0 is stable')

    def test_meaning_columns_escape_content_and_align_labels(self):
        result = logic.meaning_table('n.猫vi.逃跑 & 躲避')
        self.assertEqual(result.count('<tr>'), 2)
        self.assertIn('width="30"', result)
        self.assertIn('width="24"', logic.meaning_table('n.猫', 24))
        self.assertIn('逃跑 &amp; 躲避', result)
        self.assertNotIn('n.  猫', result)

    def test_the_meaning_columns_line_up_on_every_row(self):
        # Part of speech right-aligned against a fixed gap cell, meaning left-aligned: the
        # distance between the two columns is the same for `n.` and for `n & v.`.
        rendered = logic.meaning_table('n.猫vi.逃跑 & 躲避', 46, 20, 8)
        self.assertIn('<td width="46" align="right" valign="top">n.</td>', rendered)
        self.assertIn('<td width="46" align="right" valign="top">vi.</td>', rendered)
        self.assertIn('<td width="8"></td>', rendered)
        self.assertIn('colspan="3"', logic.meaning_table('没有词性的整行', 46, 0, 8))

    def test_examples_are_grouped_with_translation_and_source(self):
        text = 'First example.\n第一条。\nSecond example.\n第二条。\n\n“Study sentence.” —— Paper'
        self.assertEqual(logic.example_groups(text), ['First example.\n第一条。', 'Second example.\n第二条。', '“Study sentence.” —— Paper'])

    def test_example_words_are_clickable_escaped_and_marked(self):
        value = logic.link_example_html('A <b>known &amp; target</b> word.', 'target', {'known'}, 'underline')
        self.assertIn('href="zvr:known"', value)
        self.assertIn('<u>known</u>', value)
        self.assertIn('<b>target</b>', value)
        self.assertIn('&amp;', value)
        self.assertIn('<b>', value)
        self.assertNotIn('href="zvr:b"', value)
        self.assertIn('href="zvr:word"', value)

    def test_chinese_em_dash_is_not_a_citation(self):
        text = 'Consistency matters.\n正直的关键在于一致性——不仅要遵守准则。'
        self.assertIsNone(logic.literature_example_html(text))
        self.assertEqual(logic.example_groups(text), [text])

    def test_recall_scoring_uses_native_grades_for_severity(self):
        # A clean recall is the one case the user wants to be able to fire with Enter:
        # the suggestion has to reach Easy, otherwise a word they already know is
        # recorded as Good and keeps coming back.
        self.assertEqual(logic.suggested_ease(True, 0, 0), 4)
        self.assertEqual(logic.suggested_ease(True, 0, 1), 3)
        self.assertEqual(logic.suggested_ease(True, 0, 2), 2)
        self.assertEqual(logic.suggested_ease(True, 0, 3), 2)
        self.assertEqual(logic.suggested_ease(True, 1, 0), 2)
        self.assertEqual(logic.suggested_ease(True, 0, 1, 1), 2)
        self.assertEqual(logic.suggested_ease(True, 1, 3), 1)
        self.assertEqual(logic.suggested_ease(True, 2, 0), 1)
        self.assertEqual(logic.suggested_ease(True, 0, 4), 1)
        self.assertEqual(logic.suggested_ease(True, 0, 0, 2), 1)
        self.assertEqual(logic.suggested_ease(False, 0, 0), 1)

    def test_the_same_slip_is_worth_more_on_a_harder_question(self):
        # Spelling the word is the hardest class, so three wrong letters plus a hint there
        # is treated as a miss, while the same record on a four-option question is only
        # Hard. The raw ladder is unchanged when no mode is given.
        self.assertEqual(logic.suggested_ease(True, 1, 3, 0, 'typing'), 1)
        self.assertEqual(logic.suggested_ease(True, 1, 3, 0, 'choice'), 2)
        self.assertEqual(logic.suggested_ease(True, 0, 2, 0, 'choice'), 2)
        self.assertEqual(logic.suggested_ease(True, 0, 0, 0, 'typing'), 4)
        self.assertEqual(logic.suggested_ease(True, 0, 0), logic.suggested_ease(True, 0, 0, 0, None))

    def test_what_counts_as_already_known_differs_by_question_type(self):
        # Spelling the base form is its own proof, so no clock is needed. Picking the right
        # meaning only counts when it was instant. Judgment is left out: two options make a
        # fast right answer a coin flip.
        self.assertTrue(logic.suggests_mastering('typing', True, seconds=99))
        self.assertTrue(logic.suggests_mastering('choice', True, seconds=1.2))
        self.assertTrue(logic.suggests_mastering('listening', True, seconds=logic.MASTERED_WINDOW_SECONDS))
        self.assertFalse(logic.suggests_mastering('choice', True, seconds=3.1))
        self.assertFalse(logic.suggests_mastering('cloze', True, seconds=None))
        self.assertFalse(logic.suggests_mastering('judgment', True, seconds=0.1))
        self.assertFalse(logic.suggests_mastering('typing', False, seconds=0.5))
        self.assertFalse(logic.suggests_mastering('typing', True, hints=1))
        self.assertFalse(logic.suggests_mastering('typing', True, incorrect_letters=1))
        self.assertFalse(logic.suggests_mastering('typing', True, failed_checks=1))
        self.assertFalse(logic.suggests_mastering('unknown-mode', True, seconds=0.1))

    def test_mastering_suspends_the_card_and_tags_the_note(self):
        # "I already know this" has to leave the study range without writing a rating.
        # Suspend is the reversible lever every card query already honours; the tag is
        # what makes the decision findable and undoable in bulk later.
        calls = []
        def api(action, params):
            calls.append((action, params))
            return [{'cardId': 99, 'note': 7}] if action == 'cardsInfo' else True
        self.assertEqual(logic.mark_mastered(api, CFG, {'card_id': 99, 'word': 'yield'}), 7)
        self.assertIn(('suspend', {'cards': [99]}), calls)
        self.assertIn(('addTags', {'notes': [7], 'tags': 'zvr_mastered'}), calls)
        self.assertEqual([c for c in calls if c[0] == 'answerCards'], [], 'mastering must not write a rating')

    def test_mastering_without_a_note_still_suspends_the_card(self):
        calls = []
        def api(action, params):
            calls.append((action, params))
            return [] if action == 'cardsInfo' else True
        self.assertIsNone(logic.mark_mastered(api, CFG, {'card_id': 99}))
        self.assertEqual([c[0] for c in calls], ['cardsInfo', 'suspend'])

    def test_compound_part_of_speech_stays_on_one_line(self):
        # 'vt&amp;vi. 出产' arrived as one marker; splitting it after the '&' left a
        # dangling 'vt&' line in the card.
        lines = logic.format_meaning('v.屈服，产出 n.产量 vt&vi.出产').splitlines()
        self.assertEqual(len(lines), 3, lines)
        self.assertTrue(lines[2].startswith('vt&vi.'), lines[2])
        self.assertEqual(len(logic.format_meaning('n./v.生产').splitlines()), 1)
        self.assertEqual(logic.meaning_markers('v.屈服 vt&vi.出产'), ['v.', 'vt&vi.'])
        rendered = logic.meaning_table('vt&vi.出产')
        self.assertIn('valign="top">vt&amp;vi.</td>', rendered, rendered)

    def test_meaning_block_is_indented_under_its_heading(self):
        rendered = logic.meaning_table('n.猫', 24, 20)
        self.assertIn('<td width="20"></td>', rendered, rendered)
        self.assertIn('width="24" align="right" valign="top">n.</td>', rendered, rendered)
        self.assertNotIn('<td width="20"></td>', logic.meaning_table('n.猫', 24))

    def test_native_hard_rating_is_sent_to_anki(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        logic.submit_review(api, CFG, question, 2)
        self.assertEqual(api.answered[0]['ease'], 2)

    def test_recent_word_is_deferred_only_when_other_cards_available(self):
        api = FakeAnki()
        cfg = dict(CFG, _review_recent_words={'notion'})
        question = logic.prepare_question(api, cfg, 'typing', random.Random(1))
        self.assertNotEqual(question['word'], 'notion')
        self.assertEqual(question['kind'], 'new')
        self.assertIsNone(logic.prepare_question(api, cfg, 'typing', random.Random(1), due_only=True))
        api.stats['new_count'] = 0
        fallback = logic.prepare_question(api, cfg, 'typing', random.Random(1))
        self.assertEqual(fallback['word'], 'notion')

    def test_current_batch_excludes_same_lemma_on_distinct_cards(self):
        api = FakeAnki()
        api.stats['review_count'] = 0
        api.cards[2]['fields']['Front']['value'] = 'leveraging'
        api.cards[3]['fields']['Front']['value'] = 'leverage'
        cfg = dict(CFG, _review_exclude_words={'leverage'})
        for seed in range(8):
            q = logic.prepare_question(api, cfg, 'typing', random.Random(seed))
            self.assertNotEqual(q['word'].casefold(), 'leverage')

    def test_mixed_authority_field_keeps_literature_and_source_together(self):
        text = 'A general example. — 普通翻译。\n文献例句：Another research finding.\n出处：Jang 等 (2025). Paper Title (p. 2)'
        groups = logic.example_groups(text)
        self.assertEqual(groups, ['A general example.\n普通翻译。', '文献例句：Another research finding.\n出处：Jang 等 (2025). Paper Title (p. 2)'])
        rendered = logic.literature_example_html(groups[1])
        self.assertIn('text-indent:28px;', rendered)
        self.assertIn('Another research finding.', rendered)
        self.assertNotIn('文献例句：', rendered)
        self.assertIn('出处：Jang 等 (2025). <i>Paper Title</i> (p. 2)', rendered)
        self.assertEqual(logic.spoken_examples(groups[1], '', 'first'), ['Another research finding.'])

    def test_literature_example_formats_quote_and_bold_title(self):
        rendered = logic.literature_example_html('“A finding.” —— Jang 等 (2025). Study & Evidence (p. 2)')
        self.assertIn('text-indent:28px;', rendered)
        self.assertIn('“A finding.”', rendered)
        self.assertIn('<br', rendered)
        self.assertIn('—— Jang 等 (2025).', rendered)
        self.assertIn('<i>Study &amp; Evidence</i>', rendered)
        self.assertIn('(p. 2)', rendered)
        self.assertIsNone(logic.literature_example_html('Ordinary sentence.'))

    def test_inline_bilingual_examples_split_and_remain_paired(self):
        text = 'First sentence. — 第一句。\nSecond sentence. — 第二句。'
        self.assertEqual(logic.example_groups(text), ['First sentence.\n第一句。', 'Second sentence.\n第二句。'])
        self.assertEqual(logic.spoken_examples('First sentence. — 第一句。', '', 'example'), ['First sentence.'])

    def test_detail_fields_preserve_bilingual_lines_and_remove_duplicate_headings(self):
        self.assertEqual(logic.clean_detail('例句:<br>We learn.<br>我们学习。', '例句'), 'We learn.\n我们学习。')
        self.assertEqual(logic.clean_detail('解释:<br>n.运动员<br><br>Zotero 收录次数：2', '解释'), 'n.运动员')
        self.assertEqual(logic.clean_detail('权威例句:<br>One.<br><br>Two.', '权威例句'), 'One.\n\nTwo.')

    def test_default_first_example_uses_first_available_only(self):
        self.assertEqual(logic.spoken_examples('First.\nSecond.', 'Third.', 'first'), ['First.'])
        self.assertEqual(logic.spoken_examples('', 'Third.\nFourth.', 'first'), ['Third.'])

    def test_example_speech_does_not_read_chinese_or_citation(self):
        self.assertEqual(logic.spoken_examples('We learn.\n我们学习。', '“More examples.” —— Author (2024)', 'all'), ['We learn.', 'More examples.'])
        self.assertEqual(logic.spoken_examples('We learn.\n我们学习。', 'Quote.', 'authority'), ['Quote.'])

    def test_progressive_spelling_hints_do_not_reveal_last_letter(self):
        self.assertEqual(logic.spelling_hint('ice-cream', 0), '___-_____')
        self.assertEqual(logic.spelling_hint('ice-cream', 2), 'ic_-_____')
        self.assertEqual(logic.spelling_hint('cat', 99), 'ca_')

    def test_cloze_replaces_only_whole_word_and_preserves_sentence(self):
        self.assertEqual(logic.cloze_sentence('A cat saw a catalog.', 'cat'), 'A ___ saw a catalog.')
        self.assertIsNone(logic.cloze_sentence('A catalog.', 'cat'))
        self.assertIsNone(logic.cloze_sentence('No cat here.', 'cat dog'))

    def test_letter_feedback_does_not_reveal_correct_answer(self):
        self.assertEqual(logic.letter_feedback('cat', 'cut'), [('c', True), ('u', False), ('t', True)])
        self.assertEqual(logic.letter_feedback('cat', 'ca'), [('c', True), ('a', True)])

    def test_old_local_difficulty_no_longer_changes_selection_weight(self):
        c = card(9, 'word', '释义')
        self.assertEqual(logic._weight(c, dict(CFG, _difficulty_weights={'9': 8})), logic._weight(c, CFG))

    def test_manual_capture_has_extra_weight_even_on_first_capture(self):
        plain = card(7, 'word', '单词')
        captured = card(8, 'word', '单词<br>全局划词收录次数：1')
        self.assertGreater(logic._weight(captured, CFG), logic._weight(plain, CFG))
        captured['fields']['Back']['value'] = '单词<br>全局划词收录次数：3'
        self.assertEqual(logic._weight(captured, CFG), 2)

    def test_separate_captured_note_increases_matching_word_weight(self):
        unrelated = card(7, 'method', '方法')
        self.assertGreater(logic._weight(unrelated, CFG, {'method': 2}), logic._weight(unrelated, CFG, {}))
        self.assertEqual(logic._weight(unrelated, CFG, {'other': 2}), 1)

    def test_additional_deck_new_before_primary_due(self):
        # Reversed on 2026-11-05 at the learner's request: today's new words first, due
        # reviews after them, so a day of 六级词汇 is not interrupted by old cards.
        api = FakeAnki()
        original = api.__call__
        api.cards[1]['deckName'] = 'CET'
        def lookup(action, params):
            if action == 'getDeckStats':
                deck = params['decks'][0]
                return {'1': dict(api.stats, name=deck, review_count=1 if deck == 'CET' else 0)}
            return original(action, params)
        cfg = dict(CFG, study_book='cet')
        question = logic.prepare_question(lookup, cfg, 'typing', random.Random(2))
        self.assertEqual(question['kind'], 'new')
        # With the new queue spent, the due card in the additional deck is next.
        spent = logic.prepare_question(lookup, dict(cfg, _review_exclude_cards={2, 3, 4, 5}),
                                       'typing', random.Random(2))
        self.assertEqual(spent['kind'], 'due')
        self.assertEqual(spent['review_deck'], 'CET')
    def test_reverse_choices_and_cloze_use_correct_content(self):
        api = FakeAnki()
        api.cards[1]['fields']['例句'] = {'value': 'This notion is useful.'}
        reverse = logic.prepare_question(api, CFG, 'reverse', random.Random(2))
        self.assertEqual(reverse['mode'], 'reverse')
        self.assertIn('notion', reverse['options'])
        cloze = logic.prepare_question(api, CFG, 'cloze', random.Random(2))
        self.assertEqual(cloze['mode'], 'cloze')
        self.assertEqual(cloze['cloze'], 'This ______ is useful.')

    def test_session_excludes_already_answered_card(self):
        api = FakeAnki()
        question = logic.prepare_question(api, dict(CFG, _review_exclude_cards={1}), 'typing', random.Random(2))
        self.assertNotEqual(question['card_id'], 1)

    def test_new_card_takes_priority_and_choices_are_distinct(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'choice', random.Random(3))
        self.assertEqual(question['kind'], 'new')
        self.assertEqual(len(question['options']), 4)
        self.assertEqual(len(set(question['options'])), 4)
        self.assertIn('概念', question['options'])

    def test_similar_option_prefixes_fall_back_to_typing(self):
        api = FakeAnki()
        common = '相同释义前缀' * 6
        for cid in (2, 3, 4, 5):
            api.cards[cid]['fields']['Back']['value'] = common + str(cid)
        question = logic.prepare_question(api, CFG, 'choice', random.Random(3))
        self.assertEqual(question['mode'], 'typing')
        self.assertEqual(question['options'], [])

    def test_due_only_does_not_introduce_new_cards(self):
        api = FakeAnki()
        api.stats.update(review_count=0, new_count=2)
        self.assertIsNone(logic.prepare_question(api, CFG, 'typing', random.Random(2), due_only=True))
        api.stats['review_count'] = 1
        self.assertEqual(logic.prepare_question(api, CFG, 'typing', random.Random(2), due_only=True)['kind'], 'due')

    def test_a_rating_in_flight_already_consumes_its_deck_slot(self):
        # The card being written in the background has taken one of the deck's new
        # slots for today. Offering another would show a card Anki then refuses to
        # grade, so the in-flight rating has to be subtracted from the quota.
        api = FakeAnki()
        api.stats.update(new_count=1, learn_count=0, review_count=0)
        self.assertEqual(logic.prepare_question(api, CFG, 'typing', random.Random(1))['kind'], 'new')
        self.assertIsNone(logic.prepare_question(api, dict(CFG, _review_inflight_new=1), 'typing', random.Random(1)))
        api.stats.update(new_count=0, review_count=1)
        self.assertEqual(logic.prepare_question(api, CFG, 'typing', random.Random(1))['kind'], 'due')
        self.assertIsNone(logic.prepare_question(api, dict(CFG, _review_inflight_due=1), 'typing', random.Random(1)))

    def test_smart_check_preserves_regular_deadline(self):
        self.assertEqual(logic.next_check_delay(100, 1300, True), 300)
        self.assertEqual(logic.next_check_delay(1200, 1300, True), 100)
        self.assertEqual(logic.next_check_delay(1300, 1300, True), 0)
        self.assertEqual(logic.next_check_delay(100, 1300, False), 1200)

    def test_new_cards_respect_remaining_daily_allowance(self):
        api = FakeAnki()
        api.stats.update(review_count=0, new_count=0)
        self.assertIsNone(logic.prepare_question(api, CFG, 'typing', random.Random(2)))
        api.stats['new_count'] = 1
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        self.assertEqual(question['kind'], 'new')
        self.assertIn(question['card_id'], [2, 3, 4, 5])

    def test_current_anki_reviewer_card_is_not_selected_for_popup(self):
        api = FakeAnki()
        cfg = dict(CFG, _review_exclude_card=1)
        question = logic.prepare_question(api, cfg, 'typing', random.Random(2))
        self.assertEqual(question['kind'], 'new')
        self.assertNotEqual(question['card_id'], 1)

    def test_a_changed_card_is_never_graded_from_a_stale_popup(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        api.cards[question['card_id']]['reps'] += 1
        with self.assertRaisesRegex(ValueError, '变化'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [])

    def test_profile_change_does_not_grade_a_different_collection(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        api.profile = 'Profile B'
        with self.assertRaisesRegex(ValueError, '账户'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [])

    def test_skip_does_not_grade_and_valid_grade_is_sent_once(self):
        api = FakeAnki()
        question = logic.prepare_question(api, CFG, 'typing', random.Random(2))
        self.assertEqual(api.answered, [])
        logic.submit_review(api, CFG, question, 3)
        self.assertEqual(api.answered, [{'cardId': question['card_id'], 'ease': 3}])
        with self.assertRaisesRegex(ValueError, '变化'):
            logic.submit_review(api, CFG, question, 3)
        self.assertEqual(len(api.answered), 1)

    def test_clean_meaning_removes_capture_metadata(self):
        self.assertEqual(logic.clean_text('<b>概念</b><br><br>Zotero 收录次数：3'), '概念')
        self.assertTrue(logic.answer_matches('  Research  ', 'research'))

    def test_card_style_is_limited_to_the_configured_deck_and_note_type(self):
        self.assertTrue(logic.should_style_card('Literature', 'Words', 'reviewQuestion', CFG))
        self.assertTrue(logic.should_style_card('Literature::Child', 'Words', 'reviewAnswer', CFG))
        self.assertFalse(logic.should_style_card('Other', 'Words', 'reviewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Other', 'reviewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Words', 'previewQuestion', CFG))
        self.assertFalse(logic.should_style_card('Literature', 'Words', 'reviewQuestion', dict(CFG, review_beautify=False)))


class QuitRequest(unittest.TestCase):
    """The restart tool's only way to ask for a real exit while a tray add-on is installed."""

    def test_a_request_is_answered_once_and_consumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = logic.quit_request_path(tmp)
            self.assertFalse(logic.take_quit_request(path), 'nothing waiting is not a request')
            path.write_text('2026-11-04T10:36:52', encoding='utf-8')
            self.assertTrue(logic.take_quit_request(path))
            self.assertFalse(path.exists(), 'a stale note would quit the next session too')
            self.assertFalse(logic.take_quit_request(path))

    def test_an_unreachable_directory_is_answered_with_nothing(self):
        self.assertFalse(logic.take_quit_request(logic.quit_request_path(
            str(logic.Path(tempfile.gettempdir()) / 'zvr-no-such-directory-91827'))))


class TrayClosePolicy(unittest.TestCase):
    def test_a_tray_add_on_means_the_close_button_is_not_a_shutdown(self):
        # 'Minimize to Tray 2' keeps Anki alive, so X is "go to background" and the study
        # timers must keep running; only our own 退出 Anki (forcing) is a real exit.
        self.assertTrue(logic.background_instead_of_quit(True, False))
        self.assertFalse(logic.background_instead_of_quit(True, True))
        self.assertFalse(logic.background_instead_of_quit(False, False))
        self.assertFalse(logic.background_instead_of_quit(False, True))


class SpellingHintGrading(unittest.TestCase):
    """看中文写单词：提示的**种类**和**位置**决定建议评分（2026-11-04 用户口径）。

    旧规则是"按过任何一次提示就一律 Hard"，用户否掉了：一次发音提示几乎等于没提示，
    而空格提示出来的字母要按位置加权——首字母值钱，末尾字母不值钱。
    """

    def test_early_letters_are_worth_more_than_late_ones(self):
        # 权重 1/(i+1)，所以占比是全词权重和的归一化结果。
        self.assertEqual(logic.hint_share(set(), 14), 0.0)
        self.assertAlmostEqual(logic.hint_share({0}, 14), 0.30754, places=4)
        self.assertAlmostEqual(logic.hint_share({13}, 14), 0.02195, places=4)
        self.assertAlmostEqual(logic.hint_share({0, 1, 2, 3, 4}, 5), 1.0, places=6)
        self.assertEqual(logic.hint_share({99}, 5), 0.0)          # 越界索引不计
        self.assertEqual(logic.hint_share({0}, 0), 0.0)           # 没有字母就没有比例

    def test_one_audio_hint_is_still_easy(self):
        self.assertEqual(logic.suggested_ease(True, 1, 0, 0, 'typing', audio_hints=1), 4)
        self.assertEqual(logic.suggested_ease(True, 2, 0, 0, 'typing', audio_hints=2), 3)
        self.assertEqual(logic.suggested_ease(True, 3, 0, 0, 'typing', audio_hints=3), 2)
        self.assertEqual(logic.suggested_ease(True, 5, 0, 0, 'typing', audio_hints=5), 2)

    def test_letter_hints_are_banded_by_position_weighted_share(self):
        # characteristic 首字母 31% → Good；drive 首字母 44% → Hard；advantage 末字母 4% → Easy
        self.assertEqual(logic.suggested_ease(True, 1, 0, 0, 'typing', revealed={0}, letters=14), 3)
        self.assertEqual(logic.suggested_ease(True, 1, 0, 0, 'typing', revealed={0}, letters=5), 2)
        self.assertEqual(logic.suggested_ease(True, 1, 0, 0, 'typing', revealed={8}, letters=9), 4)
        self.assertEqual(logic.suggested_ease(True, 4, 0, 0, 'typing', revealed={0, 1, 2}, letters=5), 1)

    def test_the_strictest_component_wins(self):
        # 一次发音（Easy）+ 首字母（Good）+ 一个错字母（Good）→ Good
        self.assertEqual(logic.suggested_ease(True, 2, 1, 0, 'typing',
                                              audio_hints=1, revealed={0}, letters=14), 3)
        # 两个错字母把地板压到 Hard
        self.assertEqual(logic.suggested_ease(True, 2, 2, 0, 'typing',
                                              audio_hints=1, revealed={0}, letters=14), 2)
        # 检查失败一次就是 Hard，发音提示再轻也救不回来
        self.assertEqual(logic.suggested_ease(True, 1, 0, 1, 'typing', audio_hints=1), 2)
        # 答错永远是 Again
        self.assertEqual(logic.suggested_ease(False, 1, 0, 0, 'typing', audio_hints=1), 1)

    def test_meaning_and_example_hints_keep_the_hard_floor(self):
        self.assertEqual(logic.suggested_ease(True, 1, 0, 0, 'typing', other_hints=1), 2)
        self.assertEqual(logic.suggested_ease(True, 2, 0, 0, 'typing',
                                              audio_hints=1, other_hints=1), 2)

    def test_a_caller_without_components_still_gets_the_blanket_rule(self):
        # 其它题型（选择/填空/听力）暂时只报"提示次数"，语义必须保持原样。
        self.assertEqual(logic.suggested_ease(True, 1, 0), 2)
        self.assertEqual(logic.suggested_ease(True, 0, 0, 0, 'typing'), 4)
        self.assertEqual(logic.suggested_ease(True, 1, 3, 0, 'typing'), 1)

    def test_any_hint_at_all_stops_being_mastered(self):
        self.assertTrue(logic.suggests_mastering('typing', True, hints=0))
        self.assertFalse(logic.suggests_mastering('typing', True, hints=1))


if __name__ == '__main__':
    unittest.main()
