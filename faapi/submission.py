from collections import namedtuple
from dataclasses import KW_ONLY, dataclass
from datetime import datetime
from typing import Optional, Type

from faapi.interface.faapi_abc import FAAPI_ABC

from .connection import join_url
from .exceptions import _raise_exception
from bs4 import BeautifulSoup
from bs4 import Tag
from .user import UserPartial


class SubmissionStats(namedtuple("SubmissionStats", ["views", "comments", "favorites"])):
    """
    This object contains the submission's statistics:
    * views
    * comments
    * favorites
    """


class SubmissionUserFolder(namedtuple("SubmissionUserFolder", ["name", "url", "group"])):
    """
    This object contains a submission's folder details:
    * name: str the name of the folder
    * url: str the URL to the folder
    * group: str the group the folder belongs to
    """


class SubmissionBase:
    """
    Base class for the submission objects.
    """

    def __init__(self, parserClass: Type[FAAPI_ABC]):
        self.id: int = 0
        self.title: str = ""
        self.author: UserPartial = UserPartial(parserClass)
        self.parserClass = parserClass

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if isinstance(other, SubmissionBase):
            return other.id == self.id
        elif isinstance(other, int):
            return other == self.id
        return False

    def __gt__(self, other) -> bool:
        if isinstance(other, SubmissionBase):
            return self.id > other.id
        elif isinstance(other, int):
            return self.id > other
        return False

    def __ge__(self, other) -> bool:
        if isinstance(other, SubmissionBase):
            return self.id >= other.id
        elif isinstance(other, int):
            return self.id >= other
        return False

    def __lt__(self, other) -> bool:
        if isinstance(other, SubmissionBase):
            return self.id < other.id
        elif isinstance(other, int):
            return self.id < other
        return False

    def __le__(self, other) -> bool:
        if isinstance(other, SubmissionBase):
            return self.id <= other.id
        elif isinstance(other, int):
            return self.id <= other
        return False

    def __iter__(self):
        yield "id", self.id
        yield "title", self.title
        yield "author", dict(self.author)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.id} {self.author} {self.title}"

    @property
    def url(self):
        """
        Compose the full URL to the submission.

        :return: The URL to the submission.
        """
        return join_url(self.parserClass.root(), "view", self.id)


class SubmissionPartial(SubmissionBase):
    """
    Contains partial submission information gathered from submissions pages (gallery, scraps, etc.).
    """

    @dataclass
    class Record:
        _: KW_ONLY
        id: int
        title: str
        rating: str
        type: str
        thumbnail_url: str
        author: str = ""

    def __init__(self, parserClass: Type[FAAPI_ABC], submission_figure: Optional[Record] = None):
        """
        :param submission_figure: The figure tag from which to parse the submission information.
        """

        super().__init__(parserClass)

        self.submission_figure: Optional[SubmissionPartial.Record] = submission_figure
        self.rating: str = ""
        self.type: str = ""
        self.thumbnail_url: str = ""

        self.parse()

    def __iter__(self):
        yield "id", self.id
        yield "title", self.title
        yield "author", dict(self.author)
        yield "rating", self.rating
        yield "type", self.type
        yield "thumbnail_url", self.thumbnail_url

    def parse(self, submission_figure: Optional[Record] = None):
        """
        Parse a submission figure Tag, overrides any information already present in the object.

        :param submission_figure: The optional figure tag from which to parse the submission.
        """

        self.submission_figure = submission_figure or self.submission_figure
        if self.submission_figure is None:
            return

        # parsed: dict = self.parserClass.parser().parse_submission_figure(self.submission_figure)

        self.id = self.submission_figure.id
        self.title = self.submission_figure.title
        self.author.name = self.submission_figure.author
        self.rating = self.submission_figure.rating
        self.type = self.submission_figure.type
        self.thumbnail_url = self.submission_figure.thumbnail_url


