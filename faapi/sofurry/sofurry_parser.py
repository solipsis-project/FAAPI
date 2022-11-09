from datetime import datetime
from re import MULTILINE
from re import Match
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
import re
from typing import Any
from typing import Optional
from typing import Union

from bbcode import Parser as BBCodeParser  # type:ignore
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from bs4.element import Tag
from dateutil.parser import parse as parse_date
from htmlmin import minify # type:ignore

from faapi.parse import parse_html_page  

from ..exceptions import DisabledAccount
from ..exceptions import NoTitle
from ..exceptions import NonePage
from ..exceptions import NotFound
from ..exceptions import NoticeMessage
from ..exceptions import ParsingError
from ..exceptions import ServerError
from ..exceptions import _raise_exception

from parse import clean_html, inner_html

root = "https://sofurry.com"

def getOnlyElement(l):
    if len(l) != 1:
        assert False
    return l[0]
        
def getOnlyElementOrNone(l):
    if len(l) == 0:
        return None
    if len(l) != 1:
        assert False
    return l[0]

def parse_user(author_tag: Tag) -> dict[str, Any]:

    tag_author_name: Optional[Tag] = author_tag.select_one("span.sf-username")
    tag_author_icon: Optional[Tag] = author_tag.select_one("img")

    assert tag_author_name is not None, _raise_exception(ParsingError("Missing author name tag"))
    assert tag_author_icon is not None, _raise_exception(ParsingError("Missing author icon tag"))

    author_name: str = tag_author_name.text.strip()
 
    author_icon_url: str = tag_author_icon.attrs["src"]

    return {
        "user": author_name,
        "user_icon_url": author_icon_url,
    }

def getStats(page: BeautifulSoup):
    statsHeader = page.find(class_="section-title", string="Stats")
    assert isinstance(statsHeader, Tag), _raise_exception(ParsingError("Missing Stats Header"))

    statsContent = statsHeader.find_next_sibling(class_="section-content")
    assert isinstance(statsContent, Tag), _raise_exception(ParsingError("Missing Stats Content"))
    stats = list(statsContent.strings)

    def parseStats(regexp: str, match_group = 1) -> str:
        reMatch = next(re.search(regexp, stat) for stat in stats)
        assert reMatch is not None, _raise_exception(ParsingError(f"Missing Stat {regexp}"))
        return reMatch[match_group]
    
    return parseStats


def parse_submission_page(sub_page: BeautifulSoup) -> dict[str, Any]:
    # Rating is not viewable from a submission page itself.
    [tag.unwrap() for tag in sub_page.find_all(name=["input", "form"])]

    idTag = sub_page.select_one('#sfPageId')
    assert idTag is not None, _raise_exception(ParsingError("Missing ID"))
    submitId = idTag.string
    
    imageTag = sub_page.select_one("[itemprop=image]")
    assert imageTag is not None
    imageSrc: Optional[str] = imageTag.attrs["src"]
    isImage: bool = "preview" in imageSrc
    hasImage: bool = imageTag.get("width") != "0px"
    
    if not hasImage:
        imageSrc = None
        
    titleTag = sub_page.select_one("#sfContentTitle")
    assert titleTag is not None, _raise_exception(ParsingError("Missing Title"))
    title = titleTag.string

    authorTag = sub_page.select_one("#sf-userinfo-outer")
    assert authorTag is not None, _raise_exception(ParsingError("Missing Artist"))

    tags: list[str] = [tag.string for tag in sub_page.find_all(id=re.compile("sftagbox-"))]

    artistDisplayNameTag = sub_page.select_one(".sf-username")
    assert artistDisplayNameTag is not None, _raise_exception(ParsingError("Missing Artist Display Name"))
    artistDisplayName = artistDisplayNameTag.string

    artistUserNameTag = sub_page.select_one(".sf-userinfo-outer")
    assert artistUserNameTag is not None, _raise_exception(ParsingError("Missing Artist User Name"))
    artistUserName = artistUserNameTag.attrs["href"][8:-13]

    seriesTitleTag = sub_page.select_one(".section-title-highlight")
    seriesTitle = seriesTitleTag and seriesTitleTag.string
    
    parseStats = getStats(sub_page)

    publishTimeStr = parseStats("Posted (.*)")
    # For some unkown reason, some pages add an extra space to these fields.
    #publishTimeStr = getOnlyElementOrNone([stat[8:] for stat in stats if stat[:8] == "\nPosted "])
    #publishTimeStr = publishTimeStr or getOnlyElement([stat[9:] for stat in stats if stat[:9] == "\n Posted "])

    publishTime: datetime = parse_date(publishTimeStr)

    views = int(parseStats("\\d+ views"))
    faves = int(parseStats("\\d+ faves"))
    commentCount = int(parseStats("\\d+ comments"))

    # viewsStr = getOnlyElementOrNone([stat[13:] for stat in stats if stat[:13] == "\nLast Edited "])
    
    seriesId = None
    seriesIdRe = re.compile("/browse/folder/stories?by=(.*?)&folder=(.*?)")
    def matchSeriesId(url: str) -> bool:
        match = seriesIdRe.match(url)
        if match:
            nonlocal seriesId
            seriesId = match[2]
            return True
        return False

    sub_page.find("a", href=matchSeriesId)

    descriptionTag = sub_page.select_one("#sfContentBody" if isImage else "#sfContentDescription")
    
    description = clean_html(inner_html(descriptionTag)) if descriptionTag else ""

    file_url = f"https://www.sofurryfiles.com/std/content?page={submitId}"

    unfaveButtonTag = sub_page.select_one("#sfFavorite_outer.yes")
    unfaveLink = unfaveButtonTag.get("href") if unfaveButtonTag else None

    faveButtonTag = None if unfaveButtonTag else sub_page.select_one("#sfFavorite_outer")
    faveLink = faveButtonTag.get("href") if faveButtonTag else None

    return {
        "id": submitId,
        "title": title,
        **parse_user(authorTag),
        "date": publishTime,
        "tags": tags,
        "views": views,
        "comment_count": commentCount,
        "favorites": faves,
        "type": "submission",
        "footer": "",
        "description": description,
        "mentions": [],
        "folder": seriesId,
        "user_folders": [],
        "file_url": file_url,
        "thumbnail_url": imageSrc,
        "prev": None,
        "next": None,
        "fav_link": faveLink,
        "unfav_link": unfaveLink,
    }


