from datetime import datetime
from optparse import Option
from re import MULTILINE
from re import Match
from re import Pattern
from re import compile as re_compile
from re import match
from re import search
from re import sub
import re
from typing import Any, Tuple, TypeVar
from typing import Optional
from typing import Union
from unicodedata import category

from bbcode import Parser as BBCodeParser  # type:ignore
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from bs4.element import Tag
from dateutil.parser import parse as parse_date
from htmlmin import minify
from localrepo_api.journal import JournalPartial # type:ignore

from localrepo_api.parse import parse_html_page
from localrepo_api.user import UserStats  

from ..exceptions import DisabledAccount
from ..exceptions import NoTitle
from ..exceptions import NonePage
from ..exceptions import NotFound
from ..exceptions import NoticeMessage
from ..exceptions import ParsingError
from ..exceptions import ServerError
from ..exceptions import _raise_exception

from localrepo_api.parse import clean_html, inner_html

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

def find(page: BeautifulSoup | Tag, regexe_exprs: dict[str, str], *args, **kwargs) -> Tuple[dict, Optional[Tag]]:
    matches = {}
    def generateMatcher(regex):
        def matcher(e: Optional[str]) -> bool:
            if e is None:
                return False
            nonlocal matches
            match = regex.match(e)
            if match:
                matches |= match.groupdict()
                return True
            matches = {}
            return False
        return matcher
    funcs = { key: generateMatcher(re.compile(regexe_exprs[key])) for key  in regexe_exprs }
    foundTag = page.find(*args, **kwargs, **funcs)
    assert (foundTag is None) or isinstance(foundTag, Tag)
    return matches, foundTag    

def parse_loggedin_user(page: BeautifulSoup) -> Optional[str]:
    a_tag = page.select_one("div.topbar-user a.avatar")
    if a_tag is None:
        return None

    matches, tag = find(page, {"href" : "https://(?P<username>.*?)\\.sofurry\\.com/"}, "a")
    return matches["username"]

def username_url(username: str) -> str:
    return sub(r"[^a-z\d.~`-]", "", username.lower())

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
    stats = list(s.strip() for s in statsContent.strings)
    def parseStats(regexp: str, match_group = 1) -> str:
        reMatches = (re.search(regexp, stat) for stat in stats)
        positiveMatches = (match for match in reMatches if match is not None)
        # Get first non-None match, or throw an exception.
        try:
            reMatch = next(positiveMatches)
            return reMatch[match_group]
        except StopIteration:
            _raise_exception(ParsingError(f"Missing Stat {regexp}"))
        
    
    return parseStats


