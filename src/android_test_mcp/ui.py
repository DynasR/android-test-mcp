"""Reading the screen from the view hierarchy, and choosing a tap target.

Lock 4 lives here: a tap must land on ONE element the agent named.

- Coordinates are never the agent's: `adb shell input tap x y` cannot fail,
  it taps whatever is there. The target is looked up in the hierarchy
  (`uiautomator dump`), and absent means error.
- Flutter writes labels in `content-desc`, field hints in `hint`, and almost
  never in `text`. All three are matched, or Flutter screens look empty.
- Several matches is an error listing the candidates, never "the first one":
  `contains="Back"` also matches "Backups", and the first node in tree order
  is often a plain label sitting above the real button.
"""
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal

from .errors import AmbiguousTarget, DeviceError, TargetNotFound

MAX_LABEL = 200
_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
# Attributes that describe what the user sees. Others (focus, index) change
# without the screen changing.
_VISIBLE = ("class", "text", "content-desc", "hint", "bounds", "checked", "selected", "enabled")

Match = Literal["exact", "contains"]


@dataclass(frozen=True)
class Node:
    text: str
    desc: str
    hint: str
    bounds: tuple[int, int, int, int]
    clickable: bool

    @property
    def labels(self) -> list[str]:
        return [label for label in (self.desc, self.text, self.hint) if label]

    @property
    def label(self) -> str:
        return self.labels[0] if self.labels else ""

    @property
    def centre(self) -> tuple[int, int]:
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    @property
    def has_area(self) -> bool:
        x1, y1, x2, y2 = self.bounds
        return x2 > x1 and y2 > y1

    def describe(self) -> dict:
        entry = {"label": self.label[:MAX_LABEL], "bounds": list(self.bounds), "clickable": self.clickable}
        if self.hint and self.hint != self.label:
            entry["hint"] = self.hint[:MAX_LABEL]
        return entry


@dataclass(frozen=True)
class Screen:
    nodes: tuple[Node, ...]
    signature: str


def parse_hierarchy(xml: str) -> Screen:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as error:
        raise DeviceError(f"The view hierarchy could not be read: {error}") from error
    nodes, visible = [], []
    for element in root.iter("node"):
        match = _BOUNDS.fullmatch(element.get("bounds") or "")
        bounds = tuple(map(int, match.groups())) if match else (0, 0, 0, 0)
        nodes.append(Node(text=element.get("text") or "", desc=element.get("content-desc") or "",
                          hint=element.get("hint") or "", bounds=bounds,
                          clickable=element.get("clickable") == "true"))
        visible.append("\x1f".join(element.get(name) or "" for name in _VISIBLE))
    signature = hashlib.sha256("\x1e".join(visible).encode("utf-8")).hexdigest()
    return Screen(tuple(nodes), signature)


def summarize(screen: Screen) -> dict:
    """What the agent sees: labelled nodes, and how many clickable nodes have
    no label at all (they exist, but cannot be tapped by name)."""
    labelled = [node.describe() for node in screen.nodes if node.label and node.has_area]
    unlabelled = sum(1 for node in screen.nodes if node.clickable and not node.label and node.has_area)
    return {"elements": labelled, "unlabelled_clickable": unlabelled}


def find_target(screen: Screen, label: str, match: Match = "exact") -> Node:
    if not label:
        raise TargetNotFound("An empty label matches nothing. Call ui_elements to see the labels.")
    if match == "exact":
        hits = [node for node in screen.nodes if label in node.labels]
    elif match == "contains":
        wanted = label.casefold()
        hits = [node for node in screen.nodes if any(wanted in text.casefold() for text in node.labels)]
    else:
        raise TargetNotFound(f"match must be 'exact' or 'contains', not {match!r}.")

    on_screen = [node for node in hits if node.has_area]
    if not on_screen:
        hidden = " It exists in the hierarchy but has no area on screen." if hits else ""
        raise TargetNotFound(f"No element labelled {label!r} ({match}) on screen.{hidden} "
                             "Call ui_elements to see what is there.")
    # The same element can be exposed by two nested nodes with the same box:
    # tapping either lands on the same pixel, so it is not a guess.
    distinct = {node.bounds: node for node in on_screen}
    if len(distinct) > 1:
        listed = "; ".join(f"{node.label[:60]!r} at {list(node.bounds)}" for node in distinct.values())
        raise AmbiguousTarget(f"{len(distinct)} elements match {label!r} ({match}): {listed}. "
                              "Use a more precise label, or match='exact'. Nothing was tapped.")
    clickable = [node for node in on_screen if node.clickable]
    return clickable[0] if clickable else on_screen[0]
