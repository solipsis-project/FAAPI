from __future__ import annotations

from abc import ABC, abstractmethod
from http.cookiejar import CookieJar
from typing import Any
from typing import Optional
from typing import Union

from ..connection import CookieDict
from ..connection import Response
from ..parse import BeautifulSoup

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..submission import Submission
    from ..submission import SubmissionPartial
    from ..user import User
    from ..user import UserPartial
    from ..journal import Journal
    from ..journal import JournalPartial

# noinspection GrazieInspection
class FAAPI_ABC(ABC):
    """
    This class provides the methods to access and parse Fur Affinity pages and retrieve objects.
    """

    @staticmethod
    @abstractmethod
    def root(self) -> str:
        """
        The root URL for the backend server
        """

    @staticmethod
    @abstractmethod
    def parser(self):
        """
        The module containing all the parser methods.
        """

    @property
    @abstractmethod
    def user_agent(self) -> str:
        """
        The user agent of the session
        """

    @property
    @abstractmethod
    def crawl_delay(self) -> float:
        """
        Crawl delay from robots.txt
        """

    @abstractmethod
    def load_cookies(self, cookies: Union[list[CookieDict], CookieJar]):
        """
        Load new cookies and create a new session.

        :param cookies: The cookies for the session.
        """

    @abstractmethod
    def handle_delay(self):
        """
        Handles the crawl delay as set in the robots.txt
        """

    @abstractmethod
    def check_path(self, path: str, *, raise_for_disallowed: bool = False) -> bool:
        """
        Checks whether a given path is allowed by the robots.txt.

        :param path: The path to check.
        :param raise_for_disallowed: Whether to raise an exception for a non-allowed path.
        :return: True if the path is allowed in the robots.txt, False otherwise.
        """

    @property
    @abstractmethod
    def connection_status(self) -> bool:
        """
        Check the status of the connection to Fur Affinity.

        :return: True if it can connect, False otherwise.
        """

    @property
    @abstractmethod
    def login_status(self) -> bool:
        """
        Check the login status of the given cookies.

        :return: True if the cookies belong to a login session, False otherwise.
        """

    @abstractmethod
    def get(self, path: str, **params: Union[str, bytes, int, float]) -> Response:
        """
        Fetch a path with a GET request.
        The path is checked against the robots.txt before the request is made.
        The crawl-delay setting is enforced wth a wait time.

        :param path: The path to fetch.
        :param params: Query parameters for the request.
        :return: A Response object from the request.
        """

    @abstractmethod
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

    @abstractmethod
    def me(self) -> Optional[User]:
        """
        Fetch the information of the logged-in user.

        :return: A User object for the logged-in user, or None if the cookies are not from a login session.
        """

    @abstractmethod
    def frontpage(self) -> list[SubmissionPartial]:
        """
        Fetch latest submissions from Fur Affinity's front page

        :return: A list of SubmissionPartial objects
        """

    @abstractmethod
    def submission(self, submission_id: int, get_file: bool = False, *, chunk_size: int = None
                   ) -> tuple[Submission, Optional[bytes]]:
        """
        Fetch a submission and, optionally, its file.

        :param submission_id: The ID of the submission.
        :param get_file: Whether to download the submission file.
        :param chunk_size: The chunk_size to be used for the download (does not override get_file).
        :return: A Submission object and a bytes object (if the submission file is downloaded).
        """

    @abstractmethod
    def submission_file(self, submission: Submission, *, chunk_size: int = None) -> bytes:
        """
        Fetch a submission file from a Submission object.

        :param submission: A Submission object.
        :param chunk_size: The chunk_size to be used for the download.
        :return: The submission file as a bytes object.
        """

    @abstractmethod
    def journal(self, journal_id: int) -> Journal:
        """
        Fetch a journal.

        :param journal_id: The ID of the journal.
        :return: A Journal object.
        """

    @abstractmethod
    def user(self, user: str) -> User:
        """
        Fetch a user.

        :param user: The name of the user (_ characters are allowed).
        :return: A User object.
        """

    @abstractmethod
    def gallery(self, user: str, page: Any) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's gallery page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """

    @abstractmethod
    def scraps(self, user: str, page: Any) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's scraps page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """

    @abstractmethod
    def favorites(self, user: str, page: Any) -> tuple[list[SubmissionPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's favorites page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of SubmissionPartial objects and the next page (None if it is the last).
        """

    @abstractmethod
    def journals(self, user: str, page: Any) -> tuple[list[JournalPartial], Optional[Any], list[Any]]:
        """
        Fetch a user's journals page.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of Journal objects and the next page (None if it is the last).
        """

    @abstractmethod
    def watchlist_to(self, user: str, page: Any) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watching the user.

        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """

    @abstractmethod
    def watchlist_by(self, user: str, page: Any) -> tuple[list[UserPartial], Optional[Any], list[Any]]:
        """
        Fetch a page from the list of users watched by the user.
        :param user: The name of the user (_ characters are allowed).
        :param page: The page to fetch.
        :return: A list of UserPartial objects and the next page (None if it is the last).
        """
