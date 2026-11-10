# feature: F00
"""Readers for the public installer-operation and metadata forms."""
import re

from packaging.utils import canonicalize_name
from packaging.version import Version


def operation_lines(text):
    """Read labeled operation records and compare releases by PEP 440 identity."""
    records = []
    for line in text.splitlines():
        match = re.fullmatch(r"\s*- (Installing|Removing|Updating|Downgrading) (\S+) \(([^)]+)\)(?:: (Skipped)(?: .*)?)?", line)
        if match:
            versions = tuple(Version(value.strip()) for value in match[3].split(" -> "))
            expected_count = 2 if match[1] in ("Updating", "Downgrading") else 1
            assert len(versions) == expected_count, line
            records.append((match[1], canonicalize_name(match[2]), versions, match[4] is not None))
    return records


def project_links(metadata):
    """Read comma-delimited label and URL fields without grading spacing."""
    links = {}
    for value in metadata.get_all("Project-URL", []):
        label, separator, url = value.partition(",")
        assert separator and label.strip() not in links, value
        links[label.strip()] = url.strip()
    return links


def local_file_path(url):
    """Read a local file URI without pinning its equivalent authority spelling."""
    from urllib.parse import unquote, urlsplit
    from pathlib import Path
    location = urlsplit(url)
    assert location.scheme == "file" and location.netloc in ("", "localhost"), url
    assert not location.query and not location.fragment, url
    return Path(unquote(location.path)).resolve()
