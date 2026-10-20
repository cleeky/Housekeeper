#!/usr/bin/python
"""
*********************************************************
    Application : HK_opt.py
    Written By:   Colin Leek
    Purpose:      File Management script to perform automatic actions defined by rules
    Version:      1.00 (Optimised)

    Description:
        Reads a pipe-delimited rules file and performs file operations:
        C = Copy, A = Archive (individual zips), G = Group Archive, M = Move, D = Delete
**********************************************************
"""
import argparse
import datetime as dt
import glob
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

# Authorship information
__author__ = "Colin Leek"
__copyright__ = "GFT"
__license__ = "GPL"
__version__ = "1.00"
__status__ = "Development"

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(rules_file: str) -> logging.Logger:
    """Configure and return a logger that writes to a date-stamped log file
    alongside the rules file.

    Args:
        rules_file: Path to the rules/config file.

    Returns:
        Configured Logger instance.
    """
    log_stem = Path(rules_file).stem
    log_name = log_stem + dt.date.today().strftime("%Y%m%d") + ".log"
    log_path = Path(rules_file).parent / log_name

    logger = logging.getLogger("housekeeper")
    logger.setLevel(logging.DEBUG)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] - %(module)-8s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also echo to console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    return logger


# ---------------------------------------------------------------------------
# Rule dataclass
# ---------------------------------------------------------------------------

SECONDS_PER_DAY = 24 * 60 * 60   # corrected: original had 24*60*60*60


class RuleValue:
    """Stores a single housekeeping rule parsed from the config file."""

    # Expected number of pipe-separated fields (including trailing empty field)
    FIELD_COUNT = 7

    def __init__(
        self,
        operation: str,
        sourcepath: str,
        sourcefile: str,
        fileage: str,
        targetpath: str,
        targetfile: str,
    ):
        self.operation = operation.strip().upper()
        self.sourcepath = sourcepath.strip()
        self.sourcefile = sourcefile.strip()
        self.fileage = SECONDS_PER_DAY * int(fileage)   # age threshold in seconds
        self.targetpath = targetpath.strip()
        self.targetfile = targetfile.strip()

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_string(cls, rule_line: str) -> "RuleValue":
        """Parse a pipe-delimited rule line into a RuleValue instance.

        Args:
            rule_line: One line from the rules config file.

        Returns:
            Populated RuleValue.

        Raises:
            ValueError: If the line does not have the expected number of fields.
        """
        rule_line = rule_line.rstrip("\n")
        parts = rule_line.split("|")
        if len(parts) != cls.FIELD_COUNT:
            raise ValueError(
                f"Rule line has {len(parts)} fields, expected {cls.FIELD_COUNT}: {rule_line!r}"
            )
        operation, sourcepath, sourcefile, fileage, targetpath, targetfile, *_ = parts
        return cls(operation, sourcepath, sourcefile, fileage, targetpath, targetfile)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DATE_TAG_RE = re.compile(r"\{date\?([dwm])\?(\d+)\}", re.IGNORECASE)


def resolve_target_filename(file_name: str) -> str:
    """Replace any ``{date?[d/w/m]?value}`` tag in *file_name* with a
    formatted date string (YYYYMMDD).

    Args:
        file_name: Raw target file name, possibly containing a date tag.

    Returns:
        File name with the tag substituted for a real date.
    """
    if not file_name:
        return file_name

    match = DATE_TAG_RE.search(file_name)
    if match is None:
        return file_name

    unit, value_str = match.group(1).lower(), int(match.group(2))
    today = dt.date.today()

    if unit == "d":
        target_date = today - dt.timedelta(days=value_str)
    elif unit == "w":
        target_date = today - dt.timedelta(weeks=value_str)
    else:  # "m"
        # Subtract months manually (timedelta doesn't support months)
        month = today.month - value_str
        year = today.year + month // 12
        month = month % 12 or 12
        target_date = today.replace(year=year, month=month)

    date_str = target_date.strftime("%Y%m%d")
    return DATE_TAG_RE.sub(date_str, file_name)


