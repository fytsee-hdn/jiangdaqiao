"""
wecom_xml.py

WeCom (企业微信) XML message parser.

Parses WeCom callback XML into a plain dict compatible with
wecom_adapter.py.

Supported XML structures:
  - Text messages (<MsgType>text</MsgType>, <Content>...</Content>)
  - Image messages (<MsgType>image</MsgType>, <PicUrl>, <MediaId>)

Uses only Python stdlib xml.etree.ElementTree — no third-party libs.
CDATA sections are automatically unwrapped by the parser.
"""

import xml.etree.ElementTree as ET
from typing import Any


# ══════════════════════════════════════════════════════════════════
#  XML -> dict conversion
# ══════════════════════════════════════════════════════════════════


def parse_wecom_xml(xml_text: str) -> dict:
    """
    Parse WeCom callback XML text into a flat dict.

    Parameters
    ----------
    xml_text : str
        Raw XML string (may contain CDATA sections).

    Returns
    -------
    dict
        Flat dict with string values for all fields.
        Keys match WeCom callback field names:
          ToUserName, FromUserName, CreateTime, MsgType,
          Content, MsgId, AgentID, PicUrl, MediaId, etc.

    Raises
    ------
    ValueError
        If XML is malformed or missing required root element.
    """
    if not xml_text or not isinstance(xml_text, str):
        raise ValueError("XML text is empty or None")

    # Strip leading/trailing whitespace
    xml_text = xml_text.strip()
    if not xml_text:
        raise ValueError("XML text is empty after stripping")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"XML parse error: {exc}") from exc

    if root is None:
        raise ValueError("XML root element is empty")

    # Convert all child elements to a flat dict
    result = {}
    for child in root:
        tag = child.tag
        text = child.text or ""
        result[tag] = text

    return result


# ══════════════════════════════════════════════════════════════════
#  Validation helper
# ══════════════════════════════════════════════════════════════════


def is_valid_wecom_xml(data: dict) -> bool:
    """
    Check if a parsed dict has the minimum required WeCom fields.

    Required: ToUserName, FromUserName, MsgType, AgentID
    """
    required = {"ToUserName", "FromUserName", "MsgType", "AgentID"}
    return required.issubset(data.keys())
