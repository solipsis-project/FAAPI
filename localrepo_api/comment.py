from __future__ import annotations
from dataclasses import KW_ONLY, dataclass

from datetime import datetime
from typing import Optional, Type
from typing import Union

from bs4.element import Tag

from localrepo_api.interface.faapi_abc import FAAPI_ABC
from .exceptions import _raise_exception

from localrepo_api.user import UserPartial

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from localrepo_api.submission import Submission
    from localrepo_api.journal import Journal
    


class Comment:
    """
    Contains comment information and references to replies and parent objects.
    """

    @dataclass
    class Record:
        _: KW_ONLY
        id: int
        timestamp: datetime
        user_name: str
        user_title: str
        avatar_url: str
        text: str
        parent: int
        edited: bool
        hidden: bool

    def __init__(self, parserClass: Type[FAAPI_ABC], tag: Optional[Record] = None, parent: Union[None, Submission, Journal] = None):
        """
        :param tag: The comment tag from which to parse information
        :param parent: The parent object of the comment
        """
        self.comment_tag: Optional[Comment.Record] = tag

        self.id: int = 0
        self.author: UserPartial = UserPartial(parserClass)
        self.date: datetime = datetime.fromtimestamp(0)
        self.text: str = ""
        self.replies: list[Comment] = []
        self.reply_to: Optional[Union[Comment, int]] = None
        self.edited: bool = False
        self.hidden: bool = False
        self.parent: Optional[Union[Submission, Journal]] = parent
        self.parserClass = parserClass

        self.parse()

    def __hash__(self) -> int:
        return hash((self.id, type(self.parent), self.parent))

    def __eq__(self, other) -> bool:
        if isinstance(other, Comment):
            return other.id == self.id and self.parent == other.parent
        elif isinstance(other, int):
            return other == self.id
        return False

    def __gt__(self, other) -> bool:
        if isinstance(other, Comment):
            return self.id > other.id
        elif isinstance(other, int):
            return self.id > other
        return False

    def __ge__(self, other) -> bool:
        if isinstance(other, Comment):
            return self.id >= other.id
        elif isinstance(other, int):
            return self.id >= other
        return False

    def __lt__(self, other) -> bool:
        if isinstance(other, Comment):
            return self.id < other.id
        elif isinstance(other, int):
            return self.id < other
        return False

    def __le__(self, other) -> bool:
        if isinstance(other, Comment):
            return self.id <= other.id
        elif isinstance(other, int):
            return self.id <= other
        return False

    def __iter__(self):
        yield "id", self.id
        yield "author", dict(self.author)
        yield "date", self.date
        yield "text", self.text
        yield "replies", [dict(r) for r in self.replies]
        yield "reply_to", dict(_remove_recursion(self.reply_to)) if isinstance(self.reply_to, Comment) \
            else self.reply_to
        yield "edited", self.edited
        yield "hidden", self.hidden
        yield "parent", None if self.parent is None else dict(self.parent)

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.id} {self.author}".rstrip()

    @property
    def text_bbcode(self) -> str:
        """
        The comment text formatted to BBCode

        :return: BBCode text
        """
        return self.parserClass.html_to_bbcode(self.text)

    @property
    def url(self):
        """
        Compose the full URL to the comment.

        :return: The URL to the comment.
        """
        return "" if self.parent is None else f"{self.parent.url}#cid:{self.id}"

    def parse(self, comment_tag: Optional[Record] = None):
        """
        Parse a comment tag, overrides any information already present in the object.

        :param comment_tag: The comment tag from which to parse information
        """
        self.comment_tag = comment_tag or self.comment_tag
        if self.comment_tag is None:
            return

        self.id = self.comment_tag.id
        self.date = self.comment_tag.timestamp
        self.author = UserPartial(self.parserClass)
        self.author.name = self.comment_tag.user_name
        self.author.title = self.comment_tag.user_title
        self.author.avatar_url = self.comment_tag.avatar_url
        self.text = self.comment_tag.text
        self.replies = []
        self.reply_to = self.comment_tag.parent
        self.edited = self.comment_tag.edited
        self.hidden = self.comment_tag.hidden


def sort_comments(comments: list[Comment]) -> list[Comment]:
    """
    Sort a list of comments into a tree structure. Replies are overwritten.

    :param comments: A list of Comment objects (flat or tree-structured)
    :return: A tree-structured list of comments with replies
    """
    print(comments)
    for comment in (comments := sorted(flatten_comments(comments))):
        print(comment)
        comment.replies = [_set_reply_to(c, comment) for c in comments if c.reply_to == comment]
    return [c for c in comments if c.reply_to is None]


def flatten_comments(comments: list[Comment]) -> list[Comment]:
    """
    Flattens a list of comments. Replies are not modified.

    :param comments: A list of Comment objects (flat or tree-structured)
    :return: A flat date-sorted (ascending) list of comments
    """
    return sorted({c for c in [r for c in comments for r in [c, *flatten_comments(c.replies)]]})


def _set_reply_to(comment: Comment, reply_to: Union[Comment, int]) -> Comment:
    comment.reply_to = reply_to
    return comment


def _remove_recursion(comment: Comment) -> Comment:
    comment_new: Comment = Comment(comment.parserClass)

    comment_new.comment_tag = comment.comment_tag
    comment_new.id = comment.id
    comment_new.author = comment.author
    comment_new.date = comment.date
    comment_new.text = comment.text
    comment_new.replies = [_remove_recursion(c) for c in comment.replies]
    comment_new.reply_to = comment.reply_to.id if isinstance(comment.reply_to, Comment) else comment.reply_to
    comment_new.edited = comment.edited
    comment_new.hidden = comment.hidden
    comment_new.parent = None

    return comment_new
