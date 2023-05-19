from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from http.cookiejar import CookieJar
from time import sleep
from time import time
from typing import Any
from typing import Optional
from typing import Union, Tuple
from urllib.robotparser import RobotFileParser

from localrepo_api.base import FAAPI_BASE
from localrepo_api.comment import Comment, sort_comments
from localrepo_api.parse import html_to_bbcode

from ..connection import CloudflareScraper
from ..connection import CookieDict
from ..connection import Response
from ..connection import get
from ..connection import get_robots
from ..connection import join_url
from ..connection import make_session
from ..connection import stream_binary
from ..exceptions import DisallowedPath, ParsingError
from ..exceptions import Unauthorized
from ..journal import Journal
from ..journal import JournalPartial
from .sofurry_parser import BeautifulSoup, parse_comment_tag, parse_comments, parse_journal_page, parse_journal_section, parse_submission_page, parse_user_page, parse_watchlist_page, username_url
from .sofurry_parser import check_page_raise
from .sofurry_parser import parse_loggedin_user
from .sofurry_parser import parse_submission_figures
from .sofurry_parser import parse_user_favorites
from .sofurry_parser import parse_user_journals
from .sofurry_parser import parse_user_submissions
from ..submission import Submission
from ..submission import SubmissionPartial
from ..user import User
from ..user import UserPartial
from . import sofurry_parser
from ..exceptions import _raise_exception

def getSubmissionType(soFurrySubmissionType: str) -> str:
    return {
        "stories": "text",
        "artwork": "image",
        "photos": "image",
        "music": "music"
    }[soFurrySubmissionType]

def createUrlFromPage(page: str) -> Tuple[str, str]:
    # We identify a page of a multi-page response by the URL that is used to retrieve that page.
    # It's a less-than-ideal situation, but doing anything else is cumbersome: the sytax for these URLs are capricious.
    # Multiple different subdomains, different endpoints and parameters depending on the subdomain, a user ID field that isn't easily scraped...

    # Doing it this way has its risks: we're making queries based on data scraped from untrusted pages, which is *potentially* a security issue depending on your attack model.
    # And these URLs can be either partial or total seemingly depending on the subdomain of the original page.
    # Reconstructing the full URL here is annoying, but attempting to model the actual endpoint logic would be even *more* annoying.

    if page.startswith("//"):
        rest = page[2:]
        pathIndex = rest.index('/')
        return ("https://" + rest[:pathIndex], rest[pathIndex:])
    if page.startswith("/"):
        return ("https://www.sofurry.com", page)


