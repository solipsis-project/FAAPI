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

class ParserABC(ABC):
    @staticmethod
    @abstractmethod
    def html_to_bbcode(html: str) -> str:
        ...

    @staticmethod
    @abstractmethod
    def bbcode_to_html_(bbcode: str) -> str:
        ...

    @staticmethod
    @abstractmethod
    def username_url(username: str) -> str:
        ...

    @staticmethod
    @abstractmethod
    def parse_user_tag(user_tag: Tag) -> dict[str, Any]:
        ...

    @staticmethod
    @abstractmethod
    def check_page_raise(page: BeautifulSoup) -> None:
        ...
    
    @staticmethod
    @abstractmethod
    def parse_submission_figure(figure_tag: Tag) -> dict[str, Any]:
        ...

    @staticmethod
    @abstractmethod
    def parse_user_page(user_page: BeautifulSoup) -> dict[str, Any]:
        ...
    
    @staticmethod
    @abstractmethod
    def parse_submission_page(sub_page: BeautifulSoup) -> dict[str, Any]:
        ...

    @staticmethod
    @abstractmethod
    def parse_comments(page: BeautifulSoup) -> list[Tag]:
        ...

    @staticmethod
    @abstractmethod
    def parse_journal_section(section_tag: Tag) -> dict[str, Any]:
        ...
    
    @staticmethod
    @abstractmethod
    def parse_journal_page(journal_page: BeautifulSoup) -> dict[str, Any]:
        ...

    @staticmethod
    @abstractmethod
    def parse_comment_tag(tag: Tag) -> dict:
        ...
       