from bs4 import BeautifulSoup
from bs4.element import Tag
from htmlmin import minify  # type:ignore
from datetime import datetime
from re import MULTILINE
from re import Match
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
from typing import Any
from typing import Optional
from typing import Union

def parse_html_page(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "lxml")