def parse_submission_page(sub_page: BeautifulSoup) -> dict[str, Any]:
    # Rating is not viewable from a submission page itself.
    [tag.unwrap() for tag in sub_page.find_all(name=["input", "form"])]

    idTag = sub_page.select_one('#sfPageId')
    assert idTag is not None, _raise_exception(ParsingError("Missing ID"))
    submitId = int(idTag.string.strip())
    
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

    artistUserNameTag = sub_page.select_one("#sf-userinfo-outer")
    assert artistUserNameTag is not None, _raise_exception(ParsingError("Missing Artist User Name"))
    artistUserName = artistUserNameTag.attrs["href"][8:-13]

    seriesTitleTag = sub_page.select_one(".section-title-highlight")
    seriesTitle = seriesTitleTag and seriesTitleTag.string
    
    parseStats = getStats(sub_page)

    publishTimeStr = parseStats("Posted (.*)")

    publishTime: datetime = parse_date(publishTimeStr)

    views = int(parseStats("(\\d+) views?"))
    faves = int(parseStats("(\\d+) faves?"))
    commentCount = int(parseStats("(\\d+) comments?"))

    matches, linkTag = find(sub_page, {"href": "/browse/folder/stories\\?by=(?P<uid>.*?)&folder=(?P<folderid>.*?)"}, "a")
    folderId = None if (linkTag is None) else matches.get("folderid")

    descriptionTag = sub_page.select_one("#sfContentBody" if isImage else "#sfContentDescription")
    
    description = clean_html(inner_html(descriptionTag)) if descriptionTag else ""

    file_url = f"https://www.sofurryfiles.com/std/content?page={submitId}"

    unfaveButtonTag = sub_page.select_one("#sfFavorite_outer.yes")
    unfaveLink = unfaveButtonTag.get("href") if unfaveButtonTag else None

    faveButtonTag = None if unfaveButtonTag else sub_page.select_one("#sfFavorite_outer")
    faveLink = faveButtonTag.get("href") if faveButtonTag else None

    parsed_user = parse_user_small(authorTag)

    category =  "music" if sub_page.select_one("#sfContentMusic") is not None else\
                "image" if isImage else\
                "story"

    return {
        "id": int(submitId),
        "title": title,
        "author": parsed_user["user"],
        "author_icon_url": parsed_user["user_icon_url"],
        "date": publishTime,
        "tags": tags,
        "views": views,
        "category": category,
        "comment_count": commentCount,
        "favorites": faves,
        "type": category,
        "footer": "",
        "description": description,
        "mentions": [],
        "folder": folderId,
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
    
    id_match = re.match("https://www.sofurryfiles.com/std/thumb\\?page=(.*?)&ext=.*", tag_id.attrs["content"])
    assert id_match is not None, _raise_exception(ParsingError("Missing link tag"))
    id_ = int(id_match[1])
    
    # noinspection DuplicatedCode
    title: str = tag_title.text.strip()

    parseStats = getStats(journal_page)

    publishTimeStr = parseStats("Posted (.*)")
    publishTime: datetime = parse_date(publishTimeStr)
    
    content: str = clean_html(inner_html(tag_content))
    commentCount = int(parseStats("(\\d+) comments?"))

    assert id_ != 0, _raise_exception(ParsingError("Missing ID"))

    user = parse_user_small(journal_page)
    user_name = user.pop("user")
    return {
        "user_name": user_name,
        **user, 
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

def parse_next_page(page: BeautifulSoup | Tag) -> Optional[str]:
    next_page_tag = page.select_one("li.next")
    if next_page_tag is None:
        return None
    if "hidden" in next_page_tag.attrs["class"]:
        return None
    return next_page_link.attrs["href"] if (next_page_link := next_page_tag.a) else None

def parse_watchlist_page(page: BeautifulSoup) -> dict[str, Any]:
    user_tags = page.select("span.sf-item-h-info-content")
    users = []
    for user_tag in user_tags:
        user_name = getOnlyElement(list(user_tag.stripped_strings))
        user_icon_tag = get(user_tag.select_one("img"), "User Image")
        user_icon_url = user_icon_tag.attrs["src"]
        users.append({
            "user_name": user_name,
            "user_icon_url": user_icon_url
        })

    return {
        "users": users,
        "next_page": parse_next_page(page)
    }

def parse_user_page(user_page: BeautifulSoup) -> dict[str, Any]:

    tag_profile: Optional[Tag] = user_page.select_one("#sf-section-1 .sftc-content span span span")
    tag_stats: Optional[Tag] = user_page.select_one('[style="display: table; white-space: nowrap; font-size: smaller;"]')
    tag_contacts: Optional[Tag] = user_page.select_one("#sf-accounts")

    assert tag_stats is not None, _raise_exception(ParsingError("Missing stats tag"))
    assert tag_profile is not None, _raise_exception(ParsingError("Missing profile tag"))

    tag_watch: Optional[Tag] = user_page.select_one("form[action^='/watch'], form[action^='/unwatch']")
    tag_block: Optional[Tag] = user_page.select_one("form[action^='/block'], form[action^='/unblock']")


    profile: str = clean_html(inner_html(tag_profile))
    
    stats_scraped: dict[str, str] = {}
    info: dict[str, str] = {}

    for stat_row_tag in tag_stats.findChildren("span", recursive = False):
        category_tag = stat_row_tag.findChildren(class_ = "sfTextMedLight", recursive = False)[0]
        if category_tag.text.strip() == "groups":
            continue
        left_cell, right_cell = stat_row_tag.findChildren(recursive = False)
        if category_tag == left_cell:
            info[left_cell.text.strip()] = right_cell.text.strip()
        else: 
            stats_scraped[right_cell.text.strip()] = left_cell.text.strip() 

    def to_int(x: str) -> int:
        return int(x.replace(",", ""))

    watchers_tag = user_page.find(class_="wide-inactive", href=re.compile("https://(?P<username>.*)\\.sofurry\\.com/watchers"))
    assert isinstance(watchers_tag, Tag)
    watchers_span = watchers_tag.span
    assert isinstance(watchers_span, Tag)
    watchers = to_int(watchers_span.text.strip()[1:-1])

    watching_tag = user_page.find(class_="wide-inactive", href=re.compile("https://(?P<username>.*)\\.sofurry\\.com/watching"))
    assert isinstance(watching_tag, Tag)
    watching_span = watching_tag.span
    assert isinstance(watching_span, Tag)
    watching = to_int(watching_span.text.strip()[1:-1])

    stats = UserStats(
            views = to_int(stats_scraped["page views"]),
            submissions = to_int(stats_scraped["submissions"]),
            comments_earned = to_int(stats_scraped["comments received"]),
            comments_made = to_int(stats_scraped["comments posted"]),
            favorites = 0,
            journals = 0,
            watched_by = watchers,
            watching = watching
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

    parsed_user_tag = parse_user_big(user_page)
    return {
        "name": parsed_user_tag["user_name"],
        "user_icon_url": parsed_user_tag["user_icon_url"],
        "title": parsed_user_tag["user_title"],
        "join_date": parsed_user_tag["user_join_date"],
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


def parse_artwork_figures(figures_page: BeautifulSoup) -> list[Tag]:
    return figures_page.select(".sfBrowseListContent .sfArtworkSmallWrapper")

def parse_artwork_figure(figure: Tag) -> dict[str, Any]:
    inner_tag = figure.select_one(".sfArtworkSmallInner")
    data, imgTag = find(figure, { "id": "sfArtwork(?P<id>\\d+)", "alt": "(?P<title>.*)|by (?P<author>)", "src": "(?P<thumbnail_url>.*)" }, "img")
    if not "title" in data:
        # TODO: Get the title of the submission by querying it directly.
        raise ParsingError(f"Artwork figure {data['id']} has no title. This is a known issue that can happen when the title contains a quote character.")

    if "sf-boxshadow-extreme" in imgTag["class"]:
        data["rating"] = "extreme"
    elif "sf-boxshadow-adult" in imgTag["class"]:
        data["rating"] = "adult"
    else:
        assert "sf-boxshadow-default" in imgTag["class"]
        data["rating"] = "general"
    data["id"] = int(data["id"])
    return data

def parse_written_figures(figures_page: BeautifulSoup) -> list[Tag]:
    return figures_page.select(".sf-story, .sf-story-big")

def parse_written_figure(figure: Tag) -> dict[str, Any]:
    title_tag = figure.select_one(".sf-story-big-headline a") or figure.select_one(".sf-story-headline a")
    assert title_tag is not None, _raise_exception(ParsingError("Title not found"))
    title = title_tag.attrs["href"]
    id_string = figure.attrs["id"]
    id_match = re.match("\\D*(\\d+)", id_string)
    assert id_match is not None, _raise_exception(ParsingError("Figure id not found"))
    id_ = id_match[1]

    author_tag = figure.select_one(".sfTextAttention")
    assert author_tag is not None, _raise_exception(ParsingError("Author tag not found"))

    icon_tag = title_tag = figure.select_one(".sf-story-big-avatar img") or figure.select_one(".sf-story-avatar img")
    assert icon_tag is not None, _raise_exception(ParsingError("Story icon not found"))

    rating = "general"
    if "sf-boxshadow-extreme" in icon_tag["class"]:
        rating = "extreme"
    elif "sf-boxshadow-adult" in icon_tag["class"]:
        rating = "adult"
    else:
        assert "sf-boxshadow-default" in icon_tag["class"]

    return {
        "id": int(id_),
        "title": title,
        "author": author_tag.string,
        "thumbnail_url": icon_tag.attrs["src"],
        "rating": rating
    }

def parse_submission_figures(page: BeautifulSoup) -> list[dict[str, Any]]:
    return ([parse_written_figure(f) for f in parse_written_figures(page)] +
        [parse_artwork_figure(f) for f in parse_artwork_figures(page)])


def parse_subfolder(subfolder: Tag) -> dict[str, Any]:
    tag_a = get(subfolder.a, "subfolder link")
    return {
        "name": tag_a.attrs["title"].strip(),
        "url": tag_a.attrs["href"].strip()
    }

def parse_subfolders(page: BeautifulSoup) -> dict[str, Any]:
    subfolders = page.select(".sfBrowseListFolders .sfArtworkSmallWrapper")
    return {
        "subfolders": [parse_subfolder(subfolder) for subfolder in subfolders]
    }

def parse_user_submissions(submissions_page: BeautifulSoup) -> dict[str, Any]:
    last_page = not any(submissions_page.select("li.next"))
    first_page = not any(submissions_page.select("li.previous"))

    return {
        **parse_user_big(submissions_page),
        **parse_subfolders(submissions_page),
        "figures": parse_submission_figures(submissions_page),
        "first_page": first_page,
        "last_page": last_page,
        "next_page": parse_next_page(submissions_page)
    }

def parse_journal_section(section_tag: Tag) -> JournalPartial.Record:
    # journals on the journals page are formatted the same as written submissions
    data = parse_written_figure(section_tag)
    date_tag = section_tag.select_one("abbr")

    if date_tag is None:
        date_tag = section_tag.select_one(".sf-story-big-metadata strong span")
        date = parse_date(date_tag.string)
    else:
        date = parse_date(date_tag.attrs["title"])
    # Only the first journal on each page has a preview.
    content_tag = section_tag.select_one(".sf-story-big-content")

    assert date_tag is not None, _raise_exception(ParsingError("Missing date tag"))

    content = "" if content_tag is None else clean_html(inner_html(content_tag))

    return JournalPartial.Record(
        id = int(data["id"]),
        title = data["title"],
        comments = 0,
        date = date,
        content = content,
        mentions = [],
        user_name= data["author"],
        user_icon_url = data["thumbnail_url"]
    )


def parse_user_favorites(favorites_page: BeautifulSoup) -> dict[str, Any]:
    return {
        **parse_user_big(favorites_page),
        "sections": parse_submission_figures(favorites_page),
        "next_page": parse_next_page(favorites_page)
    }

def parse_user_journals(journals_page: BeautifulSoup) -> dict[str, Any]:
    return {
        **parse_user_big(journals_page),
        "sections": journals_page.select(".sf-story, .sf-story-big"),
        "next_page": parse_next_page(journals_page)
    }

def check_page_raise(page: BeautifulSoup) -> None:
    if page is None:
        raise NonePage
    """
    elif not (title := page.title.text.lower() if page.title else ""):
        raise NoTitle
    elif title.startswith("account disabled"):
        raise DisabledAccount
    elif title == "system error":
        error_text: str = error.text if (error := page.select_one("div.section-body")) else ""
        if any(m in error_text.lower() for m in not_found_messages):
            raise NotFound
        else:
            raise ServerError(*filter(bool, map(str.strip, error_text.splitlines())))
    elif notice := page.select_one("section.notice-message"):
        notice_text: str = notice.text
        if any(m in notice_text.lower() for m in deactivated_messages):
            raise DisabledAccount
        elif any(m in notice_text.lower() for m in not_found_messages):
            raise NotFound
        else:
            raise NoticeMessage(*filter(bool, map(str.strip, notice_text.splitlines())))
    """

