

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

def bbcode_to_html(bbcode: str) -> str:
    import faapi.furaffinity.furaffinity_parser
    return faapi.furaffinity.furaffinity_parser.bbcode_to_html(bbcode)

def html_to_bbcode(html: str) -> str:
    import faapi.furaffinity.furaffinity_parser
    return faapi.furaffinity.furaffinity_parser.html_to_bbcode(html)
    
def inner_html(tag: Tag) -> str:
    return tag.decode_contents()


def clean_html(html: str) -> str:
    return sub(r" *(<br/?>) *", r"\1", minify(html, remove_comments=True, reduce_boolean_attributes=True)).strip()
