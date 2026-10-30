"""Conservative, individually checked word-family memory aids."""

from functools import lru_cache
from pathlib import Path
import re

# Meanings describe these words in context, not every sense of a morpheme.
_ENTRIES = {
    'asynchrony': ('a + syn + chron + y', 'a-：不；syn-：一起；chron：时间；-y：状态。合起来指时间不同步。'),
    'asynchronous': ('a + syn + chron + ous', 'a-：不；syn-：一起；chron：时间；-ous：形容词后缀。指不同步的。'),
    'synchronous': ('syn + chron + ous', 'syn-：一起；chron：时间；-ous：形容词后缀。指同时或同步的。'),
    'synchronize': ('syn + chron + ize', 'syn-：一起；chron：时间；-ize：使成为。指使同步。'),
    'predict': ('pre + dict', 'pre-：预先；dict：说。指预先说出，即预测。'),
    'predictable': ('pre + dict + able', 'pre-：预先；dict：说；-able：能够……的。指可预测的。'),
    'transport': ('trans + port', 'trans-：跨越；port：运送。指运输。'),
    'transportation': ('trans + port + ation', 'trans-：跨越；port：运送；-ation：行为或过程。指运输。'),
    'export': ('ex + port', 'ex-：向外；port：运送。指出口。'),
    'import': ('im + port', 'im-：向内；port：运送。指进口。'),
    'portable': ('port + able', 'port：携带；-able：能够……的。指便携的。'),
    'construct': ('con + struct', 'con-：一起；struct：建造。指构建。'),
    'reconstruction': ('re + con + struct + ion', 're-：再次；con-：一起；struct：建造；-ion：行为或结果。指重建。'),
    'destruct': ('de + struct', 'de-：拆开；struct：建造。指破坏。'),
    'incredible': ('in + cred + ible', 'in-：不；cred：相信；-ible：能够……的。指难以置信的。'),
    'audible': ('aud + ible', 'aud：听；-ible：能够……的。指听得见的。'),
    'invisible': ('in + vis + ible', 'in-：不；vis：看；-ible：能够……的。指看不见的。'),
    'television': ('tele + vis + ion', 'tele-：远；vis：看；-ion：行为或结果。指电视。'),
    'visible': ('vis + ible', 'vis：看；-ible：能够……的。指看得见的。'),
    'telegraph': ('tele + graph', 'tele-：远；graph：写或记录。指电报或电报通信。'),
    'photograph': ('photo + graph', 'photo-：光；graph：写或记录。指照片或摄影。'),
    'autograph': ('auto + graph', 'auto-：自己；graph：写。指亲笔签名。'),
    'geographic': ('geo + graph + ic', 'geo-：地球；graph：写或描述；-ic：……的。指地理的。'),
    'microscope': ('micro + scope', 'micro-：小；scope：观察的仪器。指显微镜。'),
    'thermometer': ('thermo + meter', 'thermo-：热；meter：测量仪器。指温度计。'),
    'manuscript': ('manu + script', 'manu-：手；script：写。指手稿。'),
    'interrupt': ('inter + rupt', 'inter-：在……之间；rupt：打断或破裂。指打断。'),
    'introduction': ('intro + duct + ion', 'intro-：向内；duct：引导；-ion：行为或结果。指引入或介绍。'),
    'projection': ('pro + ject + ion', 'pro-：向前；ject：投掷；-ion：行为或结果。可指投射。'),
    'injection': ('in + ject + ion', 'in-：向内；ject：投掷或投入；-ion：行为或结果。指注射。'),
    'biologist': ('bio + log + ist', 'bio-：生命；log：研究；-ist：从事某领域的人。指生物学家。'),
    'biography': ('bio + graph + y', 'bio-：生命；graph：写；-y：名词后缀。指传记。'),
    'philosophy': ('philo + soph + y', 'philo-：爱；soph：智慧；-y：名词后缀。指哲学。'),
    'friendship': ('friend + ship', 'friend：朋友；-ship：关系或状态。指友谊。'),
    'thoughtless': ('thought + less', 'thought：考虑；-less：没有。指欠考虑的。'),
    'unhelpful': ('un + help + ful', 'un-：不；help：帮助；-ful：有……的。指没有帮助的。'),
    'misunderstand': ('mis + understand', 'mis-：错误地；understand：理解。指误解。'),
    'happiness': ('happy + ness', 'happy：快乐的，拼写变为 happi-；-ness：状态。指幸福或快乐。'),
    'unhappiness': ('un + happy + ness', 'un-：不；happy：快乐的，拼写变为 happi-；-ness：状态。指不快乐。'),
    'beautiful': ('beauty + ful', 'beauty：美，拼写变为 beauti-；-ful：有……的。指美丽的。'),
    'unbelievable': ('un + believe + able', 'un-：不；believe：相信，接后缀时去掉末尾 e；-able：能够……的。指难以置信的。'),
}

_CONFUSIONS = (
    (('affect', 'effect'), 'affect 常作动词：影响；effect 常作名词：影响、效果。注意两词也有其他词性。'),
    (('economic', 'economical'), 'economic：经济的、与经济有关的；economical：节约的、经济实惠的。'),
    (('historic', 'historical'), 'historic：有历史意义的；historical：历史的、与历史有关的。'),
    (('adapt', 'adopt', 'adept'), 'adapt：适应或改编；adopt：采用或收养；adept：熟练的。'),
    (('desert', 'dessert'), 'desert：沙漠，或作动词表示抛弃；dessert：甜点。'),
    (('principal', 'principle'), 'principal：主要的，或校长；principle：原则。'),
    (('complement', 'compliment'), 'complement：补充、使完整；compliment：称赞、恭维。'),
    (('stationary', 'stationery'), 'stationary：静止的；stationery：文具。'),
    (('personal', 'personnel'), 'personal：个人的；personnel：全体人员、人事部门。'),
    (('precede', 'proceed'), 'precede：在……之前；proceed：继续进行。'),
    (('lose', 'loose'), 'lose：失去；loose：松的。'),
    (('accept', 'except'), 'accept：接受；except：除……之外。'),
    (('assure', 'ensure', 'insure'), 'assure：向人保证；ensure：确保；insure：投保。具体用法依语境而定。'),
    (('emigrate', 'immigrate'), 'emigrate：从某地移出；immigrate：移入某地。'),
    (('borrow', 'lend'), 'borrow：借入；lend：借出。'),
)


def breakdown(word):
    item = _ENTRIES.get(str(word or '').casefold())
    return '%s\n%s' % item if item else ''


def confusion(word):
    key = str(word or '').casefold()
    return next((text for words, text in _CONFUSIONS if key in words), '')


@lru_cache(maxsize=1)
def _syllables():
    result = {}
    path = Path(__file__).parent / 'lexicon' / 'syllables.txt'
    for line in path.read_text(encoding='utf-8').splitlines():
        parts = line.strip().casefold().split(';')
        if len(parts) > 1 and all(re.fullmatch(r'[a-z]+', part) for part in parts):
            result.setdefault(''.join(parts), tuple(parts))
    return result


def spelling_chunks(word):
    word = str(word or '').strip()
    if len(word) < 8 or not re.fullmatch(r'[A-Za-z]+', word):
        return None
    parts = _syllables().get(word.casefold())
    if parts:
        pieces = []
        index = 0
        for part in parts:
            pieces.append(word[index:index + len(part)])
            index += len(part)
        return '音节分段', pieces
    return '拼写分块', [word[index:index + 4] for index in range(0, len(word), 4)]
