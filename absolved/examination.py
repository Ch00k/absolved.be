"""The examination of conscience: the questions the prepare page asks, and what the user says to the priest.

A question is the prompt; its statements are the answers the user can mark, and what the confession page shows. Each
statement is a whole sentence in the simple past, so that a count reads naturally after it and no sentence has to be
assembled from fragments, which could not be translated.

A user's answers are encrypted in their browser and refer to statements and questions by id, so an id must never be
reused or changed once published. Wording can change freely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.utils.functional import Promise


@dataclass(frozen=True)
class Statement:
    id: str
    text: Promise


@dataclass(frozen=True)
class Question:
    id: str
    text: Promise
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class Section:
    # A commandment's number; the precepts of the Church have none.
    number: int | None
    title: Promise
    questions: tuple[Question, ...]


def single(question_id: str, text: Promise, statement: Promise) -> Question:
    """A question answered by one statement, which shares the question's id."""
    return Question(question_id, text, (Statement(question_id, statement),))


SECTIONS = (
    Section(
        1,
        _("I am the Lord your God: you shall not have strange gods before me."),
        (
            single("c1-prayer", _("Have I neglected daily prayer?"), _("I neglected daily prayer.")),
            single(
                "c1-lukewarm",
                _("Have I been lukewarm or lazy in my life with God?"),
                _("I was lukewarm and lazy in my life with God."),
            ),
            Question(
                "c1-faith",
                _("Have I doubted or denied a truth of the faith, or been ashamed of it before others?"),
                (
                    Statement("c1-doubt", _("I doubted a truth of the faith.")),
                    Statement("c1-denial", _("I denied a truth of the faith.")),
                    Statement("c1-ashamed", _("I was ashamed of my faith before others.")),
                ),
            ),
            Question(
                "c1-occult",
                _("Have I put my trust in horoscopes, fortune-telling, superstition or the occult?"),
                (
                    Statement("c1-horoscopes", _("I put my trust in horoscopes.")),
                    Statement("c1-fortune-telling", _("I put my trust in fortune-telling.")),
                    Statement("c1-superstition", _("I put my trust in superstition.")),
                    Statement("c1-occultism", _("I took part in the occult.")),
                ),
            ),
            Question(
                "c1-idols",
                _("Have I put money, work, pleasure or anything else before God?"),
                (
                    Statement("c1-money", _("I put money before God.")),
                    Statement("c1-work", _("I put my work before God.")),
                    Statement("c1-pleasure", _("I put pleasure before God.")),
                    Statement("c1-other-gods", _("I put other things before God.")),
                ),
            ),
            Question(
                "c1-pride",
                _("Have I been proud, vain or boastful, or refused to be corrected?"),
                (
                    Statement("c1-proud", _("I thought myself better than others.")),
                    Statement("c1-vain", _("I was vain about my looks or achievements.")),
                    Statement("c1-boastful", _("I boasted.")),
                    Statement("c1-refused-correction", _("I refused to be corrected.")),
                ),
            ),
            Question(
                "c1-hope",
                _("Have I despaired of God's mercy, or presumed on it?"),
                (
                    Statement("c1-despair", _("I despaired of God's mercy.")),
                    Statement("c1-presumption", _("I presumed on God's mercy.")),
                ),
            ),
            single(
                "c1-communion",
                _("Have I received Holy Communion while conscious of a serious sin?"),
                _("I received Holy Communion while conscious of a serious sin."),
            ),
            single(
                "c1-concealed",
                _("Have I deliberately concealed a serious sin in confession?"),
                _("I deliberately concealed a serious sin in a past confession."),
            ),
        ),
    ),
    Section(
        2,
        _("You shall not take the name of the Lord your God in vain."),
        (
            Question(
                "c2-name",
                _("Have I used the name of God, Jesus, Mary or the saints carelessly or in anger?"),
                (
                    Statement("c2-name-carelessly", _("I used the name of God or of the saints carelessly.")),
                    Statement("c2-name-in-anger", _("I used the name of God or of the saints in anger.")),
                ),
            ),
            Question(
                "c2-cursing",
                _("Have I cursed, or wished evil on anyone?"),
                (
                    Statement("c2-cursed", _("I cursed someone.")),
                    Statement("c2-wished-evil", _("I wished evil on someone.")),
                ),
            ),
            Question(
                "c2-oath",
                _("Have I sworn an oath falsely or without need?"),
                (
                    Statement("c2-false-oath", _("I swore an oath falsely.")),
                    Statement("c2-needless-oath", _("I swore an oath without need.")),
                ),
            ),
            Question(
                "c2-vow",
                _("Have I broken a promise or vow made to God?"),
                (
                    Statement("c2-broken-promise", _("I broke a promise made to God.")),
                    Statement("c2-broken-vow", _("I broke a vow made to God.")),
                ),
            ),
            Question(
                "c2-mockery",
                _("Have I mocked religion, sacred things, or people consecrated to God?"),
                (
                    Statement("c2-mocked-religion", _("I mocked religion.")),
                    Statement("c2-mocked-sacred", _("I mocked sacred things.")),
                    Statement("c2-mocked-consecrated", _("I mocked people consecrated to God.")),
                ),
            ),
        ),
    ),
    Section(
        3,
        _("Remember to keep holy the Lord's Day."),
        (
            Question(
                "c3-mass",
                _("Have I missed Mass on a Sunday or holy day of obligation through my own fault?"),
                (
                    Statement("c3-missed-sunday", _("I missed Mass on a Sunday through my own fault.")),
                    Statement(
                        "c3-missed-holy-day", _("I missed Mass on a holy day of obligation through my own fault.")
                    ),
                ),
            ),
            Question(
                "c3-late",
                _("Have I come late to Mass or left early without good reason?"),
                (
                    Statement("c3-came-late", _("I came late to Mass without good reason.")),
                    Statement("c3-left-early", _("I left Mass early without good reason.")),
                ),
            ),
            Question(
                "c3-irreverence",
                _("Have I been deliberately inattentive or irreverent at Mass?"),
                (
                    Statement("c3-inattentive", _("I was deliberately inattentive at Mass.")),
                    Statement("c3-irreverent", _("I was irreverent at Mass.")),
                ),
            ),
            Question(
                "c3-rest",
                _("Have I done needless work or shopping on Sunday, or kept others from rest?"),
                (
                    Statement("c3-work", _("I did needless work on Sunday.")),
                    Statement("c3-shopping", _("I did needless shopping on Sunday.")),
                    Statement("c3-others-rest", _("I kept others from their Sunday rest.")),
                ),
            ),
        ),
    ),
    Section(
        4,
        _("Honour your father and your mother."),
        (
            Question(
                "c4-parents",
                _("Have I been disrespectful to my parents, or neglected them in their need?"),
                (
                    Statement("c4-disrespected-parents", _("I was disrespectful to my parents.")),
                    Statement("c4-neglected-parents", _("I neglected my parents in their need.")),
                ),
            ),
            Question(
                "c4-children",
                _("Have I neglected the care, upbringing in the faith or good example I owe my children?"),
                (
                    Statement("c4-children-care", _("I neglected the care of my children.")),
                    Statement("c4-children-faith", _("I neglected my children's upbringing in the faith.")),
                    Statement("c4-children-example", _("I failed to give my children a good example.")),
                ),
            ),
            Question(
                "c4-family",
                _("Have I failed in love or respect towards my spouse or family?"),
                (
                    Statement("c4-spouse-love", _("I failed in love towards my spouse.")),
                    Statement("c4-spouse-respect", _("I was disrespectful to my spouse.")),
                    Statement("c4-family-love", _("I failed in love towards my family.")),
                    Statement("c4-family-respect", _("I was disrespectful to my family.")),
                ),
            ),
            single(
                "c4-authority",
                _("Have I disobeyed lawful authority without just cause?"),
                _("I disobeyed lawful authority without just cause."),
            ),
        ),
    ),
    Section(
        5,
        _("You shall not kill."),
        (
            Question(
                "c5-harm",
                _("Have I harmed anyone physically, or wished them harm?"),
                (
                    Statement("c5-harmed", _("I harmed someone physically.")),
                    Statement("c5-wished-harm", _("I wished someone harm.")),
                ),
            ),
            Question(
                "c5-abortion",
                _("Have I had, encouraged or helped with an abortion?"),
                (
                    Statement("c5-had-abortion", _("I had an abortion.")),
                    Statement("c5-encouraged-abortion", _("I encouraged an abortion.")),
                    Statement("c5-helped-abortion", _("I helped with an abortion.")),
                ),
            ),
            Question(
                "c5-anger",
                _("Have I nursed anger, hatred or resentment, or refused to forgive?"),
                (
                    Statement("c5-nursed-anger", _("I nursed anger.")),
                    Statement("c5-hatred", _("I hated someone.")),
                    Statement("c5-resentment", _("I held on to resentment.")),
                    Statement("c5-unforgiveness", _("I refused to forgive someone.")),
                ),
            ),
            Question(
                "c5-temper",
                _("Have I lost my temper, or been impatient with others?"),
                (
                    Statement("c5-lost-temper", _("I lost my temper.")),
                    Statement("c5-impatient", _("I was impatient with others.")),
                ),
            ),
            Question(
                "c5-cruelty",
                _("Have I hurt anyone with cruel words, bullying or contempt?"),
                (
                    Statement("c5-cruel-words", _("I hurt someone with cruel words.")),
                    Statement("c5-bullying", _("I bullied someone.")),
                    Statement("c5-contempt", _("I treated someone with contempt.")),
                ),
            ),
            Question(
                "c5-health",
                _("Have I harmed my health through drunkenness, drugs, gluttony or recklessness?"),
                (
                    Statement("c5-drunkenness", _("I got drunk.")),
                    Statement("c5-drugs", _("I took drugs.")),
                    Statement("c5-gluttony", _("I was gluttonous.")),
                    Statement("c5-recklessness", _("I harmed my health through recklessness.")),
                ),
            ),
            Question(
                "c5-danger",
                _("Have I put others in danger, for example by driving recklessly or under the influence?"),
                (
                    Statement("c5-reckless-driving", _("I drove recklessly.")),
                    Statement("c5-driving-under-influence", _("I drove under the influence.")),
                    Statement("c5-endangered", _("I put others in danger.")),
                ),
            ),
            Question(
                "c5-scandal",
                _("Have I led someone into sin by my words or example?"),
                (
                    Statement("c5-scandal-words", _("I led someone into sin by my words.")),
                    Statement("c5-scandal-example", _("I led someone into sin by my example.")),
                ),
            ),
        ),
    ),
    Section(
        6,
        _("You shall not commit adultery."),
        (
            Question(
                "c6-adultery",
                _("Have I been unfaithful to my spouse, or had sexual relations outside marriage?"),
                (
                    Statement("c6-unfaithful", _("I was unfaithful to my spouse.")),
                    Statement("c6-outside-marriage", _("I had sexual relations outside marriage.")),
                ),
            ),
            Question(
                "c6-impurity",
                _("Have I committed impure acts, alone or with others?"),
                (
                    Statement("c6-impure-alone", _("I committed impure acts alone.")),
                    Statement("c6-impure-with-others", _("I committed impure acts with someone else.")),
                ),
            ),
            single(
                "c6-pornography",
                _("Have I deliberately looked at pornography?"),
                _("I deliberately looked at pornography."),
            ),
            single(
                "c6-openness",
                _("Have I acted against the openness of marriage to new life?"),
                _("I acted against the openness of marriage to new life."),
            ),
            Question(
                "c6-modesty",
                _("Have I dressed, spoken or acted immodestly, or joined in impure conversation?"),
                (
                    Statement("c6-immodest-dress", _("I dressed immodestly.")),
                    Statement("c6-immodest-speech", _("I spoke immodestly.")),
                    Statement("c6-immodest-acts", _("I acted immodestly.")),
                    Statement("c6-impure-conversation", _("I joined in impure conversation.")),
                ),
            ),
        ),
    ),
    Section(
        7,
        _("You shall not steal."),
        (
            Question(
                "c7-theft",
                _("Have I stolen, or kept something that is not mine?"),
                (
                    Statement("c7-stole", _("I stole.")),
                    Statement("c7-kept", _("I kept something that is not mine.")),
                ),
            ),
            Question(
                "c7-cheating",
                _("Have I cheated anyone, or failed to pay what I owe?"),
                (
                    Statement("c7-cheated", _("I cheated someone.")),
                    Statement("c7-unpaid", _("I failed to pay what I owe.")),
                ),
            ),
            single(
                "c7-damage",
                _("Have I damaged someone's property without making amends?"),
                _("I damaged someone's property without making amends."),
            ),
            Question(
                "c7-work",
                _("Have I been lazy or dishonest in my work, or withheld a just wage?"),
                (
                    Statement("c7-lazy", _("I was lazy in my work.")),
                    Statement("c7-dishonest-work", _("I was dishonest in my work.")),
                    Statement("c7-wage", _("I withheld a just wage.")),
                ),
            ),
            Question(
                "c7-time",
                _("Have I wasted time, or neglected my duties through laziness?"),
                (
                    Statement("c7-wasted-time", _("I wasted time.")),
                    Statement("c7-neglected-duties", _("I neglected my duties through laziness.")),
                ),
            ),
            Question(
                "c7-generosity",
                _("Have I wasted money, or been ungenerous to those in need?"),
                (
                    Statement("c7-wasted-money", _("I wasted money.")),
                    Statement("c7-ungenerous", _("I was ungenerous to those in need.")),
                ),
            ),
        ),
    ),
    Section(
        8,
        _("You shall not bear false witness against your neighbour."),
        (
            single("c8-lies", _("Have I lied?"), _("I lied.")),
            Question(
                "c8-gossip",
                _("Have I gossiped, or revealed others' faults without need?"),
                (
                    Statement("c8-gossiped", _("I gossiped.")),
                    Statement("c8-revealed-faults", _("I revealed others' faults without need.")),
                ),
            ),
            single(
                "c8-calumny",
                _("Have I damaged someone's reputation with things that are untrue?"),
                _("I damaged someone's reputation by saying things that are untrue."),
            ),
            single("c8-judgement", _("Have I judged others rashly?"), _("I judged others rashly.")),
            single(
                "c8-secret",
                _("Have I failed to keep a secret entrusted to me?"),
                _("I failed to keep a secret entrusted to me."),
            ),
        ),
    ),
    Section(
        9,
        _("You shall not covet your neighbour's wife."),
        (
            Question(
                "c9-thoughts",
                _("Have I deliberately dwelt on impure thoughts or desires?"),
                (
                    Statement("c9-impure-thoughts", _("I deliberately dwelt on impure thoughts.")),
                    Statement("c9-impure-desires", _("I deliberately dwelt on impure desires.")),
                ),
            ),
            single(
                "c9-spouse",
                _("Have I desired someone else's husband or wife?"),
                _("I desired someone else's husband or wife."),
            ),
            Question(
                "c9-guard",
                _("Have I let films, books or social media fill my imagination with impurity?"),
                (
                    Statement("c9-films", _("I let films fill my imagination with impurity.")),
                    Statement("c9-books", _("I let books fill my imagination with impurity.")),
                    Statement("c9-social-media", _("I let social media fill my imagination with impurity.")),
                ),
            ),
        ),
    ),
    Section(
        10,
        _("You shall not covet your neighbour's goods."),
        (
            Question(
                "c10-envy",
                _("Have I envied others their possessions, success or gifts?"),
                (
                    Statement("c10-envied-possessions", _("I envied others their possessions.")),
                    Statement("c10-envied-success", _("I envied others their success.")),
                    Statement("c10-envied-gifts", _("I envied others their gifts.")),
                ),
            ),
            single(
                "c10-greed", _("Have I set my heart on money and things?"), _("I set my heart on money and things.")
            ),
            single(
                "c10-gratitude",
                _("Have I been discontented instead of thankful for what God has given me?"),
                _("I was discontented instead of thankful for what God has given me."),
            ),
        ),
    ),
    Section(
        None,
        _("The precepts of the Church"),
        (
            single(
                "p-confession",
                _("Have I failed to confess serious sins at least once a year?"),
                _("I failed to confess serious sins at least once a year."),
            ),
            single(
                "p-easter",
                _("Have I failed to receive Holy Communion during the Easter season?"),
                _("I failed to receive Holy Communion during the Easter season."),
            ),
            Question(
                "p-fasting",
                _("Have I failed to keep the days of fasting and abstinence?"),
                (
                    Statement("p-fast-day", _("I failed to keep a day of fasting.")),
                    Statement("p-abstinence-day", _("I failed to keep a day of abstinence.")),
                ),
            ),
            single(
                "p-eucharistic-fast",
                _("Have I failed to keep the fast before Holy Communion?"),
                _("I failed to keep the fast before Holy Communion."),
            ),
            single(
                "p-support",
                _("Have I failed to help provide for the needs of the Church?"),
                _("I failed to help provide for the needs of the Church."),
            ),
        ),
    ),
)