def parse_journal_page(journal_page: BeautifulSoup) -> dict[str, Any]:
    tag_id: Optional[Tag] = journal_page.select_one("meta[name='og:image']")
    tag_title: Optional[Tag] = journal_page.select_one("#sfContentTitle")
    tag_content: Optional[Tag] = journal_page.select_one("#sfContentBody")

    assert tag_id is not None, _raise_exception(ParsingError("Missing ID tag"))
    assert tag_title is not None, _raise_exception(ParsingError("Missing title tag"))
    assert tag_content is not None, _raise_exception(ParsingError("Missing content tag"))

    id_match = re.match("https://www.sofurryfiles.com/std/thumb?page=(.*?)&ext=.*", tag_id.attrs["content"]):
    assert id_match is not None, _raise_exception(ParsingError("Missing link tag"))
    id_ = int(id_match[1])
    
    # noinspection DuplicatedCode
    title: str = tag_title.text.strip()

    parseStats = getStats(journal_page)

    publishTimeStr = parseStats("Posted (.*)")
    publishTime: datetime = parse_date(publishTimeStr)
    
    content: str = clean_html(inner_html(tag_content))
    commentCount = int(parseStats("\\d+ comments"))

    assert id_ != 0, _raise_exception(ParsingError("Missing ID"))

    return {
        **parse_user(journal_page),
        "id": id_,
        "title": title,
        "date": publishTime,
        "content": content,
        "comments": commentCount,
    }

def parse_comments(page: BeautifulSoup) -> list[Tag]:
    return page.select("div.sfCommentOuter")

def parse_comment_tag(tag: Tag) -> dict:
    tag_id: Optional[Tag] = tag.select_one("a")
    tag_username: Optional[Tag] = tag.select_one("span.sf-comment-username a")
    tag_user_icon: Optional[Tag] = tag.select_one("img.sf-comments-avlarge")
    tag_body: Optional[Tag] = tag.select_one("div.sfCommentBodyContent")

    assert tag_id is not None, _raise_exception(ParsingError("Missing link tag"))
    assert tag_body is not None, _raise_exception(ParsingError("Missing body tag"))

    comment_id: Optional[str] = tag_id.attrs.get("name")
    assert comment_id is not None, _raise_exception(ParsingError("Missing comment id"))

    comment_text: str = clean_html(inner_html(tag_body))

    assert tag_username is not None, _raise_exception(ParsingError("Missing user name tag"))
    assert tag_user_icon is not None, _raise_exception(ParsingError("Missing user icon tag"))

    parent_id: Optional[int] = None

    parent_tag = tag.parent
    if parent_tag and (parent_class := parent_tag.attrs.get("class")) and parent_class == "sfCommentChildren":
        id_match = re.match("sfCommentChildren(\\d+)", parent_tag.attrs["id"])
        assert id_match is not None
        parent_id = int(id_match[1])

    attr_user_icon: Optional[str] = tag_user_icon.attrs.get("src")

    assert attr_user_icon is not None, _raise_exception(ParsingError("Missing user icon src attribute"))

    return {
        "id": int(comment_id),
        "user_name": tag_username.text.strip(),
        "user_icon_url": attr_user_icon,
        "text": comment_text,
        "parent": parent_id,
    }