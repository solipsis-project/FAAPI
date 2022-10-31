from http.cookiejar import CookieJar
from time import sleep
from time import time
from typing import Union

from .connection import CookieDict
from .connection import Response
from .connection import get
from .connection import make_session
from .connection import stream_binary
from .exceptions import DisallowedPath
from .exceptions import Unauthorized
from .parse import BeautifulSoup
from .parse import check_page_raise
from .parse import parse_loggedin_user
from .parse import parse_page
from .submission import Submission
from .abc import FAAPI_ABC

class FAAPI_BASE(FAAPI_ABC):

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
        if not (allowed := self.robots.can_fetch(self.user_agent, "/" + path.lstrip("/"))) and raise_for_disallowed:
            raise DisallowedPath(f"Path {path!r} is not allowed by robots.txt")
        return allowed

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

    def get(self, path: str, **params: Union[str, bytes, int, float]) -> Response:
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
        return get(self.session, self.root, path, timeout=self.timeout, params=params)

    def get_parsed(self, path: str, *, skip_page_check: bool = False, skip_auth_check: bool = False,
                   **params: Union[str, bytes, int, float]) -> BeautifulSoup:
        """
        Fetch a path with a GET request and parse it using BeautifulSoup.

        :param path: The path to fetch.
        :param skip_page_check: Whether to skip checking the parsed page for errors.
        :param skip_auth_check: Whether to skip checking the parsed page for login status.
        :param params: Query parameters for the request.
        :return: A BeautifulSoup object containing the parsed content of the request response.
        """
        response: Response = self.get(path, **params)
        response.raise_for_status()
        page: BeautifulSoup = parse_page(response.text)
        if not skip_page_check:
            check_page_raise(page)
        if not skip_auth_check and self.raise_for_unauthorized and not parse_loggedin_user(page):
            raise Unauthorized("Not logged in")
        return page

    def submission_file(self, submission: Submission, *, chunk_size: int = None) -> bytes:
        """
        Fetch a submission file from a Submission object.

        :param submission: A Submission object.
        :param chunk_size: The chunk_size to be used for the download.
        :return: The submission file as a bytes object.
        """
        self.handle_delay()
        return stream_binary(self.session, submission.file_url, chunk_size=chunk_size, timeout=self.timeout)