class SoFurryFAAPI(FAAPI_BASE):
    """
    This class provides the methods to access and parse Fur Affinity pages and retrieve objects.
    """
    @staticmethod
    def root() -> str:
        return "https://www.sofurry.com/"

    def __init__(self, cookies: Union[list[CookieDict], CookieJar]):
        """
        :param cookies: The cookies for the session.
        """

        self.session: CloudflareScraper = make_session(cookies)  # Session used for get requests
        
        super().__init__(
            robots = get_robots(self.session, "https://sofurry.com"),  # robots.txt handler
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
        return parse_loggedin_user(self.get_parsed("", skip_auth_check=True)) is not None

    def me(self) -> Optional[User]:
        """
        Fetch the information of the logged-in user.

        :return: A User object for the logged-in user, or None if the cookies are not from a login session.
        """
        return self.user(user) if (user := parse_loggedin_user(self.get_parsed(""))) else None

    def frontpage(self) -> list[SubmissionPartial]:
        """
        Fetch latest submissions from Fur Affinity's front page

        :return: A list of SubmissionPartial objects
        """
        raise NotImplementedError
        page_parsed: BeautifulSoup = self.get_parsed("/")
        submission_tags = parse_submission_figures(page_parsed)
        submissions: list[SubmissionPartial] = [SubmissionPartial(SoFurryFAAPI, SubmissionPartial.Record(**parse_submission_figure(f))) for f in submission_tags]
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
        sub: Submission = Submission(SoFurryFAAPI, Submission.Record(
            rating = None,
            author_title = "",
            species = "",
            gender = "",
            **parsed_submission))
        comments = [Comment(SoFurryFAAPI, Comment.Record(
            timestamp = datetime.fromtimestamp(0),
            user_title = "",
            edited = False,
            hidden = False,
            **parse_comment_tag(t)), sub) for t in parse_comments(beautiful_soup)]
        sub.comments = sort_comments(comments)
        sub_file: list[bytes] = self.submission_files(sub, chunk_size=chunk_size) if get_file and sub.id else []
        return sub, sub_file

    def journal(self, journal_id: int) -> Journal:
        """
        Fetch a journal.

        :param journal_id: The ID of the journal.
        :return: A Journal object.
        """
        url = join_url("view", int(journal_id))
        beautiful_soup = self.get_parsed(url)
        try:
            parsed = Journal.Record(
                user_status="",
                user_title="",
                user_join_date=datetime.fromtimestamp(0),
                header="",
                footer="",
                mentions=[],
                **parse_journal_page(beautiful_soup))
            journal = Journal(SoFurryFAAPI, parsed)
            comments = [Comment(SoFurryFAAPI, Comment.Record(
                timestamp=datetime.fromtimestamp(0),
                user_title="",
                edited=False,
                hidden=False,
                **parse_comment_tag(t)), journal) for t in parse_comments(beautiful_soup)]
        except ParsingError as e:
            _raise_exception(ParsingError(f"Error while parsing {url}", *e.args))
        journal.comments = sort_comments(comments)
        return journal

    def user(self, user: str) -> User:
        """
        Fetch a user.

        :param user: The name of the user (_ characters are allowed).
        :return: A User object.
        """
        beautifulSoup = self.get_parsed("", root=f"https://{username_url(user)}.sofurry.com/", adult=1)
        parsed_user = parse_user_page(beautifulSoup)
        watch = parsed_user.pop("watch")
        unwatch = parsed_user.pop("unwatch")
        block = parsed_user.pop("block")
        unblock = parsed_user.pop("unblock")
        parsed_user["watched"] = watch is None and unwatch is not None
        parsed_user["watched_toggle_link"] = watch or unwatch or None
        parsed_user["blocked"] = block is None and unblock is not None
        parsed_user["blocked_toggle_link"] = block or unblock or None
        return User(SoFurryFAAPI, User.Record(status= "", **parsed_user))

    # noinspection DuplicatedCode
    def gallery(self, user: str, page: Any = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's gallery page.

        SoFurry has separate urls for each submission type:
        - Stories
        - Artwork
        - Photos
        - Music
        - Journals
        - Characters

        In addition, submissions that are in a folder won't show up on
        the main results page, so we need to return sub-urls.

        The page parameter here is a url. We could try to break it down into its components, by why would we?
        We'd just use them to reconstitute the url on a subsequent call.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        if page is None:
            # Return as subfolders the different submission types
            sub_folders = [ (submission_type, f"//{username_url(user)}.sofurry.com/{submission_type}") for submission_type in ["stories", "artwork", "photos", "music"]]

            return ([], None, sub_folders)

        root, path = createUrlFromPage(page[1])
        page_parsed: BeautifulSoup = self.get_parsed(path = path, root = root)
        info_parsed: dict[str, Any] = parse_user_submissions(page_parsed)
        author: UserPartial = UserPartial(SoFurryFAAPI)
        author.name, author.status, author.title, author.join_date, author.user_icon_url = [
            info_parsed["user_name"], "",
            info_parsed["user_title"], info_parsed["user_join_date"],
            info_parsed["user_icon_url"]
        ]
        submissions = [SubmissionPartial(SoFurryFAAPI, SubmissionPartial.Record(type=getSubmissionType(page[0]), **figure)) for figure in info_parsed["figures"]]
        for s in submissions:
            s.author = author

        # Every results page will contain the subfolders, but we want to make sure that we only parse each subfolder once, on the first page
        # of each category.
        
        sub_folders = [(page[0], subfolder["url"]) for subfolder in info_parsed["subfolders"]] if info_parsed["first_page"] else []
        return (submissions, (page[0], next_page) if (next_page := info_parsed["next_page"]) else None, sub_folders)

    # noinspection DuplicatedCode
    def scraps(self, user: str, page: Any = 1) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's scraps page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        # SoFurry doesn't have scraps
        return ([], None, [])


    def favorites(self, user: str, page: Any = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's favorites page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        # TODO: Unlike in FA, Favorites can include journals and characters. We don't currently scrape characters, and linking
        # to a favorited journal may not work correctly.

        if page is None:
            # Return as subfolders the different submission types
            sub_folders = [ (submission_type, f"//{username_url(user)}.sofurry.com/favorites?type={submission_type}") for submission_type in ["stories", "artwork", "photos", "music"]]

            return ([], None, sub_folders)

        root, path = createUrlFromPage(page[1])
        page_parsed: BeautifulSoup = self.get_parsed(path = path, root = root)
        info_parsed: dict[str, Any] = parse_user_favorites(page_parsed)
        submissions = [SubmissionPartial(SoFurryFAAPI, SubmissionPartial.Record(type=getSubmissionType(page[0]), **figure)) for figure in info_parsed["sections"]]
        return (submissions, (page[0], next_page) if (next_page := info_parsed["next_page"]) else None, [])

    def journals(self, user: str, page: Any = None) -> tuple[list[JournalPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's journals page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of Journal objects and the next page (None if it is the last).
        """
        if page:
            root, path = createUrlFromPage(page)
        else:
            root, path = f"https://{user}.sofurry.com", "journals"
        page_parsed: BeautifulSoup = self.get_parsed(path = path, root = root)
        info_parsed: dict[str, Any] = parse_user_journals(page_parsed)
        author: UserPartial = UserPartial(SoFurryFAAPI)
        author.name, author.title, author.join_date, author.user_icon_url = [
            info_parsed["user_name"],
            info_parsed["user_title"], info_parsed["user_join_date"],
            info_parsed["user_icon_url"]
        ]
        journals = [
            JournalPartial(SoFurryFAAPI, parse_journal_section(tag))
                for tag in info_parsed["sections"]]
        for j in journals:
            j.author = author
        return (journals, info_parsed["next_page"] or None, [])

    def watchlist_to(self, user: str, page: Any = None) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watching the user.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        if page:
            root, path = createUrlFromPage(page)
        else:
            root, path = f"https://{user}.sofurry.com", "watchers"
        watchers_soup = self.get_parsed(path = path, root = root)
        watchers = parse_watchlist_page(watchers_soup)
           
        users: list[UserPartial] = []
        for user in watchers["users"]:
            _user: UserPartial = UserPartial(SoFurryFAAPI)
            _user.name = watchers["user_name"]
            _user.user_icon_url = watchers["user_icon_url"]
            users.append(_user)
        return (users, watchers["next_page"], [])

    def watchlist_by(self, user: str, page: Any = None) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watched by the user.
        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        if page:
            root, path = createUrlFromPage(page)
        else:
            root, path = f"https://{user}.sofurry.com", "watching"
        watchers_soup = self.get_parsed(path = path, root = root)
        watchers = parse_watchlist_page(watchers_soup)
           
        users: list[UserPartial] = []
        for user in watchers["users"]:
            _user: UserPartial = UserPartial(SoFurryFAAPI)
            _user.name = user["user_name"]
            _user.user_icon_url = user["user_icon_url"]
            users.append(_user)
        return (users, watchers["next_page"], [])

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
