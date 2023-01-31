from datetime import datetime, timezone
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
import re
from typing import Any, Dict
from typing import Optional
from typing import NewType
from dateutil.tz import tzutc

from bs4 import BeautifulSoup
from bs4.element import NavigableString
from bs4.element import Tag
from dateutil.parser import parse as parse_date

from faapi.parse import clean_html, inner_html
from faapi.user import User, UserStats

from ..exceptions import DisabledAccount, Unauthorized
from ..exceptions import NoTitle
from ..exceptions import NonePage
from ..exceptions import NotFound
from ..exceptions import NoticeMessage
from ..exceptions import ParsingError
from ..exceptions import ServerError
from ..exceptions import _raise_exception

from abc import ABC, abstractmethod
from datetime import datetime
from re import MULTILINE
from re import Match
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
from typing import Any
from typing import Optional
from typing import Union

from bbcode import Parser as BBCodeParser  # type:ignore
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from bs4.element import Tag
from dateutil.parser import parse as parse_date
from htmlmin import minify  # type:ignore

from ..exceptions import DisabledAccount
from ..exceptions import NoTitle
from ..exceptions import NonePage
from ..exceptions import NotFound
from ..exceptions import NoticeMessage
from ..exceptions import ParsingError
from ..exceptions import ServerError
from ..exceptions import _raise_exception

import locale
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

def find_title_tag(bs: BeautifulSoup, title: str):
    for title_tag in bs.select("div.title"):
        if title_tag.text == title:
            return title_tag.next_sibling.span
    _raise_exception(ParsingError(f"Missing {title} tag"))

def parse_contact_details(bs: BeautifulSoup) -> dict[str, str]:
    contacts_tag = find_title_tag(bs, "Links and Contact Details")

    contacts: dict[str, str] = {}

    for div_tag in contacts_tag.next_siblings:
        children = div_tag.find_all("div", recursive = False)
        if len(children) == 2:
            site_name = children[0].text
            link = children[1].a["href"]
            contacts[site_name] = link

    return contacts

def parse_user_profile(username: str, bs: BeautifulSoup) -> User.Record:

    profile_tag = find_title_tag(bs, "Profile")
    profile_description = clean_html(inner_html(profile_tag))

    views_tag = bs.select_one('span[title="Submission Views Received"] > strong')
    assert views_tag is not None, _raise_exception(ParsingError("Missing views tag"))

    submissions_tag = bs.select_one('span[title="Submissions Uploaded"] > strong')
    assert submissions_tag is not None, _raise_exception(ParsingError("Missing submissions tag"))

    favorites_tag = bs.select_one('span[title="Favorites Received"] > strong')
    assert favorites_tag is not None, _raise_exception(ParsingError("Missing favorites tag"))

    comments_earned_tag = bs.select_one('span[title="Comments Received"] > strong')
    assert comments_earned_tag is not None, _raise_exception(ParsingError("Missing comments received tag"))

    comments_made_tag = bs.select_one('span[title="Comments Given"] > strong')
    assert comments_made_tag is not None, _raise_exception(ParsingError("Missing comments given tag"))

    journals_tag = bs.select_one('span[title="Journals Created"] > strong')
    assert journals_tag is not None, _raise_exception(ParsingError("Missing journals tag"))

    watchers_tag = bs.select_one('span[title="Watches Received"] > strong')
    assert watchers_tag is not None, _raise_exception(ParsingError("Missing watchers tag"))

    watches_tag = bs.select_one('#watches strong')
    assert watches_tag is not None, _raise_exception(ParsingError("Missing watches tag"))

    contacts = parse_contact_details(bs)    

    profile_image_tag = bs.select_one('meta[property="og:image"]')
    assert profile_image_tag is not None, _raise_exception(ParsingError("Missing profile image tag"))

    watchbox_tag = bs.select_one("#widget-watchbox-watchstate")
    assert watchbox_tag is not None, _raise_exception(ParsingError("Missing profile watchbox tag"))

    watched = (watchbox_tag["value"] == "true")

    block_remove_form = bs.select_one("#block_remove_form")
    assert block_remove_form is not None, _raise_exception(ParsingError("Missing block remove form tag"))

    blocked = "UnBlock user's submissions." in block_remove_form.next_sibling.next_sibling.text

    return User.Record(
        name = username,
        status = "",
        profile = profile_description,
        title = "",
        join_date = datetime.fromtimestamp(0),
        stats = UserStats(
            views= locale.atoi(views_tag.text),
            submissions= locale.atoi(submissions_tag.text),
            favorites= locale.atoi(favorites_tag.text),
            comments_earned= locale.atoi(comments_earned_tag.text),
            comments_made= locale.atoi(comments_made_tag.text),
            journals= locale.atoi(journals_tag.text),
            watched_by= locale.atoi(watchers_tag.text),
            watching= locale.atoi(watches_tag.text)
        ),
        info = {},
        contacts= contacts,
        user_icon_url = profile_image_tag["content"],
        watched= watched,
        watched_toggle_link= None,
        blocked= blocked,
        blocked_toggle_link= None
    )
