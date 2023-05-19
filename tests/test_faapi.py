from datetime import datetime
from json import load
from pathlib import Path
from re import sub
from typing import Optional

from pytest import fixture
from pytest import raises
from requests.cookies import RequestsCookieJar

import faapi
from localrepo_api import Comment
from localrepo_api import FAAPI
from localrepo_api import JournalPartial
from localrepo_api import SubmissionPartial
from localrepo_api import UserPartial
from localrepo_api.exceptions import DisallowedPath
from localrepo_api.exceptions import Unauthorized
from localrepo_api.furaffinity.furaffinity_parser import username_url
from localrepo_api.interface.faapi_abc import FAAPI_ABC
from localrepo_api.parse import clean_html



__root__: Path = Path(__file__).resolve().parent


@fixture
def cookies(data: dict) -> RequestsCookieJar:
    return data["cookies"]



def remove_user_icons(html: str) -> str:
    return sub(r"a\.furaffinity\.net/\d{8}/[^. ]+.gif", "", html)


def test_robots(test_data, cookies: RequestsCookieJar):
    api: FAAPI_ABC = test_data.backend(cookies)
    assert getattr(api.robots, "default_entry") is not None
    assert api.crawl_delay >= 1
    for endpoint in test_data.data["endpoints"]:
        assert api.check_path(endpoint)
    for endpoint in test_data.data["disallowed_endpoints"]:
        with raises(DisallowedPath):
            assert not api.check_path(endpoint, raise_for_disallowed=True)


def test_login(test_data, cookies: RequestsCookieJar):
    api: FAAPI_ABC = test_data.backend(cookies)
    assert api.login_status
    assert api.connection_status

    api.load_cookies([{"name": "a", "value": "1"}])
    with raises(Unauthorized):
        api.me()


# noinspection DuplicatedCode
def test_frontpage(test_data, cookies: RequestsCookieJar):
    api: FAAPI_ABC = test_data.backend(cookies)

    ss = api.frontpage()

    assert len({s.id for s in ss}) == len(ss)

    for submission in ss:
        assert submission.id > 0
        assert submission.type != ""
        assert submission.rating != ""
        assert submission.thumbnail_url != ""


