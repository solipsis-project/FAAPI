from collections import namedtuple
from dataclasses import KW_ONLY, dataclass
from datetime import datetime
from typing import Optional, Type
from urllib.parse import quote

from faapi.interface.faapi_abc import FAAPI_ABC

from .connection import join_url
from .exceptions import _raise_exception
from bs4 import BeautifulSoup
from bs4 import Tag


class UserStats(namedtuple("UserStats", ["views", "submissions", "favorites", "comments_earned",
                                         "comments_made", "journals", "watched_by", "watching"])):
    """
    This object contains a user's statistics:
    * views
    * submissions
    * favorites
    * comments_earned
    * comments_made
    * journals
    * watched_by
    * watching
    """


class UserBase:
    """
    Base class for the user objects.
    """

    def __init__(self, parserClass: Type[FAAPI_ABC]):
        self.name: str = ""
        self.status: str = ""
        self.parserClass = parserClass

    def __hash__(self) -> int:
        return hash(self.name_url)

    def __eq__(self, other) -> bool:
        if isinstance(other, UserBase):
            return other.name_url == self.name_url
        elif isinstance(other, str):
            return self.parserClass.username_url(other) == self.name_url
        return False

    def __gt__(self, other) -> bool:
        if isinstance(other, UserBase):
            return self.name_url > other.name_url
        elif isinstance(other, str):
            return self.name_url > self.parserClass.username_url(other)
        return False

    def __ge__(self, other) -> bool:
        if isinstance(other, UserBase):
            return self.name_url >= other.name_url
        elif isinstance(other, str):
            return self.name_url >= self.parserClass.username_url(other)
        return False

    def __lt__(self, other) -> bool:
        if isinstance(other, UserBase):
            return self.name_url < other.name_url
        elif isinstance(other, str):
            return self.name_url < self.parserClass.username_url(other)
        return False

    def __le__(self, other) -> bool:
        if isinstance(other, UserBase):
            return self.name_url <= other.name_url
        elif isinstance(other, str):
            return self.name_url <= self.parserClass.username_url(other)
        return False

    def __iter__(self):
        yield "name", self.name
        yield "status", self.status

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str(self.status) + str(self.name)

    @property
    def name_url(self):
        """
        Compose the URL-safe username.

        :return: The cleaned username.
        """
        return self.parserClass.username_url(self.name)

    @property
    def url(self):
        """
        Compose the full URL to the user.

        :return: The URL to the user.
        """
        return join_url(self.parserClass.root(), "user", quote(self.name_url))

    def generate_user_icon_url(self) -> str:
        """
        Generate the URl for the current user icon.

        :return: The URL to the user icon
        """
        return f"https://a.furaffinity.net/{datetime.now():%Y%m%d}/{self.name_url}.gif"


class UserPartial(UserBase):
    """
    Contains partial user information gathered from user folders (gallery, journals, etc.) and submission/journal pages.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        name: str
        status: str
        title: str
        join_date: datetime
        user_icon_url: str

    def __init__(self, parserClass : Type[FAAPI_ABC], user_tag: Optional[Record] = None):
        """
        :param user_tag: The tag from which to parse the user information.
        """

        super().__init__(parserClass)

        self.user_tag: Optional[UserPartial.Record] = user_tag
        self.title: str = ""
        self.join_date: datetime = datetime.fromtimestamp(0)
        self.user_icon_url: str = ""

        self.parse()

    def __iter__(self):
        yield "name", self.name
        yield "status", self.status
        yield "title", self.title
        yield "join_date", self.join_date
        yield "user_icon_url", self.user_icon_url

    def parse(self, user_tag: Optional[Record] = None):
        """
        Parse a user page, overrides any information already present in the object.

        :param user_tag: The tag from which to parse the user information.
        """

        self.user_tag = user_tag or self.user_tag
        if self.user_tag is None:
            return

        # parsed: dict = self.parserClass.parser().parse_user_tag(self.user_tag)

        self.name = self.user_tag.name
        self.status = self.user_tag.status
        self.title = self.user_tag.title
        self.join_date = self.user_tag.join_date
        self.user_icon_url = self.user_tag.user_icon_url

class User(UserBase):
    """
    Contains complete user information gathered from userpages.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        name: str
        status: str
        profile: str
        title: str
        join_date: datetime
        stats: UserStats
        info: dict[str, str]
        contacts: dict[str, str]
        user_icon_url: str
        watched: bool
        watched_toggle_link: Optional[str]
        blocked: bool
        blocked_toggle_link: Optional[str]

    def __init__(self, parserClass : Type[FAAPI_ABC], user_page: Optional[Record] = None):
        """
        :param user_page: The page from which to parse the user information.
        """

        super().__init__(parserClass)
        self.user_page: Optional[User.Record] = user_page
        self.title: str = ""
        self.join_date: datetime = datetime.fromtimestamp(0)
        self.profile: str = ""
        self.stats: UserStats = UserStats(0, 0, 0, 0, 0, 0, 0, 0)
        self.info: dict[str, str] = {}
        self.contacts: dict[str, str] = {}
        self.user_icon_url: str = ""
        self.watched: bool = False
        self.watched_toggle_link: Optional[str] = None
        self.blocked: bool = False
        self.blocked_toggle_link: Optional[str] = None

        self.parse()

    def __iter__(self):
        yield "name", self.name
        yield "status", self.status
        yield "title", self.title
        yield "join_date", self.join_date
        yield "profile", self.profile
        yield "stats", self.stats._asdict()
        yield "info", self.info
        yield "contacts", self.contacts
        yield "user_icon_url", self.user_icon_url
        yield "watched", self.watched
        yield "watched_toggle_link", self.watched_toggle_link
        yield "blocked", self.blocked
        yield "blocked_toggle_link", self.blocked_toggle_link

    @property
    def profile_bbcode(self) -> str:
        """
        The user profile text formatted to BBCode

        :return: BBCode profile
        """
        return self.parserClass.html_to_bbcode(self.profile)

    def parse(self, user_page: Optional[Record] = None):
        """
        Parse a user page, overrides any information already present in the object.

        :param user_page: The page from which to parse the user information.
        """
        self.user_page = user_page or self.user_page
        if self.user_page is None:
            return

        # parsed: dict = self.parserClass.parser().parse_user_page(self.user_page)

        self.name = self.user_page.name
        self.status = self.user_page.status
        self.profile = self.user_page.profile
        self.title = self.user_page.title
        self.join_date = self.user_page.join_date
        self.stats = UserStats(*self.user_page.stats)
        self.info = self.user_page.info
        self.contacts = self.user_page.contacts
        self.user_icon_url = self.user_page.user_icon_url
        self.watched = self.user_page.watched
        self.watched_toggle_link = self.user_page.watched_toggle_link
        self.blocked = self.user_page.blocked
        self.blocked_toggle_link = self.user_page.blocked_toggle_link