def resolve_target(action_line: RuleValue, file: str) -> str:
    """Determine the full target path for a file operation.

    Rules (same logic as original, extracted to avoid repetition):
      1. No target file name and no wildcard in source → use source basename.
      2. No wildcard in source but a target file name given → use target file name.
      3. Wildcard present → use only target directory.

    Args:
        action_line: Parsed rule.
        file: Matched source file path.

    Returns:
        Full target path string.
    """
    no_wildcard = "*" not in action_line.sourcefile
    if not action_line.targetfile and no_wildcard:
        return os.path.join(action_line.targetpath, os.path.basename(file))
    if no_wildcard:
        return os.path.join(action_line.targetpath, action_line.targetfile)
    return action_line.targetpath


def is_old_enough(file: str, age_threshold_seconds: int) -> bool:
    """Return True if the file's last-modification time exceeds the threshold.

    Args:
        file: Path to the file.
        age_threshold_seconds: Minimum age in seconds.

    Returns:
        True if the file is older than the threshold.
    """
    if age_threshold_seconds == 0:
        return True
    file_mtime = os.stat(file).st_mtime
    age = dt.datetime.now().timestamp() - file_mtime
    return age > age_threshold_seconds


def glob_files(action_line: RuleValue):
    """Yield file paths matching the rule's source pattern that are old enough.

    Args:
        action_line: Parsed rule.

    Yields:
        Matching file paths.
    """
    pattern = os.path.join(action_line.sourcepath, action_line.sourcefile)
    for file in glob.glob(pattern):
        if os.path.isfile(file) and is_old_enough(file, action_line.fileage):
            yield file


def _parse_and_resolve(aline: str) -> RuleValue:
    """Parse a rule line and resolve any date tag in the target file name.

    Args:
        aline: Raw rule line.

    Returns:
        Ready-to-use RuleValue.
    """
    action_line = RuleValue.from_string(aline)
    action_line.targetfile = resolve_target_filename(action_line.targetfile)
    return action_line


def _check_paths(action_line: RuleValue, operation: str) -> bool:
    """Validate source (and optionally target) paths, logging errors on failure.

    Args:
        action_line: Parsed rule.
        operation: Label used in log messages (e.g. "COPY").

    Returns:
        True if all required paths exist, False otherwise.
    """
    if not os.path.exists(action_line.sourcepath):
        log.error("[%s] Source path does not exist: %s", operation, action_line.sourcepath)
        return False
    if action_line.targetpath and not os.path.exists(action_line.targetpath):
        log.error("[%s] Target path does not exist: %s", operation, action_line.targetpath)
        return False
    return True


# ---------------------------------------------------------------------------
# Operation functions
# ---------------------------------------------------------------------------

def copy_function(aline: str) -> None:
    """Copy files matching the rule to the target directory.

    Args:
        aline: Raw rule line beginning with 'C'.
    """
    action_line = _parse_and_resolve(aline)
    if not _check_paths(action_line, "COPY"):
        return

    for file in glob_files(action_line):
        target = resolve_target(action_line, file)
        try:
            shutil.copy2(file, target)
            log.info("[COPY] %s → %s", file, target)
        except OSError as exc:
            log.error("[COPY] Failed to copy %s → %s: %s", file, target, exc)


def archive_function(aline: str) -> None:
    """Compress each matching file into its own zip archive in the target directory.

    Args:
        aline: Raw rule line beginning with 'A'.
    """
    action_line = _parse_and_resolve(aline)
    if not _check_paths(action_line, "ARCHIVE"):
        return

    for file in glob_files(action_line):
        zip_name = Path(file).with_suffix(".zip").name
        zip_path = os.path.join(action_line.targetpath, zip_name)
        try:
            with ZipFile(zip_path, "w", ZIP_DEFLATED) as zipf:
                zipf.write(file, arcname=os.path.basename(file))
            log.info("[ARCHIVE] %s → %s", file, zip_path)
        except OSError as exc:
            log.error("[ARCHIVE] Failed to archive %s: %s", file, exc)
            continue
        try:
            os.remove(file)
            log.info("[ARCHIVE] Removed source file %s", file)
        except OSError as exc:
            log.warning("[ARCHIVE] Could not remove source file %s: %s", file, exc)


