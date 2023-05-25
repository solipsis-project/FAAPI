from abc import abstractmethod
from http.cookiejar import CookieJar
from requests import Response
from time import sleep
from time import time
from typing import Optional, Union
from typing import Any
from typing import Optional
from typing import Union
from urllib.parse import quote
from urllib.robotparser import RobotFileParser


from .connection import CookieDict
from .connection import get
from .connection import make_session
from .connection import stream_binary
from .exceptions import DisallowedPath
from .exceptions import Unauthorized
from bs4 import BeautifulSoup
from .parse import parse_html_page
from .submission import Submission
from .interface.faapi_abc import FAAPI_ABC

def join_multipart_field(parts: list[str]):
    return "|" + "||".join(parts) + "|"

def parse_multipart_field(obj: str) -> list[str]:
    return obj.removeprefix("|").removesuffix("|").split("||")

class FAAPI_BASE(FAAPI_ABC):

    def __init__(self, robots: RobotFileParser, timeout: Optional[int], raise_for_unauthorized : bool):
        self.robots = robots
        self.timeout = timeout
        self.raise_for_unauthorized = raise_for_unauthorized

    @property
    def user_agent(self) -> str:
        """
        The user agent of the session
        """
        return self.session.headers["User-Agent"]

    @property
    def crawl_delay(self) -> float:
        """
        Crawl delay from robots.txt
        """
        return float(self.robots.crawl_delay(self.user_agent) or 1)

    def load_cookies(self, cookies: Union[list[CookieDict], CookieJar]):
        """
        Load new cookies and create a new session.

        :param cookies: The cookies for the session.
        """
        self.session = make_session(cookies)

    def handle_delay(self):
        """
        Handles the crawl delay as set in the robots.txt
        """
        if (d := time() - self.last_get) < self.crawl_delay:
            sleep(self.crawl_delay - d)
        self.last_get = time()

    def check_path(self, path: str, *, raise_for_disallowed: bool = False) -> bool:
        """
        Checks whether a given path is allowed by the robots.txt.

        :param path: The path to check.
        :param raise_for_disallowed: Whether to raise an exception for a non-allowed path.
        :return: True if the path is allowed in the robots.txt, False otherwise.
        """
        return True

    @property
    def connection_status(self) -> bool:
        """
        Check the status of the connection to Fur Affinity.

        :return: True if it can connect, False otherwise.
        """
        try:
            return self.get("/").ok
        except ConnectionError:
            return False

    def get(self, path: str, root: Optional[str] = None, **params: Union[str, bytes, int, float]) -> Response:
        """
        Fetch a path with a GET request.
        The path is checked against the robots.txt before the request is made.
        The crawl-delay setting is enforced wth a wait time.

        :param path: The path to fetch.
        :param params: Query parameters for the request.
        :return: A Response object from the request.
        """
        self.check_path(path, raise_for_disallowed=True)
        self.handle_delay()
        return get(self.session, root if root else self.root(), path, timeout=self.timeout, params=params)

    def get_parsed(self, path: str, *, root: Optional[str] = None, skip_page_check: bool = False, skip_auth_check: bool = False, output: dict[str,Response] | None = None,
                   **params: Union[str, bytes, int, float]) -> BeautifulSoup:
        """
        Fetch a path with a GET request and parse it using BeautifulSoup.

        :param path: The path to fetch.
        :param skip_page_check: Whether to skip checking the parsed page for errors.
        :param skip_auth_check: Whether to skip checking the parsed page for login status.
        :param params: Query parameters for the request.
        :return: A BeautifulSoup object containing the parsed content of the request response.
        """
        response: Response = self.get(path, root = root, **params)
        response.raise_for_status()
        page: BeautifulSoup = parse_html_page(response.text)
        if not skip_page_check:
            self.check_page_raise(page)
        if output is not None:
            output["response"] = response
        return page

    @abstractmethod
    def parse_loggedin_user(self, page: BeautifulSoup) -> Optional[str]:
        ...

    @abstractmethod
    def check_page_raise(self, page: BeautifulSoup) -> None:
        ...

    def submission_files(self, submission: Submission, *, chunk_size: Optional[int] = None) -> bytes:
        """
        Fetch a submission file from a Submission object.

        :param submission: A Submission object.
        :param chunk_size: The chunk_size to be used for the download.
        :return: The submission file as a bytes object.
        """
        def submission_file(file_url):
            self.handle_delay()
            return stream_binary(self.session, file_url, chunk_size=chunk_size, timeout=self.timeout)
        return [submission_file(file_url) for file_url in parse_multipart_field(submission.file_url)]
