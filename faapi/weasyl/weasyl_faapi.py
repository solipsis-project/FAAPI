from datetime import datetime, timezone
import functools
from http.cookiejar import CookieJar
import re
from re import sub
from time import sleep
from time import time
from typing import Any, Dict, List, Tuple, Type
from typing import Optional
from typing import Union
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date
from dateutil.tz import tzutc

from faapi.base import FAAPI_BASE

from ..connection import CloudflareScraper
from ..connection import CookieDict
from ..connection import Response
from ..connection import get_robots
from ..connection import make_session
from ..exceptions import DisallowedPath, NonePage, ParsingError
from ..exceptions import Unauthorized
from ..journal import Journal, JournalStats
from ..journal import JournalPartial
from ..submission import Submission, SubmissionUserFolder
from ..submission import SubmissionPartial
from ..user import User, UserStats
from ..user import UserPartial
from . import weasyl_parser

from .weasyl_parser import parse_submission_figure, parse_user_favorites, parse_user_folder

def convertRating(rating: str) -> str:
    match rating:
        case "general":
            return "General"
        case "mature":
            return "Mature"
        case "explicit":
            return "Explicit"

def computeTypeFromExtension(extension: str, submitid: int) -> str:
    match extension:
        case "jpg" | "gif" | "png":
            return "image"
        case "swf":
            return "flash"
        case "txt" | "md" | "pdf":
            return "text"
        case "mp3":
            return "music"
    raise Exception(f"Unknown file extension {extension} on submission {submitid}")


