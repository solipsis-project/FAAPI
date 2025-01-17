from http.cookiejar import CookieJar
from time import sleep
from time import time
from typing import Any
from typing import Optional
from typing import Union
from urllib.parse import quote
from urllib.robotparser import RobotFileParser

from localrepo_api.base import FAAPI_BASE
from localrepo_api.comment import Comment, sort_comments

from ..connection import CloudflareScraper
from ..connection import CookieDict
from ..connection import Response
from ..connection import get
from ..connection import get_robots
from ..connection import join_url
from ..connection import make_session
from ..connection import stream_binary
from ..exceptions import DisallowedPath
from ..exceptions import Unauthorized
from ..journal import Journal
from ..journal import JournalPartial
from .furaffinity_parser import BeautifulSoup, parse_tag_search, parse_comment_tag, parse_comments, parse_journal_page, parse_journal_section, parse_submission_figure, parse_submission_page, parse_user_page
from .furaffinity_parser import check_page_raise
from .furaffinity_parser import parse_loggedin_user
from .furaffinity_parser import parse_submission_figures
from .furaffinity_parser import parse_user_favorites
from .furaffinity_parser import parse_user_journals
from .furaffinity_parser import parse_user_submissions
from .furaffinity_parser import parse_watchlist
from .furaffinity_parser import username_url
from .furaffinity_parser import html_to_bbcode
from ..submission import Submission
from ..submission import SubmissionPartial
from ..user import User
from ..user import UserPartial
from . import furaffinity_parser


