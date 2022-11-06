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

from faapi.interface.parser_abc import ParserABC

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

class WeasylParser(ParserABC):
    @staticmethod
    @abstractmethod
    def html_to_bbcode(html: str) -> str:
        ...

    @staticmethod
    @abstractmethod
    def username_url(username: str) -> str:
        return sub(r"[^a-z\d.~-]", "", username.lower())
       

def parse_submission_figure(figure_tag: Tag) -> dict[str, Any]:
    id_link_tag = figure_tag.a

    assert id_link_tag is not None, _raise_exception(ParsingError("Missing ID tag"))

    id_: int = int(id_link_tag.attrs["href"].split("/")[3])

    tag_title: Optional[Tag] = figure_tag.select_one(".title")
    tag_author: Optional[Tag] = figure_tag.select_one(".byline")
    tag_thumbnail: Optional[Tag] = figure_tag.select_one("img")

    assert tag_title is not None, _raise_exception(ParsingError("Missing title tag"))
    assert tag_author is not None, _raise_exception(ParsingError("Missing author tag"))
    assert tag_thumbnail is not None, _raise_exception(ParsingError("Missing thumbnail tag"))

    title: str = tag_title.attrs["title"]
    author: str = tag_author.attrs["title"][3:]
    rating: str = ""
    type_: str = "submission"
    thumbnail_url: str = tag_thumbnail.attrs["src"]

    return {
        "id": id_,
        "title": title,
        "author": author,
        "rating": rating,
        "type": type_,
        "thumbnail_url": thumbnail_url,
    }


def parse_user_tag(user_tag: Tag) -> dict[str, Any]:
    name = user_tag.select_one(".username")
    user_id_tag = user_tag.select_one("#user-id")

    assert user_id_tag is not None, _raise_exception(ParsingError("Missing user id tag"))

    user_info = user_id_tag.text.split("/")
    title = user_info[0]
    status = user_info[4] if len(user_info) >= 5 else ""
    join_date: datetime = datetime.fromtimestamp(0, tz = tzutc())

    return {
        "user_name": name.text.strip(),
        "user_status": status,
        "user_title": title,
        "user_join_date": join_date,
    }


def parse_user_folder(folder_page: BeautifulSoup) -> dict[str, Any]:
    tag_username: Optional[Tag] = folder_page.select_one("#user-info")
    assert tag_username is not None, _raise_exception(ParsingError("Missing username tag"))
    tag_user_icon: Optional[Tag] = tag_username.select_one(".avatar")
    assert tag_user_icon is not None, _raise_exception(ParsingError("Missing user icon tag"))
    tag_user_img = tag_user_icon.select_one("img")
    assert tag_user_img is not None, _raise_exception(ParsingError("Missing user image"))
    return {
        **parse_user_tag(tag_username),
        "user_icon_url": tag_user_img.attrs["src"],
    }


def parse_submission_figures(figures_page: BeautifulSoup) -> list[Tag]:
    return figures_page.select(".item")

def parse_user_favorites(favorites_page: BeautifulSoup) -> dict[str, Any]:
    user_info: dict[str, str] = parse_user_folder(favorites_page)
    next_page: str = None
    href_re = re.compile("/favorites\\?userid=.*&feature=submit&nextid=(.*)")
    def match_href(url: str):
        match = href_re.match(url)
        if match:
            nonlocal next_page
            next_page = match[1]
    favorites_page.find("a", href=match_href)

    return {
        **user_info,
        "figures": parse_submission_figures(favorites_page),
        "last_page": next_page is None,
        "next_page": next_page,
    }