class WeasylFAAPI(FAAPI_BASE):
    """
    This class provides the methods to access and parse Fur Affinity pages and retrieve objects.
    """
    @staticmethod
    def root() -> str:
        return "https://www.weasyl.com/"

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

        return response.json()
    
    def get_loggedin_user(self, endpoint: str = "/api/whoami", **kwargs) -> Optional[str]:
        json = self.get_json(endpoint, **kwargs)
        match json:
            case {"login": name}:
                return name
            case _:
                return None
    
    @property
    def login_status(self) -> bool:
        """
        Check the login status of the given cookies.

        :return: True if the cookies belong to a login session, False otherwise.
        """
        return self.get_loggedin_user(skip_auth_check=True) is not None

    def me(self) -> Optional[User]:
        """
        Fetch the information of the logged-in user.

        :return: A User object for the logged-in user, or None if the cookies are not from a login session.
        """
        return self.user(user) if (user := self.get_loggedin_user()) else None

    def frontpage(self) -> list[SubmissionPartial]:
        """
        Fetch latest submissions from Weasyl's front page

        :return: A list of SubmissionPartial objects
        """
        frontpage_submissions = self.get_json("/api/submissions/frontpage")
        if type(frontpage_submissions) is not list:
            raise ParsingError("Unable to parse front page submissions")

        # The front page can be a mix of submissions and characters. Characters have a different format and are not currently supported, so they get ignored.
        submissions: list[SubmissionPartial] = [
            SubmissionPartial(WeasylFAAPI, SubmissionPartial.Record(
                id = f["submitid"],
                title = f["title"],
                author = f["owner"],
                rating = convertRating(f["rating"]),
                type = computeTypeFromExtension(f["media"]["thumbnail"][0]["url"].split(".")[-1], f["submitid"]),
                thumbnail_url = f["media"]["thumbnail"][0]["url"]))
            for f in frontpage_submissions if f["type"] == "submission"]
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
        response: Any = self.get_json(f"/api/submissions/{submission_id}/view")
        assert response["submitid"] == submission_id
        sub: Submission = Submission(
            WeasylFAAPI,
            Submission.Record(
                id = response["submitid"],
                title = response["title"],
                author = response["owner"],
                rating = convertRating(response["rating"]),
                type = computeTypeFromExtension(response["media"]["submission"][0]["url"].split(".")[-1], response["submitid"]),
                thumbnail_url = response["media"]["thumbnail-generated"][0]["url"],
                author_title = "",
                author_icon_url = response["owner_media"]["avatar"][0]["url"],
                date = parse_date(response["posted_at"]),
                tags = response["tags"],
                category = "",
                species = "",
                gender = "",
                views = response["views"],
                comment_count = response["comments"],
                favorites = response["favorites"],
                description = response["description"],
                footer = "",
                mentions = [],
                folder = "gallery",
                user_folders = [SubmissionUserFolder(response["folder_name"], f"{self.root()}submissions/{response['owner_login']}?folderid={response['folderid']}", "")],
                file_url = response["media"]["submission"][0]["url"],
                prev = 0,
                next = 0,
                favorite = response["favorited"],
                favorite_toggle_link = "",
            )
        )
                
        sub_file: list[bytes] = self.submission_file(sub, chunk_size=chunk_size) if get_file and sub.id else []
        return sub, sub_file

    def journal(self, journal_id: int) -> Journal:
        """
        Fetch a journal.

        :param journal_id: The ID of the journal.
        :return: A Journal object.
        """
        # Author join date isn't returned by the query. Use 0 time for now.
        # We can improve this with a second query.
        response: Any = self.get_json(f"/api/journals/{journal_id}/view")
        assert response["journalid"] == journal_id
        return Journal(WeasylFAAPI, Journal.Record(
            id = response["journalid"],
            title = response["title"],
            user_name = response["owner"],
            user_title = "",
            user_status = "",
            user_join_date = datetime.fromtimestamp(0, tz = tzutc()),
            user_icon_url = response["owner_media"]["avatar"][0]["url"],
            comments = response["comments"],
            date = parse_date(response["posted_at"]),
            content = response["content"],
            header = "",
            footer = "",
            mentions = [],
        ))

    def user(self, user: str) -> User:
        """
        Fetch a user.

        :param user: The name of the user (_ characters are allowed).
        :return: A User object.
        """
        def parseUserInfo(user_info: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
            contacts = user_info.pop("user_links")
            del user_info["sorted_user_links"]
            result: Dict[str, str] = {}
            for location in contacts:
                urls = contacts[location]
                if len(urls) == 1:
                    result[location] = urls[0]
                else:
                    for (i, url) in enumerate(urls):
                        result[f"{location} {i+1}"] = url
            return user_info, result

        response: Any = self.get_json(f"/api/users/{user}/view")
        assert response["username"] == user
        user_info, contact_info = parseUserInfo(response["user_info"])
        return User(WeasylFAAPI, User.Record(
            name = response["username"],
            status = response["catchphrase"],
            profile = response["profile_text"],
            title = response["full_name"],
            join_date = parse_date(response["created_at"]),
            stats = UserStats(
                views = response["statistics"]["page_views"],
                submissions = response["statistics"]["submissions"],
                favorites = response["statistics"]["faves_sent"],
                comments_earned = 0,
                comments_made = 0,
                journals = response["statistics"]["journals"],
                watched_by = response["statistics"]["followed"],
                watching = response["statistics"]["following"]
            ),
            info = user_info | response["commission_info"],
            contacts = contact_info,
            user_icon_url = response["media"]["avatar"][0]["url"],
            watched = response["relationship"]["follow"],
            watched_toggle_link = "",
            blocked = False,
            blocked_toggle_link = ""
        ))

    # noinspection DuplicatedCode
    def gallery(self, user: str, page: int | str | None = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's gallery page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        response: Any
        if page != None and page != 1:
            response = self.get_json(f"/api/users/{user}/gallery", nextid = page)
        else:
            print(f"/api/users/{user}/gallery")
            response = self.get_json(f"/api/users/{user}/gallery")
            
        author: UserPartial = UserPartial(WeasylFAAPI, UserPartial.Record(
            name = user,
            status = "",
            title = "",
            join_date = datetime.fromtimestamp(0, tz = tzutc()),
            user_icon_url = ""
        ))
        submissions = [SubmissionPartial(WeasylFAAPI, SubmissionPartial.Record(
            id = s["submitid"],
            title = s["title"],
            rating = convertRating(s["rating"]),
            type = computeTypeFromExtension(s["media"]["thumbnail"][0]["url"].split(".")[-1], s["submitid"]),
            thumbnail_url = s["media"]["thumbnail"][0]["url"]
        )) for s in response["submissions"]]
        for s in submissions:
            s.author = author
        return (submissions, response["nextid"], [])

    # noinspection DuplicatedCode
    def scraps(self, user: str, page: Any = 1) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's scraps page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        # Weasyl doesn't have scraps
        return ([], None, [])

    """
    @functools.cache
    def get_user_id(self, username: str) -> str:
        favorites_overview_page = self.get_parsed(f"~{username}")
        follow_tag = favorites_overview_page.select_one("input[name=userid]")
        assert follow_tag is not None
        return follow_tag.attrs["value"]
    """
        
    def favorites(self, user: str, page: Any = None) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's favorites page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """
        # Thwe Weasyl API doesn't support examining a user's favorites. We'll have to use traditional scraping here.
        # URL for favorites: https://www.weasyl.com/favorites?userid={id}&feature={submit|char|journal}&nextid={}
        # TODO: Support querying favorites.
        # TODO: Should this also return favorite journals / characters?
        # To query favorites, we need a user id, which we can get from the user page or the "favorites overview page"
        # By caching the result of the helper function, we only make the extra query once per artist.
        
        get_params = { "feature": "submit"} | ({"nextid": page} if page is not None else {})
        page_parsed: BeautifulSoup = self.get_parsed(f"favorites/{user}", **get_params)
        info_parsed: dict[str, Any] = parse_user_favorites(page_parsed)
        submissions = [SubmissionPartial(WeasylFAAPI, SubmissionPartial.Record(**parse_submission_figure(tag))) for tag in info_parsed["figures"]]
        return (submissions, info_parsed["next_page"] or None, [])

    def journals(self, user: str, page: Any = 1) -> tuple[list[JournalPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's journals page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of Journal objects and the next page (None if it is the last).
        """
        page_parsed: BeautifulSoup = self.get_parsed(f"journals/{user}")
        user_info = parse_user_folder(page_parsed)
        assert user_info["user_name"] == user
        journal_tags = page_parsed.select(".text-post-item")
        header_tags = page_parsed.select(".text-post-group-header")

        journals : List[JournalPartial] = []
        for (header, journal) in zip(header_tags, journal_tags):
            title_tag = journal.select_one(".text-post-title").a
            assert title_tag is not None
            excerpt_tag = journal.select_one(".text-post-excerpt")
            assert excerpt_tag is not None
            journals.append(JournalPartial(WeasylFAAPI, JournalPartial.Record(
            id = int(title_tag.attrs["href"].split("/")[2]),
            title = title_tag.text,
            comments = 0,
            date = parse_date(header.time.attrs["datetime"]),
            content = excerpt_tag.text,
            mentions = [],
            **user_info)))
        
        return (journals, None, [])
        
    def watchlist_to(self, user: str, page: Any = 1) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watching the user.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        page_parsed: BeautifulSoup = self.get_parsed(f"followed/{user}")
        follower_tags = page_parsed.select(".grid-unit")
        followers = [UserPartial(WeasylFAAPI, UserPartial.Record(
            name = tag.a.attrs["title"],
            status = "",
            title = "",
            join_date = datetime.fromtimestamp(0, tz = tzutc()),
            user_icon_url = tag.img.attrs["src"]
        )) for tag in follower_tags]
        
        next_page = None
        href_re = re.compile("/following\\?userid=.*&nextid=(.*)")
        def match_href(url: str):
            match = href_re.match(url)
            if match:
                nonlocal next_page
                next_page = match[1]
        page_parsed.find("a", href=match_href)
        return (followers, next_page, [])

    def watchlist_by(self, user: str, page: Any = 1) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watched by the user.
        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
        page_parsed: BeautifulSoup = self.get_parsed(f"following/{user}")
        follower_tags = page_parsed.select(".grid-unit")
        followers = [UserPartial(WeasylFAAPI, UserPartial.Record(
            name = tag.a.attrs["title"],
            status = "",
            title = "",
            join_date = datetime.fromtimestamp(0, tz = tzutc()),
            user_icon_url = tag.img.attrs["src"]
        )) for tag in follower_tags]

        next_page = None
        href_re = re.compile("/following\\?userid=.*&nextid=(.*)")
        def match_href(url: str):
            match = href_re.match(url)
            if match:
                nonlocal next_page
                next_page = match[1]
        page_parsed.find("a", href=match_href)
        return (followers, next_page, [])

    def parse_loggedin_user(self, page: BeautifulSoup) -> Optional[str]:
        username_tag = page.select_one("#username")
        return username_tag.text if username_tag else None

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