def group_archive_function(aline: str) -> None:
    """Compress all matching files into a single zip archive.

    Args:
        aline: Raw rule line beginning with 'G'.
    """
    action_line = _parse_and_resolve(aline)
    if not _check_paths(action_line, "GARCHIVE"):
        return

    zip_name = re.sub(r"\.[^.]+$", ".zip", action_line.targetfile)
    zip_path = os.path.join(action_line.targetpath, zip_name)

    for file in glob_files(action_line):
        # 'a' mode creates the file if it doesn't exist, appends otherwise
        try:
            with ZipFile(zip_path, "a", ZIP_DEFLATED) as zipf:
                zipf.write(file, arcname=os.path.basename(file))
            log.info("[GARCHIVE] %s → %s", file, zip_path)
        except OSError as exc:
            log.error("[GARCHIVE] Failed to archive %s: %s", file, exc)
            continue
        try:
            os.remove(file)
            log.info("[GARCHIVE] Removed source file %s", file)
        except OSError as exc:
            log.warning("[GARCHIVE] Could not remove source file %s: %s", file, exc)


def delete_function(aline: str) -> None:
    """Delete files matching the rule.

    Args:
        aline: Raw rule line beginning with 'D'.
    """
    action_line = _parse_and_resolve(aline)
    if not _check_paths(action_line, "DELETE"):
        return

    for file in glob_files(action_line):
        try:
            os.remove(file)
            log.info("[DELETE] Deleted %s", file)
        except OSError as exc:
            log.error("[DELETE] Failed to delete %s: %s", file, exc)


def move_function(aline: str) -> None:
    """Move files matching the rule to the target directory.

    Args:
        aline: Raw rule line beginning with 'M'.
    """
    action_line = _parse_and_resolve(aline)
    if not _check_paths(action_line, "MOVE"):
        return

    for file in glob_files(action_line):
        target = resolve_target(action_line, file)
        try:
            shutil.move(file, target)
            log.info("[MOVE] %s → %s", file, target)
        except OSError as exc:
            log.error("[MOVE] Failed to move %s → %s: %s", file, target, exc)


# ---------------------------------------------------------------------------
# Dispatch table – maps operation codes to handler functions
# ---------------------------------------------------------------------------

OPERATIONS = {
    "C": copy_function,
    "A": archive_function,
    "G": group_archive_function,
    "D": delete_function,
    "M": move_function,
}

COMMENT_OR_BLANK_RE = re.compile(r"^\s*(#|$)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Namespace with ``rules_file`` attribute.
    """
    parser = argparse.ArgumentParser(
        prog="HK_opt.py",
        description="Housekeeper – automated file management via a rules file.",
    )
    parser.add_argument(
        "-i", "--ifile",
        dest="rules_file",
        required=True,
        metavar="RULESFILE",
        help="Path to the pipe-delimited rules file (e.g. housekeeper.txt)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = success, 1 = fatal error).
    """
    args = parse_args()
    rules_file = args.rules_file

    global log
    log = setup_logging(rules_file)
    log.info("Starting housekeeping. Rules file: %s", rules_file)

    try:
        with open(rules_file, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        log.error("Failed to open rules file %s: %s", rules_file, exc)
        return 1

    for line in lines:
        # Skip comments and blank lines
        if COMMENT_OR_BLANK_RE.match(line):
            continue

        action = line.split("|")[0].strip().upper()
        handler = OPERATIONS.get(action)
        if handler is None:
            log.warning("Unknown operation code, skipping line: %r", line.rstrip())
            continue

        try:
            handler(line)
        except ValueError as exc:
            log.error("Malformed rule line: %s", exc)

    log.info("Housekeeping complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())