class FAAPI(FAAPI_BASE):
    """
    This class provides the methods to access and parse Fur Affinity pages and retrieve objects.
    """
    @staticmethod
    def root() -> str:
        return "https://www.furaffinity.net"

    def __init__(self, cookies: Union[list[CookieDict], CookieJar]):
        """
        :param cookies: The cookies for the session.
        """

        self.session: CloudflareScraper = make_session(cookies)  # Session used for get requests
        
        super().__init__(
            robots = get_robots(self.session, self.root()),  # robots.txt handler
            timeout = None,  # Timeout for requests
            raise_for_unauthorized = True  # Control login checks
        )
        
        self.last_get: float = time() - self.crawl_delay  # Time of last get (UNIX time)
        
        
    
    @property
    def login_status(self) -> bool:
        """
        Check the login status of the given cookies.

        :return: True if the cookies belong to a login session, False otherwise.
        """
        return parse_loggedin_user(self.get_parsed("login", skip_auth_check=True)) is not None

    def me(self) -> Optional[User]:
        """
        Fetch the information of the logged-in user.

        :return: A User object for the logged-in user, or None if the cookies are not from a login session.
        """
        return self.user(user) if (user := parse_loggedin_user(self.get_parsed("login"))) else None

    def frontpage(self) -> list[SubmissionPartial]:
        """
        Fetch latest submissions from Fur Affinity's front page

        :return: A list of SubmissionPartial objects
        """
        page_parsed: BeautifulSoup = self.get_parsed("/")
        submission_tags = parse_submission_figures(page_parsed)
        submissions: list[SubmissionPartial] = [SubmissionPartial(FAAPI, SubmissionPartial.Record(**parse_submission_figure(f))) for f in submission_tags]
        return sorted({s for s in submissions}, reverse=True)

    def submission(self, submission_id: int, get_file: bool = False, *, chunk_size: Optional[int] = None
                   ) -> tuple[Submission, list[bytes]]:
        """
        Fetch a submission and, optionally, its file.

        :param submission_id: The ID of the submission.
        :param get_file: Whether to download the submission file.
        :param chunk_size: The chunk_size to be used for the download (does not override get_file).
        :return: A Submission object and a bytes object (if the submission file is downloaded).
        """
        beautiful_soup = self.get_parsed(join_url("view", int(submission_id)))
        parsed_submission = parse_submission_page(beautiful_soup)
        fav_link = parsed_submission.pop('fav_link')
        unfav_link = parsed_submission.pop('unfav_link')
        parsed_submission['favorite_toggle_link'] = fav_link or unfav_link
        parsed_submission['favorite'] = unfav_link is not None
        sub: Submission = Submission(FAAPI, Submission.Record(**parsed_submission))
        comments = [Comment(FAAPI, Comment.Record(**parse_comment_tag(t)), sub) for t in parse_comments(beautiful_soup)]
        sub.comments = sort_comments(comments)
        sub_file: list[bytes] = self.submission_files(sub, chunk_size=chunk_size) if get_file and sub.id else []
        return sub, sub_file

    def journal(self, journal_id: int) -> Journal:
        """
        Fetch a journal.

        :param journal_id: The ID of the journal.
        :return: A Journal object.
        """
        beautiful_soup = self.get_parsed(join_url("journal", int(journal_id)))

        journal_dict = parse_journal_page(beautiful_soup)
        user_info = journal_dict.pop("user_info")
        parsed = Journal.Record(
            **journal_dict,
            user_name=user_info["name"],
            user_title=user_info["title"],
            user_status=user_info["status"],
            user_join_date=user_info["join_date"],
            avatar_url=user_info["avatar_url"])
        journal = Journal(FAAPI, parsed)
        comments = [Comment(FAAPI, Comment.Record(**parse_comment_tag(t)), journal) for t in parse_comments(beautiful_soup)]
        journal.comments = sort_comments(comments)
        return journal

    def user(self, user: str) -> User:
        """
        Fetch a user.

        :param user: The name of the user (_ characters are allowed).
        :return: A User object.
        """
        beautifulSoup = self.get_parsed(join_url("user", quote(username_url(user))))
        parsed_user = parse_user_page(beautifulSoup)
        watch = parsed_user.pop("watch")
        unwatch = parsed_user.pop("unwatch")
        block = parsed_user.pop("block")
        unblock = parsed_user.pop("unblock")
        parsed_user["watched"] = watch is None and unwatch is not None
        parsed_user["watched_toggle_link"] = watch or unwatch or None
        parsed_user["blocked"] = block is None and unblock is not None
        parsed_user["blocked_toggle_link"] = block or unblock or None
        return User(FAAPI, User.Record(**parsed_user))

    # noinspection DuplicatedCode
    def gallery(self, user: str, page: Any = 1) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's gallery page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        if page is None:
            page = 1
        page_parsed: BeautifulSoup = self.get_parsed(join_url("gallery", quote(username_url(user)), int(page)))
        info_parsed: dict[str, Any] = parse_user_submissions(page_parsed)
        author: UserPartial = UserPartial(FAAPI)
        user_info = info_parsed["user_info"]
        author.name, author.status, author.title, author.join_date, author.avatar_url = [
            user_info["name"], user_info["status"],
            user_info["title"], user_info["join_date"],
            user_info["avatar_url"]
        ]
        submissions = [SubmissionPartial(FAAPI, SubmissionPartial.Record(**parse_submission_figure(tag))) for tag in info_parsed["figures"]]
        for s in submissions:
            s.author = author
        return (submissions, (page + 1) if not info_parsed["last_page"] else None, [])

    # noinspection DuplicatedCode
    def scraps(self, user: str, page: Any = 1) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's scraps page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        if page is None:
            page = 1
        page_parsed: BeautifulSoup = self.get_parsed(join_url("scraps", quote(username_url(user)), int(page)))
        info_parsed: dict[str, Any] = parse_user_submissions(page_parsed)
        author: UserPartial = UserPartial(FAAPI)
        user_info = info_parsed["user_info"]
        author.name, author.status, author.title, author.join_date, author.avatar_url = [
            user_info["name"], user_info["status"],
            user_info["title"], user_info["join_date"],
            user_info["avatar_url"]
        ]
        submissions = [SubmissionPartial(FAAPI, SubmissionPartial.Record(**parse_submission_figure(tag))) for tag in info_parsed["figures"]]
        for s in submissions:
            s.author = author
        return (submissions, (page + 1) if not info_parsed["last_page"] else None, [])

    def favorites(self, user: str, page: Any = "") -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's favorites page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        if page is None:
            page = ""
        page_parsed: BeautifulSoup = self.get_parsed(join_url("favorites", quote(username_url(user)), page.strip()))
        info_parsed: dict[str, Any] = parse_user_favorites(page_parsed)
        submissions = [SubmissionPartial(FAAPI, SubmissionPartial.Record(**parse_submission_figure(tag))) for tag in info_parsed["figures"]]

        return (submissions, info_parsed["next_page"] or None, [])

    # noinspection DuplicatedCode
    def tag(self, tag: str, page: Any = 1) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch all submissions with a given tag.

        :param tag: The tag to search for.
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        if page is None:
            page = 1
        options = {
            "page": page,
            "q": "@keywords+{}".format(tag),
            "do_search": "Search",
            "order-by": "date",
            "order-direction": "desc",
            "range": "all",
            "range_from": "",
            "range_to": "",
            "rating-general": "1",
            "rating-mature": "1",
            "rating-adult": "1",
            "type-art": "1",
            "type-music": "1",
            "type-flash": "1",
            "type-story": "1",
            "type-photo": "1",
            "type-poetry": "1",
            "mode": "extended",
            "one": "on"
        }
        page_parsed: BeautifulSoup = self.get_parsed(
            "search",
            **options)
        info_parsed: dict[str, Any] = parse_tag_search(page_parsed)

        submissions = [SubmissionPartial(FAAPI, SubmissionPartial.Record(**parse_submission_figure(tag))) for tag in info_parsed["figures"]]

        return (submissions, (page + 1) if not info_parsed["last_page"] else None, [])

    def journals(self, user: str, page: Any = 1) -> tuple[list[JournalPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's journals page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of Journal objects and the next page (None if it is the last).
        """
        if page == None:
            page = 1
        page_parsed: BeautifulSoup = self.get_parsed(join_url("journals", quote(username_url(user)), int(page)))
        info_parsed: dict[str, Any] = parse_user_journals(page_parsed)
        author: UserPartial = UserPartial(FAAPI)
        author.name, author.status, author.title, author.join_date, author.avatar_url = [
            info_parsed["name"], info_parsed["status"],
            info_parsed["title"], info_parsed["join_date"],
            info_parsed["avatar_url"]
        ]
        journals = [
            JournalPartial(FAAPI, JournalPartial.Record(**parse_journal_section(tag)))
                for tag in info_parsed["sections"]]
        for j in journals:
            j.author = author
        return (journals, (page + 1) if not info_parsed["last_page"] else None, [])

    def watchlist_to(self, user: str, page: Any = None) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watching the user.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        page = page or 1
        users: list[UserPartial] = []
        us, np = parse_watchlist(
            self.get_parsed(join_url("watchlist", "to", quote(username_url(user)), page), skip_auth_check=True))
        for s, u in us:
            _user: UserPartial = UserPartial(FAAPI)
            _user.name = u
            _user.status = s
            users.append(_user)
        return (users, np if np and np != page else None, [])

    def watchlist_by(self, user: str, page: Any = None) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watched by the user.
        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        page = page or 1
        users: list[UserPartial] = []
        us, np = parse_watchlist(
            self.get_parsed(join_url("watchlist", "by", quote(username_url(user)), page), skip_auth_check=True))
        for s, u in us:
            _user: UserPartial = UserPartial(FAAPI)
            _user.name = u
            _user.status = s
            users.append(_user)
        return (users, np if np and np != page else None, [])

    def parse_loggedin_user(self, page: BeautifulSoup) -> Optional[str]:
        return parse_loggedin_user(page)

    def check_page_raise(self, page: BeautifulSoup) -> None:
        check_page_raise(page)

    @staticmethod
    def html_to_bbcode(html: str) -> str:
        return html_to_bbcode(str)

    @staticmethod
    def username_url(username: str) -> str:
        return username_url(username)
