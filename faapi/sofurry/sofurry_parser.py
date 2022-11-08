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

root = "https://furaffinity.net"

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

def getContents(parent):
        return ''.join([str(e) for e in parent.children])

def parse_submission_page(sub_page: BeautifulSoup) -> dict[str, Any]:
    # Rating is not viewable from a submission page itself.
    [tag.unwrap() for tag in sub_page.find_all(name=["input", "form"])]

    idTag = sub_page.select_one('#sfPageId')
    assert artistDisplayNameTag is not None, _raise_exception(ParsingError("Missing ID"))
    submitId = idTag.string
    
    imageTag = sub_page.select_one("[itemprop=image]")
    assert imageTag is not None
    imageSrc: str = imageTag.get("src")
    isImage: bool = "preview" in imageSrc
    hasImage: bool = imageTag.get("width") != "0px"
    
    if not hasImage:
        imageSrc = None
        
    titleTag = sub_page.select_one("#sfContentTitle")
    assert titleTag is not None, _raise_exception(ParsingError("Missing Title"))
    title = titleTag.string

    authorTag = sub_page("#sf-userinfo-outer")
    assert authorTag is not None, _raise_exception(ParsingError("Missing Artist"))

    tags: list[str] = [tag.string for tag in sub_page.find_all(id=re.compile("sftagbox-"))]

    artistDisplayNameTag = sub_page.select_one(".sf-username")
    assert artistDisplayNameTag is not None, _raise_exception(ParsingError("Missing Artist Display Name"))
    artistDisplayName = artistDisplayNameTag.string

    artistUserNameTag = sub_page.select_one(".sf-userinfo-outer")
    assert artistUserNameTag is not None, _raise_exception(ParsingError("Missing Artist User Name"))
    artistUserName = artistUserNameTag.get("href")[8:-13]

    seriesTitleTag = sub_page.select_one(".section-title-highlight")
    seriesTitle = seriesTitleTag and seriesTitleTag.string
    
    stats = list(sub_page.find(class_="section-title", string="Stats").find_next_sibling(class_="section-content").strings)

    def parseStats(regexp: re.Pattern, match_group = 1):
        reMatch = next(regexp.search(stat) for stat in stats)
        return reMatch[match_group] if reMatch else None
            
    publishTimeStr = parseStats("Posted (.*)")
    # For some unkown reason, some pages add an extra space to these fields.
    #publishTimeStr = getOnlyElementOrNone([stat[8:] for stat in stats if stat[:8] == "\nPosted "])
    #publishTimeStr = publishTimeStr or getOnlyElement([stat[9:] for stat in stats if stat[:9] == "\n Posted "])
    publishTime: datetime = parse_date(publishTimeStr)

    lastEditedTimeStr = parseStats("Last Edited (.*)")

    #lastEditedTimeStr = getOnlyElementOrNone([stat[13:] for stat in stats if stat[:13] == "\nLast Edited "])
    #lastEditedTimeStr = lastEditedTimeStr or getOnlyElementOrNone([stat[14:] for stat in stats if stat[:14] == "\n Last Edited "])
    lastEditedTime: datetime = lastEditedTimeStr and parse_date(lastEditedTimeStr)

    views = int(parseStats("\d+ views"))
    faves = int(parseStats("\d+ faves"))
    commentCount = int(parseStats("\d+ comments"))

    # viewsStr = getOnlyElementOrNone([stat[13:] for stat in stats if stat[:13] == "\nLast Edited "])
    
    
    seriesId = None
    seriesIdRe = re.compile("/browse/folder/stories?by=(.*?)&folder=(.*?)")
    def matchSeriesId(url: str):
        match = seriesIdRe.match(url)
        if match:
            nonlocal seriesId
            seriesId = match[2]
    sub_page.find("a", href=matchSeriesId)

    descriptionTag = sub_page.select_one("#sfContentBody" if isImage else "#sfContentDescription")
    
    description = getContents(descriptionTag)

    file_url = f"https://www.sofurryfiles.com/std/content?page={submitId}"

    unfaveButtonTag = sub_page.select_one("#sfFavorite_outer.yes")
    unfaveLink = unfaveButtonTag.get("href") if unfaveButtonTag else None

    faveButtonTag = None if unfaveButtonTag else sub_page.select_one("#sfFavorite_outer")
    faveLink = faveButtonTag.get("href") if faveButtonTag else None

    return {
        "id": submitId,
        "title": title,
        **parse_submission_author(authorTag),
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