def test_user(test_data, cookies: RequestsCookieJar, user_test_data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    user = api.user(user_test_data["name"])
    user_dict = dict(user)

    assert user.name == user_dict["name"] == user_test_data["name"]
    assert user.status == user_dict["status"] == user_test_data["status"]
    assert user.title == user_dict["title"] == user_test_data["title"]
    assert user.join_date == user_dict["join_date"] == user_test_data["join_date"]
    assert user.stats.views == user_dict["stats"]["views"]
    assert user_dict["stats"]["views"] >= user_test_data["stats"]["views"]
    assert user.stats.submissions == user_dict["stats"]["submissions"]
    assert user_dict["stats"]["submissions"] >= user_test_data["stats"]["submissions"]
    assert user.stats.favorites == user_dict["stats"]["favorites"]
    assert user_dict["stats"]["favorites"] >= user_test_data["stats"]["favorites"]
    assert user.stats.comments_earned == user_dict["stats"]["comments_earned"]
    assert user_dict["stats"]["comments_earned"] >= user_test_data["stats"]["comments_earned"]
    assert user.stats.comments_made == user_dict["stats"]["comments_made"]
    assert user_dict["stats"]["comments_made"] >= user_test_data["stats"]["comments_made"]
    assert user.stats.journals == user_dict["stats"]["journals"]
    assert user_dict["stats"]["journals"] >= user_test_data["stats"]["journals"]
    assert user.info == user_dict["info"] == user_test_data["info"]
    assert user.contacts == user_dict["contacts"] == user_test_data["contacts"]
    assert user.avatar_url == user_dict["avatar_url"] != ""
    assert user.banner_url == user_dict["banner_url"] != ""
    assert remove_user_icons(clean_html(user.profile)) == \
           remove_user_icons(clean_html(user_dict["profile"])) == \
           remove_user_icons(clean_html(user_test_data["profile"]))
    # assert user.profile_bbcode == user_test_data["profile_bbcode"]


# noinspection DuplicatedCode
def test_submission(test_data, cookies: RequestsCookieJar, submission_test_data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    submission, files = api.submission(submission_test_data["id"], get_file=True)
    submission_dict = dict(submission)

    assert submission.id == submission_dict["id"] == submission_test_data["id"]
    assert submission.title == submission_dict["title"] == submission_test_data["title"]
    assert submission.author.name == submission_dict["author"]["name"] == submission_test_data["author"]["name"]
    assert submission.author.avatar_url == submission_dict["author"]["avatar_url"] != ""
    assert submission.date == submission_dict["date"] == submission_test_data["date"]
    assert submission.tags == submission_dict["tags"] == submission_test_data["tags"]
    assert submission.category == submission_dict["category"] == submission_test_data["category"]
    assert submission.species == submission_dict["species"] == submission_test_data["species"]
    assert submission.gender == submission_dict["gender"] == submission_test_data["gender"]
    assert submission.rating == submission_dict["rating"] == submission_test_data["rating"]
    assert submission.stats.views == submission_dict["stats"]["views"]
    assert submission.stats.views >= submission_test_data["stats"]["views"]
    assert submission.stats.comments == submission_dict["stats"]["comments"]
    assert submission.stats.comments >= submission_test_data["stats"]["comments"]
    assert submission.stats.favorites == submission_dict["stats"]["favorites"]
    assert submission.stats.favorites >= submission_test_data["stats"]["favorites"]
    assert submission.type == submission_dict["type"] == submission_test_data["type"]
    assert submission.mentions == submission_dict["mentions"] == submission_test_data["mentions"]
    assert submission.folder == submission_dict["folder"] == submission_test_data["folder"]
    assert submission.file_url == submission_dict["file_url"] != ""
    assert submission.thumbnail_url == submission_dict["thumbnail_url"] != ""
    assert submission.prev == submission_dict["prev"] == submission_test_data["prev"]
    assert submission.next == submission_dict["next"] == submission_test_data["next"]
    assert submission.favorite == submission_dict["favorite"] == submission_test_data["favorite"]
    assert bool(submission.favorite_toggle_link) == bool(submission_dict["favorite_toggle_link"]) == \
           bool(submission_test_data["favorite_toggle_link"])
    assert remove_user_icons(clean_html(submission.description)) == \
           remove_user_icons(clean_html(submission_dict["description"])) == \
           remove_user_icons(clean_html(submission_test_data["description"]))
    assert remove_user_icons(clean_html(submission.footer)) == \
           remove_user_icons(clean_html(submission_dict["footer"])) == \
           remove_user_icons(clean_html(submission_test_data["footer"]))
    #assert submission.description_bbcode == submission_test_data["description_bbcode"]
    #assert submission.footer_bbcode == submission_test_data["footer_bbcode"]

    assert len(files) > 0
    for file in files:
        assert(len(file)) > 0

    assert len(faapi.comment.flatten_comments(submission.comments)) == submission.stats.comments

    comments: dict[int, Comment] = {c.id: c for c in faapi.comment.flatten_comments(submission.comments)}

    for comment in comments.values():
        assert comment.reply_to is None or isinstance(comment.reply_to, Comment)

        if comment.reply_to:
            assert comment.reply_to.id in comments
            assert comment in comments[comment.reply_to.id].replies

        if comment.replies:
            for reply in comment.replies:
                assert reply.reply_to == comment


# noinspection DuplicatedCode
def test_journal(test_data, cookies: RequestsCookieJar, journal_test_data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    journal = api.journal(journal_test_data["id"])
    journal_dict = dict(journal)

    assert journal.id == journal_dict["id"] == journal_test_data["id"]
    assert journal.title == journal_dict["title"] == journal_test_data["title"]
    assert journal.author.name == journal_dict["author"]["name"] == journal_test_data["author"]["name"]
    assert journal.author.join_date == journal_dict["author"]["join_date"] == \
           journal_test_data["author"]["join_date"]
    assert journal.author.avatar_url == journal_dict["author"]["avatar_url"] != ""
    assert journal.date == journal_dict["date"] == journal_test_data["date"]
    assert journal.stats.comments == journal_dict["stats"]["comments"] >= journal_test_data["stats"]["comments"]
    assert journal.mentions == journal_dict["mentions"] == journal_test_data["mentions"]
    #assert remove_user_icons(clean_html(journal.content)) == \
    #       remove_user_icons(clean_html(journal_dict["content"])) == \
    #       remove_user_icons(clean_html(journal_test_data["content"]))
    assert remove_user_icons(clean_html(journal.header)) == \
           remove_user_icons(clean_html(journal_dict["header"])) == \
           remove_user_icons(clean_html(journal_test_data["header"]))
    assert remove_user_icons(clean_html(journal.footer)) == \
           remove_user_icons(clean_html(journal_dict["footer"])) == \
           remove_user_icons(clean_html(journal_test_data["footer"]))
    #assert journal.content_bbcode == journal_test_data["content_bbcode"]
    #assert journal.header_bbcode == journal_test_data["header_bbcode"]
    #assert journal.footer_bbcode == journal_test_data["footer_bbcode"]

    # assert len(faapi.comment.flatten_comments(journal.comments)) == journal.stats.comments

    comments: dict[int, Comment] = {c.id: c for c in faapi.comment.flatten_comments(journal.comments)}

    for comment in comments.values():
        assert comment.reply_to is None or isinstance(comment.reply_to, Comment)

        if comment.reply_to:
            assert comment.reply_to.id in comments
            assert comment in comments[comment.reply_to.id].replies

        if comment.replies:
            for reply in comment.replies:
                assert reply.reply_to == comment


# noinspection DuplicatedCode
def test_gallery(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    ss: list[SubmissionPartial] = []

    pending_pages: list[Any] = [None]

    while len(pending_pages) > 0:
        p = pending_pages.pop()
        ss_, p_, subpages_ = api.gallery(data["gallery"]["user"], p)
        assert isinstance(ss, list)
        assert all(isinstance(s, SubmissionPartial) for s in ss_)
        assert p_ is None or isinstance(p_, int)
        assert p_ is None or p_ > p
        assert len(ss_) or p_ is None

        ss.extend(ss_)
        pending_pages.extend(subpages_)
        if p_ is not None:
            pending_pages.append(p_)

    assert len(ss) >= data["gallery"]["length"]
    assert len({s.id for s in ss}) == len(ss)

    for submission in ss:
        assert submission.id > 0
        assert submission.type != ""
        assert submission.rating != ""
        assert submission.thumbnail_url != ""
        assert submission.author.name_url == username_url(data["gallery"]["user"])


# noinspection DuplicatedCode
def test_scraps(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    ss: list[SubmissionPartial] = []

    pending_pages: list[Any] = [None]

    while len(pending_pages) > 0:
        p = pending_pages.pop()
        ss_, p_, subpages_ = api.scraps(data["scraps"]["user"], p)
        assert isinstance(ss, list)
        assert all(isinstance(s, SubmissionPartial) for s in ss_)
        assert p_ is None or isinstance(p_, int)
        assert p_ is None or p_ > p
        assert len(ss) or p is None
        assert len(ss_) or p_ is None

        ss.extend(ss_)
        pending_pages.extend(subpages_)
        if p_ is not None:
            pending_pages.append(p_)

    assert len(ss) >= data["scraps"]["length"]
    assert len({s.id for s in ss}) == len(ss)

    for submission in ss:
        assert submission.id > 0
        assert submission.type != ""
        assert submission.rating != ""
        assert submission.thumbnail_url != ""
        assert submission.author.name_url == username_url(data["scraps"]["user"])


# noinspection DuplicatedCode
def test_favorites(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    ss: list[SubmissionPartial] = []
    p: Optional[str] = None

    pending_pages: list[Any] = [None]

    while len(ss) < data["favorites"]["max_length"]:
        p = pending_pages.pop()
        ss_, p_, subpages_ = api.favorites(data["favorites"]["user"], p)
        assert isinstance(ss, list)
        assert all(isinstance(s, SubmissionPartial) for s in ss_)
        assert len(ss_) or p_ is None

        ss.extend(ss_)
        pending_pages.extend(subpages_)
        if p_ is not None:
            pending_pages.append(p_)

        if len(pending_pages) == 0:
            break

    assert len(ss) >= data["favorites"]["length"]
    assert len({s.id for s in ss}) == len(ss)

    for submission in ss:
        assert submission.id > 0
        assert submission.type != ""
        assert submission.rating != ""
        assert submission.thumbnail_url != ""


# noinspection DuplicatedCode
def test_journals(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)

    js: list[JournalPartial] = []
    p: Optional[int] = None
    i = 0
    while True:
        js_, p_, subpages_ = api.journals(data["journals"]["user"], p)
        i+=1
        assert len(subpages_) == 0
        assert isinstance(js, list)
        assert all(isinstance(s, JournalPartial) for s in js_)
        assert len(js) or p == None
        assert len(js_) or p_ is None

        js.extend(js_)
        p = p_

        if not p:
            break

    assert len(js) >= data["journals"]["length"]
    assert len({j.id for j in js}) == len(js)

    for journal in js:
        assert journal.id > 0
        # assert journal.author.join_date.timestamp() > 0
        assert journal.date.timestamp() > 0
        assert journal.author.name_url == username_url(data["journals"]["user"])


# noinspection DuplicatedCode
def test_watchlist_to(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)
    assert api.login_status

    ws: list[UserPartial] = []
    p: Optional[int] = None

    while True:
        ws_, p_, subpages_ = api.watchlist_to(data["watchlist"]["user"], p)
        assert len(subpages_) == 0
        assert isinstance(ws, list)
        assert all(isinstance(s, UserPartial) for s in ws_)
        assert p_ is None or isinstance(p_, int)
        assert p_ is None or p_ > p
        assert len(ws) or p is None
        assert len(ws_) or p_ is None

        ws.extend(ws_)
        p = p_

        if not p:
            break

    assert len({w.name_url for w in ws}) == len(ws)


# noinspection DuplicatedCode
def test_watchlist_by(test_data, cookies: RequestsCookieJar, data: dict):
    api: FAAPI_ABC = test_data.backend(cookies)
    assert api.login_status

    ws: list[UserPartial] = []
    p: Optional[int] = None

    while True:
        ws_, p_, subpages_ = api.watchlist_by(data["watchlist"]["user"], p)
        assert len(subpages_) == 0
        assert isinstance(ws, list)
        assert all(isinstance(s, UserPartial) for s in ws_)
        assert p_ is None or isinstance(p_, int)
        assert p_ is None or p_ > p
        assert len(ws) or p is None
        assert len(ws_) or p_ is None

        ws.extend(ws_)
        p = p_

        if not p:
            break

    assert len({w.name_url for w in ws}) == len(ws)