class Submission(SubmissionBase):
    """
    Contains complete submission information gathered from submission pages, including comments.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        id: int
        title: str
        author: str
        rating: str
        type: str
        thumbnail_url: str
        author_title: str
        author_icon_url: str
        date: datetime
        tags: list[str]
        category: str
        species: str
        gender: str
        views: int
        comment_count: int
        favorites: int
        description: str
        footer: str
        mentions: list[str]
        folder: str
        user_folders: list[SubmissionUserFolder] 
        file_url: str
        prev: Optional[int]
        next: Optional[int]
        favorite: bool
        favorite_toggle_link: str


    def __init__(self, parserClass: Type[FAAPI_ABC], submission_page: Optional[Record] = None):
        """
        :param submission_page: The page from which to parse the submission information.
        """

        super().__init__(parserClass)

        self.submission_page: Optional[Submission.Record] = submission_page
        self.date: datetime = datetime.fromtimestamp(0)
        self.tags: list[str] = []
        self.category: str = ""
        self.species: str = ""
        self.gender: str = ""
        self.rating: str = ""
        self.stats: SubmissionStats = SubmissionStats(0, 0, 0)
        self.type: str = ""
        self.description: str = ""
        self.footer: str = ""
        self.mentions: list[str] = []
        self.folder: str = ""
        self.user_folders: list[SubmissionUserFolder] = []
        self.file_url: str = ""
        self.thumbnail_url: str = ""
        self.prev: Optional[int] = None
        self.next: Optional[int] = None
        self.favorite: bool = False
        self.favorite_toggle_link: str = ""
        from .comment import Comment
        self.comments: list[Comment] = []

        self.parse()

    def __iter__(self):
        yield "id", self.id
        yield "title", self.title
        yield "author", dict(self.author)
        yield "date", self.date
        yield "tags", self.tags
        yield "category", self.category
        yield "species", self.species
        yield "gender", self.gender
        yield "rating", self.rating
        yield "stats", self.stats._asdict()
        yield "type", self.type
        yield "description", self.description
        yield "footer", self.footer
        yield "mentions", self.mentions
        yield "folder", self.folder
        yield "user_folders", [f._asdict() for f in self.user_folders]
        yield "file_url", self.file_url
        yield "thumbnail_url", self.thumbnail_url
        yield "prev", self.prev
        yield "next", self.next
        yield "favorite", self.favorite
        yield "favorite_toggle_link", self.favorite_toggle_link
        from .comment import _remove_recursion
        yield "comments", [dict(_remove_recursion(c)) for c in self.comments]

    @property
    def description_bbcode(self) -> str:
        """
        The submission description formatted to BBCode

        :return: BBCode description
        """
        return self.parserClass.parser().html_to_bbcode(self.description)

    @property
    def footer_bbcode(self) -> str:
        """
        The submission footer formatted to BBCode

        :return: BBCode footer
        """
        return self.parserClass.parser().html_to_bbcode(self.footer)

    def parse(self, submission_page: Optional[Record] = None):
        """
        Parse a submission page, overrides any information already present in the object.

        :param submission_page: The optional page from which to parse the submission.
        """

        self.submission_page = submission_page or self.submission_page
        if self.submission_page is None:
            return

        self.id = self.submission_page.id
        self.title = self.submission_page.title
        self.author.name = self.submission_page.author
        self.author.title = self.submission_page.author_title
        self.author.user_icon_url = self.submission_page.author_icon_url
        self.date = self.submission_page.date
        self.tags = self.submission_page.tags
        self.category = self.submission_page.category
        self.species = self.submission_page.species
        self.gender = self.submission_page.gender
        self.rating = self.submission_page.rating
        self.stats = SubmissionStats(self.submission_page.views, self.submission_page.comment_count, self.submission_page.favorites)
        self.type = self.submission_page.type
        self.description = self.submission_page.description
        self.footer = self.submission_page.footer
        self.mentions = self.submission_page.mentions
        self.folder = self.submission_page.folder
        self.user_folders = self.submission_page.user_folders
        self.file_url = self.submission_page.file_url
        self.thumbnail_url = self.submission_page.thumbnail_url
        self.prev = self.submission_page.prev
        self.next = self.submission_page.next
        self.favorite = self.submission_page.favorite
        self.favorite_toggle_link = self.submission_page.favorite_toggle_link
        
