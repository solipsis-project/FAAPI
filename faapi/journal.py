from collections import namedtuple
from dataclasses import KW_ONLY, dataclass
from datetime import datetime
from typing import List, Optional, Type
from typing import Union

from faapi.interface.faapi_abc import FAAPI_ABC

from .connection import join_url
from .exceptions import _raise_exception
from bs4 import BeautifulSoup
from bs4 import Tag
from .user import UserPartial


class JournalStats(namedtuple("JournalStats", ["comments"])):
    """
    This object contains the journal's statistics:
    * comments
    """


class JournalBase:
    def __init__(self, parserClass: Type[FAAPI_ABC]):
        self.id: int = 0
        self.title: str = ""
        self.date: datetime = datetime.fromtimestamp(0)
        self.author: UserPartial = UserPartial(parserClass)
        self.stats: JournalStats = JournalStats(0)
        self.content: str = ""
        self.mentions: list[str] = []
        self.parserClass = parserClass;

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if isinstance(other, JournalBase):
            return other.id == self.id
        elif isinstance(other, int):
            return other == self.id
        return False

    def __gt__(self, other) -> bool:
        if isinstance(other, JournalBase):
            return self.id > other.id
        elif isinstance(other, int):
            return self.id > other
        return False

    def __ge__(self, other) -> bool:
        if isinstance(other, JournalBase):
            return self.id >= other.id
        elif isinstance(other, int):
            return self.id >= other
        return False

    def __lt__(self, other) -> bool:
        if isinstance(other, JournalBase):
            return self.id < other.id
        elif isinstance(other, int):
            return self.id < other
        return False

    def __le__(self, other) -> bool:
        if isinstance(other, JournalBase):
            return self.id <= other.id
        elif isinstance(other, int):
            return self.id <= other
        return False

    def __iter__(self):
        yield "id", self.id
        yield "title", self.title
        yield "date", self.date
        yield "author", dict(self.author)
        yield "stats", self.stats._asdict()
        yield "content", self.content
        yield "mentions", self.mentions

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.id} {self.author} {self.title}"

    @property
    def content_bbcode(self) -> str:
        """
        The journal content formatted to BBCode

        :return: BBCode content
        """
        return self.parserClass.parser().html_to_bbcode(self.content)

    @property
    def url(self) -> str:
        """
        Compose the full URL to the journal.

        :return: The URL to the journal.
        """
        return join_url(self.parserClass.root(), "journal", self.id)


class JournalPartial(JournalBase):
    """
    Contains partial journal information gathered from journals pages.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        id: int
        title: str
        comments: int
        date: datetime
        content: str
        mentions: List[str]
        user_name: str = ""
        user_status: str = ""
        user_title: str = ""
        user_icon_url: str = ""
        user_join_date: datetime = datetime.min

    def __init__(self,  parserClass : Type[FAAPI_ABC], journal_tag: Optional[Record] = None):
        """
        :param journal_tag: The tag from which to parse the journal.
        """
        self.journal_tag: Optional[JournalPartial.Record] = journal_tag

        super(JournalPartial, self).__init__(parserClass)

        self.parse()

    def parse(self, journal_tag: Optional[Record] = None):
        """
        Parse a journal tag, overrides any information already present in the object.

        :param journal_tag: The tag from which to parse the journal.
        """

        self.journal_tag = journal_tag or self.journal_tag
        if self.journal_tag is None:
            return

        # parsed: dict = self.parserClass.parser().parse_journal_section(self.journal_tag)

        # noinspection DuplicatedCode
        self.id = self.journal_tag.id
        self.title = self.journal_tag.title
        self.author.name = self.journal_tag.user_name
        self.author.status = self.journal_tag.user_status
        self.author.title = self.journal_tag.user_title
        self.author.join_date = self.journal_tag.user_join_date
        self.author.user_icon_url = self.journal_tag.user_icon_url
        self.stats = JournalStats(self.journal_tag.comments)
        self.date = self.journal_tag.date
        self.content = self.journal_tag.content
        self.mentions = self.journal_tag.mentions


class Journal(JournalBase):
    """
    Contains complete journal information gathered from journal pages, including comments.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        id: int
        title: str
        comments: int
        user_name: str
        user_status: str
        user_title: str
        user_join_date: datetime
        user_icon_url: str
        date: datetime
        content: str
        header: str
        footer: str
        mentions: List[str]

    def __init__(self, parserClass : Type[FAAPI_ABC], journal_page: Optional[Record] = None):
        """
        :param journal_page: The page from which to parse the journal.
        """

        self.journal_page: Optional[Journal.Record] = journal_page

        super(Journal, self).__init__(parserClass)

        self.header: str = ""
        self.footer: str = ""
        from .comment import Comment
        self.comments: list[Comment] = []

        self.parse()

    def __iter__(self):
        for k, v in super(Journal, self).__iter__():
            yield k, v
        yield "header", self.header
        yield "footer", self.footer
        from .comment import _remove_recursion
        yield "comments", [dict(_remove_recursion(c)) for c in self.comments]

    @property
    def header_bbcode(self) -> str:
        """
        The journal header formatted to BBCode

        :return: BBCode header
        """
        return self.parserClass.parser().html_to_bbcode(self.header)

    @property
    def footer_bbcode(self) -> str:
        """
        The journal footer formatted to BBCode

        :return: BBCode footer
        """
        return self.parserClass.parser().html_to_bbcode(self.footer)

    def parse(self, journal_page: Optional[Record] = None):
        """
        Parse a journal page, overrides any information already present in the object.

        :param journal_page: The page from which to parse the journal.
        """
        self.journal_page = journal_page or self.journal_page
        if self.journal_page is None:
            return

        # parsed: dict = self.parserClass.parser().parse_journal_page(self.journal_page)

        # noinspection DuplicatedCode
        self.id = self.journal_page.id
        self.title = self.journal_page.title
        self.author.name = self.journal_page.user_name
        self.author.status = self.journal_page.user_status
        self.author.title = self.journal_page.user_title
        self.author.join_date = self.journal_page.user_join_date
        self.author.user_icon_url = self.journal_page.user_icon_url
        self.stats = JournalStats(self.journal_page.comments)
        self.date = self.journal_page.date
        self.content = self.journal_page.content
        self.header = self.journal_page.header
        self.footer = self.journal_page.footer
        self.mentions = self.journal_page.mentions
