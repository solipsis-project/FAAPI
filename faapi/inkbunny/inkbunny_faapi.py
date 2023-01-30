from datetime import datetime, timezone
import functools
from http.cookiejar import Cookie, CookieJar
import re
from re import sub
from time import sleep
from time import time
from typing import Any, Dict, List, Tuple, Type
from typing import Optional
from typing import Union
from urllib.robotparser import RobotFileParser
from xmlrpc.client import Boolean
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from urllib.parse import quote

from faapi.base import FAAPI_BASE

from ..connection import CloudflareScraper
from ..connection import CookieDict
from ..connection import Response
from ..connection import get_robots
from ..connection import make_session
from ..exceptions import DisallowedPath, NonePage, ParsingError, ServerError
from ..exceptions import Unauthorized
from ..journal import Journal, JournalStats
from ..journal import JournalPartial
from ..submission import Submission, SubmissionUserFolder
from ..submission import SubmissionPartial
from ..user import User, UserStats
from ..user import UserPartial
from . import inkbunny_parser

def convertRating(rating: str) -> str:
    match rating:
        case "General":
            return "General"
        case "Mature":
            return "Mature"
        case "Adult":
            return "Explicit"
    raise Exception(f"Unknown rating {rating}")

def convertType(type: str) -> str:
    match type:
        case "Comic" | "Picture/Pinup":
            return "image"
        case "Writing - Document":
            return "text"
        case "swf":
            return "flash"
        case "mp3":
            return "music"
    raise Exception(f"Unknown submission type {type}")

# The InkBunny API doesn't use cookies. Instead the session id is passed as a query param.
# For now, we will reuse the `$0 config cookies` feature but extract the sid from the cookies.
def getCookie(cookies: Union[list[CookieDict], CookieJar], name: str):
    for cookie in cookies:
        if isinstance(cookie, Cookie):
            if cookie.name == name:
                return cookie.value
        else:
            if cookie["name"] == name:
                return cookie["value"]

# Long term: download every resolution (or make it configurable). For now, download the best resolution available

THUMBNAIL_PRIORITY = [
    "thumbnail_url_huge",
    "thumbnail_url_large",
    "thumbnail_url_medium",
    "thumbnail_url_huge_noncustom",
    "thumbnail_url_large_noncustom",
    "thumbnail_url_medium_noncustom"
]

FILE_PRIORITY = [
    "file_url_full",
    "file_url_screen",
    "file_url_preview"
]

USER_ICON_PRIORITY = [
    "user_icon_url_large",
    "user_icon_url_medium",
    "user_icon_url_small",
]

def getFirst(d, keys):
    for key in keys:
        if key in d:
            return d[key]
    return None

