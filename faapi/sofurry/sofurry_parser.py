from datetime import datetime
from re import MULTILINE
from re import Match
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
import re
from typing import Any, TypeVar
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

T = TypeVar('T') 

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

def get(e: Optional[T], message: str) -> T:
    assert e is not None, _raise_exception(ParsingError(f"Missing {message}"))
    return e

def parse_user_small(author_tag: Tag) -> dict[str, Any]:

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

    publishTime: datetime = parse_date(publishTimeStr)

    views = int(parseStats("\\d+ views"))
    faves = int(parseStats("\\d+ faves"))
    commentCount = int(parseStats("\\d+ comments"))
    
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
        **parse_user_small(authorTag),
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
        **parse_user_small(journal_page),
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

def parse_watchlist_page(page: BeautifulSoup) -> dict[str, Any]:
    user_tags = page.select("span.sf-item-h-info-content")
    users = []
    for user_tag in user_tags:
        user_name = getOnlyElement(user_tag.stripped_strings)
        user_icon_tag = get(user_tag.select_one("img"), "User Image")
        user_icon_url = user_icon_tag.attrs["href"]
        users.append({
            "user_name": user_name,
            "user_icon_url": user_icon_url
        })
    next_page_tag = page.select_one("li.next")
    next_page = next_page_link.attrs["href"] if next_page_tag and (next_page_link := next_page_tag.a) else None

    return {
        "users": users,
        "next_page": next_page
    }

def parse_user_page(user_page: BeautifulSoup) -> dict[str, Any]:

    tag_profile: Optional[Tag] = user_page.select_one("#sf-section-1 sftc-content span span span")
    tag_stats: Optional[Tag] = user_page.select_one('[style="display: table; white-space: nowrap; font-size: smaller;"]')
    tag_contacts: Optional[Tag] = user_page.select_one("#sf-accounts")
    
    tag_stats: Optional[Tag] = user_page.select_one("div.userpage-section-right div.table")
    
    tag_user_nav_controls: Optional[Tag] = user_page.select_one("div.user-nav-controls")

    

    assert tag_stats is not None, _raise_exception(ParsingError("Missing stats tag"))
    assert tag_profile is not None, _raise_exception(ParsingError("Missing profile tag"))
    assert tag_stats is not None, _raise_exception(ParsingError("Missing stats tag"))
    assert tag_user_nav_controls is not None, _raise_exception(ParsingError("Missing user nav controls tag"))

    tag_watch: Optional[Tag] = tag_user_nav_controls.select_one("form[action^='/watch'], a[form[action^='/unwatch']")
    tag_block: Optional[Tag] = tag_user_nav_controls.select_one("form[action^='/block'], a[form[action^='/unblock']")


    profile: str = clean_html(inner_html(tag_profile))
    
    stats_scraped: dict[str, str] = {}
    info: dict[str, str] = {}

    for stat_row_tag in tag_stats.findChildren():
        category_tag = stat_row_tag.findChildren(class_ = "sfTextMedLight")
        left_cell, right_cell = stat_row_tag.findChildren()
        if category_tag == left_cell:
            info[left_cell.text.strip()] = right_cell.text.strip()
        else: 
            stats_scraped[right_cell.text.strip()] = left_cell.text.strip() 

    stats = UserStats(
            views = stats_scraped["page views"]
            submissions = stats_scraped["submissions"]
            comments_earned = stats_scrapped["comments received"]
            comments_made = stats_scrapped["comments posted"]
    )

    tag_key: Optional[Tag]
    
    contacts: dict[str, str] = {}
    if tag_contacts:
        for contact in tag_contacts.find_all(href=True):
            contacts[contact.text.strip()] = contact.attrs["href"]

    
    tag_watch_href: str = ("https://" + tag_watch.attrs["action"]) if tag_watch else ""
    watch: Optional[str] = f"{root}{tag_watch_href}" if tag_watch_href.endswith("/watch") else None
    unwatch: Optional[str] = f"{root}{tag_watch_href}" if tag_watch_href.endswith("/unwatch") else None
    tag_block_href: str = ("https://" + tag_block.attrs["action"]) if tag_block else ""
    block: Optional[str] = f"{root}{tag_block_href}" if tag_block_href.endswith("/block") else None
    unblock: Optional[str] = f"{root}{tag_block_href}" if tag_block_href.endswith("/unblock") else None

    return {
        **parse_user_big(user_page),
        "profile": profile,
        "stats": stats,
        "info": info,
        "contacts": contacts,
        "watch": watch,
        "unwatch": unwatch,
        "block": block,
        "unblock": unblock,
    }

def parse_user_big(user_tag: Tag) -> dict[str, Any]:

    tag_username: Optional[Tag] = user_tag.select_one(".user-text")
    tag_title: Optional[Tag] = user_tag.select_one(".user .sfTextMedLight")
    tag_title_join_date: Optional[Tag] = user_tag.select_one("span.user-stats strong")
    tag_user_icon_url: Optional[Tag] = user_tag.select_one(".user-info")
    
    assert tag_username is not None, _raise_exception(ParsingError("Missing name tag"))
    assert tag_title is not None, _raise_exception(ParsingError("Missing title tag"))
    assert tag_title_join_date is not None, _raise_exception(ParsingError("Missing join date tag"))
    assert tag_user_icon_url is not None, _raise_exception(ParsingError("Missing user icon URL tag"))

    user_icon_img_tag: Optional[Tag] = tag_user_icon_url.img
    assert user_icon_img_tag is not None, _raise_exception(ParsingError("Missing user icon tag"))
    user_icon_url = user_icon_img_tag.attrs["src"]

    name: str = tag_username.text.strip()
    title: str = tag_title.text.strip()
    join_date: datetime = parse_date(tag_title_join_date.text.strip())
    

    return {
        "user_name": name,
        "user_title": title,
        "user_join_date": join_date,
        "user_icon_url": user_icon_url
    }


def parse_submission_figures(figures_page: BeautifulSoup) -> list[Tag]:
    return figures_page.select(".sfArtworkSmallInner")

def parse_subfolder(subfolder: Tag) -> dict[str, Any]:
    tag_a = get(subfolder.a, "subfolder link")
    return {
        "name": tag_a.attrs["title"].strip(),
        "url": tag_a.attrs["href"].strip()
    }

def parse_subfolders(page: BeautifulSoup) -> dict[str, Any]:
    subfolders = page.select(".sfArtworkSmallWrapper")
    return {
        "subfolders": [parse_subfolder(subfolder) for subfolder in subfolders]
    }

def parse_user_submissions(submissions_page: BeautifulSoup) -> dict[str, Any]:
    last_page = not any(submissions_page.select(".next"))

    return {
        **parse_user_big(submissions_page),
        **parse_subfolders(submissions_page),
        "figures": parse_submission_figures(submissions_page),
        "last_page": last_page,
    }