class InkBunnyFAAPI(FAAPI_BASE):
    """
    This class provides the methods to access and parse Fur Affinity pages and retrieve objects.
    """
    @staticmethod
    def root() -> str:
        return "https://inkbunny.net/"

    def __init__(self, cookies: Union[list[CookieDict], CookieJar]):
        """
        :param cookies: The cookies for the session.
        """

        self.sid: str = getCookie(cookies, "sid")

        self.session: CloudflareScraper = make_session(cookies)
        self.api_session: CloudflareScraper = make_session(cookies=[])  # Session used for get requests
        
        super().__init__(
            robots = get_robots(self.session, self.root()),  # robots.txt handler
            timeout = None,  # Timeout for requests
            raise_for_unauthorized = True  # Control login checks
        )
        
        self.last_get: float = time() - self.crawl_delay  # Time of last get (UNIX time)

    def get_json(self, path: str, *, skip_auth_check: bool = False,
                   **params: Union[str, bytes, int, float]) -> Any:
        """
        Fetch a path with a GET request and parse it as JSON.

        :param path: The path to fetch.
        :param skip_page_check: Whether to skip checking the parsed page for errors.
        :param skip_auth_check: Whether to skip checking the parsed page for login status.
        :param params: Query parameters for the request.
        :return: A BeautifulSoup object containing the parsed content of the request response.
        """
        response: Response = self.get(path, **params)
        if not skip_auth_check and self.raise_for_unauthorized and response.status_code == 401:
            raise Unauthorized("Not logged in")
        if response.status_code != 401:
            response.raise_for_status()

        response_json = response.json()
        if "error_code" in response_json:
            raise ServerError(f"API response returned error: {response_json['error_message']}")
        return response_json
    
   
    @property
    def login_status(self) -> bool:
        """
        Check the login status of the given sid.

        :return: True if the cookies belong to a login session, False otherwise.
        """
        return self.my_username() is not None
    
    def my_username(self) -> Optional[str]:
        """
        Fetch the username of the logged-in user.

        :return: A string for the logged-in user, or None if the cookies are not from a login session.
        """
        response = self.get_parsed("/")

        return self.parse_loggedin_user(response)

    def me(self) -> Optional[User]:
        """
        Fetch the information of the logged-in user.

        :return: A User object for the logged-in user, or None if the cookies are not from a login session.
        """
        
        username: Optional[str] = self.my_username()

        return self.user(username) if username else None

    def frontpage(self) -> list[SubmissionPartial]:
        """
        Fetch latest submissions from Weasyl's front page

        :return: A list of SubmissionPartial objects
        """
        raise NotImplementedError

    def submission(self, submission_id: int, get_file: bool = False, *, chunk_size: int = None
                   ) -> tuple[Submission, Optional[bytes]]:
        """
        Fetch a submission and, optionally, its file.

        :param submission_id: The ID of the submission.
        :param get_file: Whether to download the submission file.
        :param chunk_size: The chunk_size to be used for the download (does not override get_file).
        :return: A Submission object and a bytes object (if the submission file is downloaded).
        """
        response: Any = self.get_json(f"/api_submissions.php", sid = self.sid, submission_ids = str(submission_id), show_description_bbcode_parsed = "yes", show_pools = "yes")

        assert len(response["submissions"]) == 1

        submission = response["submissions"][0]
        assert int(submission["submission_id"]) == submission_id

        sub: Submission = Submission(
            InkBunnyFAAPI,
            Submission.Record(
                id = int(submission["submission_id"]),
                title = submission["title"],
                author = submission["username"],
                rating = convertRating(submission["rating_name"]),
                type = convertType(submission["type_name"]),
                thumbnail_url = getFirst(submission, THUMBNAIL_PRIORITY),
                author_title = "",
                author_icon_url = getFirst(submission, USER_ICON_PRIORITY),
                date = parse_date(submission["create_datetime"]),
                tags = sorted([ keyword["keyword_name"] for keyword in submission["keywords"]]),
                category = "",
                species = "",
                gender = "",
                views = int(submission["views"]),
                comment_count = int(submission["comments_count"]),
                favorites = int(submission["favorites_count"]),
                description = submission["description_bbcode_parsed"],
                footer = "",
                mentions = [],
                folder = "gallery" if (submission["scraps"] == "f") else "scraps",
                user_folders = [SubmissionUserFolder(pool["name"], f"{self.root()}poolview_process.php?pool_id={pool['pool_id']}", "") for pool in submission["pools"]],
                file_url = getFirst(submission, USER_ICON_PRIORITY),
                prev = 0,
                next = 0,
                favorite = submission["favorite"],
                favorite_toggle_link = "",
            )
        )
                
        sub_file: Optional[bytes] = self.submission_file(sub, chunk_size=chunk_size) if get_file and sub.id else None
        return sub, sub_file

    def journal(self, journal_id: int) -> Journal:
        """
        Fetch a journal.

        :param journal_id: The ID of the journal.
        :return: A Journal object.
        """
        raise NotImplementedError

    def user(self, user: str) -> User:
        """
        Fetch a user.

        :param user: The name of the user (_ characters are allowed).
        :return: A User object.
        """
        beautifulSoup, response = self.get_parsed(quote(self.username_url(user)), return_response=True)

        # If the user doesn't exist, the response will be a member search page.
        if response.url.startswith(f"{self.root()}usersviewall.php"):
            raise ServerError(f"User {user} does not exist.")

        return User(InkBunnyFAAPI, inkbunny_parser.parse_user_profile(user, beautifulSoup))

    def search(self, params: Dict[str, str], page: Optional[Tuple[str, int]]):
        if page != None:
            return self.get_json(f"/api_search.php", sid = self.sid, rid = page[0], page = page[1])
        else:
            return self.get_json(f"/api_search.php", sid = self.sid, get_rid = "yes", submissions_per_page = "100", **params)

    def gallery(self, user: str, page: Optional[Tuple[str, int]] = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's gallery page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        response = self.search({"username": user, "scraps": "no"}, page)

        return self.parse_folder(response)

    def scraps(self, user: str, page: Optional[Tuple[str, int]] = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's scraps page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        response = self.search({"username": user, "scraps": "only"}, page)

        return self.parse_folder(response)
      
            
    def parse_folder(self, response: Any):
        submissions = [SubmissionPartial(InkBunnyFAAPI, SubmissionPartial.Record(
            id = int(s["submission_id"]),
            title = s["title"],
            rating = convertRating(s["rating_name"]),
            type = convertType(s["type_name"]),
            thumbnail_url = getFirst(s, THUMBNAIL_PRIORITY),
            author = s["username"]
        )) for s in response["submissions"]]

        if response["page"] == response["pages_count"]:
            return (submissions, None, [])
        
        next_page_number: int = int(response["page"]) + 1
        
        return (submissions, (response["rid"], next_page_number), [])


    def favorites(self, user: str, page: Any = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's favorites page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        raise NotImplementedError

    def journals(self, user: str, page: Any = 1) -> tuple[list[JournalPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's journals page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of Journal objects and the next page (None if it is the last).
        """
        raise NotImplementedError
        
    def watchlist_to(self, user: str, page: Any = 1) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watching the user.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        raise NotImplementedError

    def watchlist_by(self, user: str, page: Any = 1) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watched by the user.
        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        if user != self.my_username():
            raise NotImplementedError

        response = self.get_json(f"/api_watchlist.php", sid = self.sid)
        
        followers = [UserPartial(InkBunnyFAAPI, UserPartial.Record(
            name = watch["username"],
            status = "",
            title = "",
            join_date = datetime.fromtimestamp(0, tz = tzutc()),
            user_icon_url = ""
        )) for watch in response["watches"]]

        return (followers, None, [])

    def check_page_raise(self, page: BeautifulSoup) -> None:
        # Weasyl returns a non-200 status code on failure.
        if page is None:
            raise NonePage

    @staticmethod
    def html_to_bbcode(html: str) -> str:
        raise NotImplementedError

    @staticmethod
    def username_url(username: str) -> str:
        return sub(r"[^a-z\d.~`-]", "", username.lower())

    def parse_loggedin_user(self, bs: BeautifulSoup) -> Optional[str]:
        username_tag = bs.select_one("#usernavigation .loggedin_userdetails a.widget_userNameSmall")
        if not username_tag:
            return None

        return username_tag.text