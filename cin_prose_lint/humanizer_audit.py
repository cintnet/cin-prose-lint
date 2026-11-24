#!/usr/bin/env python3
"""Humanizer AI-Writing Pattern Auditor for cintnet.org (`site/content/**/*.html`).

Implements the rules from `blader/humanizer` (`.agents/skills/humanizer/SKILL.md`),
based on Wikipedia's "Signs of AI writing":
  - §1 Not X but Y / negative parallelisms ("not just X, but Y", "it's not X; it's Y")
  - §2 One-line dramatic closers ("That is the real win", "Let that sink in")
  - §3 Sayings that sound deep ("at its core", "the heart of the matter", "the currency of")
  - §4 Staged run-ups ("Let's dive in", "Here's what you need to know", "Here's the thing")
  - §5 Arguing with no one ("Don't get me wrong", "This is not to say", "One might be tempted to")
  - §8 Em-dashes (`—` / `&mdash;` / ` -- `) in prose paragraphs and list items
  - §12 Overused AI vocabulary (`delve`, `tapestry`, `testament`, `underscore`, `showcase`,
        `foster`, `pivotal`, `intricate`, `realm`, `vibrant`, `seamless`, `bolstered`,
        `garner`, `meticulous`, `indelible`, `interplay`, `crucial`, `deep dive`, `landscape`)
  - §13 Inflated significance (`plays a key role`, `stands as a`, `setting the stage for`)
  - §15 Shallow `-ing` participial riders (`, highlighting...`, `, underscoring...`, `, fostering...`)
  - §16 Sales / promotional language (`groundbreaking`, `breathtaking`, `diverse array`, `exemplifies`)
  - §18 Copula avoidance (`serves as a`, `stands as a`, `functions as a`, `boasts`)
  - §20 Title-case `<h2>`/`<h3>` headings (instead of sentence case)
  - Formulaic transitions (`Moreover,`, `Furthermore,`, `Additionally,`, `In conclusion,`, `It is worth noting`)
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys

CIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
_candidates = [
    CIN_ROOT.parent / "cin-site" / "cin-foundation-website" / "site" / "content",
    pathlib.Path("site/content"),
]
CONTENT_DIR = next((p for p in _candidates if p.exists()), _candidates[0])

# Patterns checked on prose (outside <section class="footnotes">, <script>, <style>, <code>, <pre>)
PROSE_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "§1 Not-X-but-Y negative parallelism",
        re.compile(
            r"\bnot (?:just|only|merely)\b[^.?!]{1,90}\bbut\b"
            r"|\b(?:it's|it is|this is|that is|they are|isn't|aren't) not (?:just |merely |simply |only )?[a-z][^.!?;]{1,50}(?:;|,|\s+it's|\s+it is|\s+they are)\b"
            r"|\b(?:is not|isn't|are not|aren't) about [^.?!]{3,50}(?:;|\.|,)\s*(?:it's|it is|they're|they are)\b"
            r"|\bthis does not mean\b[^.?!]+\.\s*it means\b",
            re.I,
        ),
        "State the positive claim directly without staged 'not X, but Y' contrast.",
    ),
    (
        "§10 Predicate hyphenation",
        re.compile(
            r"\b(?:is|are|was|were|be|remains|stay|stays)\s+(?:high-quality|well-known|well-documented|long-term|short-term|real-time|client-facing|open-source|user-friendly)\b",
            re.I,
        ),
        "Drop hyphen when compound modifier appears after the noun/verb.",
    ),
    (
        "§2 Dramatic closer / fragment",
        re.compile(
            r"\b(?:that is the real win|read that again|let that sink in|the message was clear|that distinction matters)\b",
            re.I,
        ),
        "Cut one-line dramatic closers; end on a concrete fact.",
    ),
    (
        "§3 Saying that sounds deep",
        re.compile(
            r"\b(?:at its core|the heart of the matter|the deeper issue|the real question is|is not a tool,? but a mirror|the currency of|the language of trust|the architecture of trust)\b",
            re.I,
        ),
        "Replace aphorisms and 'at its core' throat-clearing with the specific claim.",
    ),
    (
        "§4 Staged run-up",
        re.compile(
            r"\b(?:let's dive in|let's explore|let's break this down|here's what you need to know|without further ado|here's the thing|let's be honest|real talk)\b",
            re.I,
        ),
        "Remove staged run-ups and announce the point directly.",
    ),
    (
        "§5 Arguing with no one",
        re.compile(
            r"\b(?:don't get me wrong|this is not to say|a tempting approach would be|one might be tempted to|it would be easy to just)\b",
            re.I,
        ),
        "Remove defensive rhetorical strawmen.",
    ),
    (
        "§8 Em-dash in prose",
        re.compile(r"—|&mdash;|&#8212;|&#x2014;|\s--\s"),
        "Replace em-dashes in prose with commas, periods, colons, or parentheses.",
    ),
    (
        "§12 Overused AI vocabulary",
        re.compile(
            r"\b(?:delve|delves|delving|tapestry|testament|underscore|underscores|underscoring|"
            r"showcase|showcases|showcasing|foster|fosters|fostering|pivotal|intricate|intricacies|"
            r"realm|vibrant|seamless|seamlessly|bolstered|garner|garnered|meticulous|meticulously|"
            r"indelible|interplay|crucial|deep dive|evolving landscape|broader landscape|"
            r"regulatory landscape|digital landscape|ai landscape|media landscape|threat landscape)\b",
            re.I,
        ),
        "Replace stock AI vocabulary with plain, specific words.",
    ),
    (
        "§9 Stacked qualifiers",
        re.compile(
            r"\b(?:could potentially|might arguably|in some cases it may|could possibly|might potentially)\b",
            re.I,
        ),
        "Use a single clear hedge ('may' or 'can') instead of stacked qualifiers.",
    ),
    (
        "§13 Inflated significance",
        re.compile(
            r"\b(?:stands as a|serves as a testament|plays a key role|plays a crucial role|"
            r"plays a vital role|marks a pivotal|setting the stage for|a step in the right direction|"
            r"exciting times ahead|the future looks bright|indelible mark|reflects a broader|"
            r"underscores its importance)\b",
            re.I,
        ),
        "Remove inflated significance and state the concrete fact.",
    ),
    (
        "§14 Vague connection",
        re.compile(
            r"\b(?:in association with|in connection with)\b",
            re.I,
        ),
        "Name the specific relationship instead of 'in association/connection with'.",
    ),
    (
        "§17 Borrowed unnamed authority",
        re.compile(
            r"\b(?:experts argue|experts believe|observers have cited|industry reports suggest|some critics argue)\b",
            re.I,
        ),
        "Name the specific source and what it found instead of unnamed 'experts argue'.",
    ),
    (
        "§22/§25 Self-referential / chatbot residue",
        re.compile(
            r"\b(?:i hope this helps|great question|you're absolutely right|in this article,? we|in this post,? we|in this essay,? we|the table below compares)\b",
            re.I,
        ),
        "Remove chatbot wrappers and self-referential document narration.",
    ),
    (
        "§15 Shallow -ing rider",
        re.compile(
            r",\s*(?:highlighting|underscoring|emphasizing|ensuring that|reflecting a|symbolizing|"
            r"cultivating|fostering|encompassing|showcasing)\b",
            re.I,
        ),
        "Remove shallow '-ing' participial tails bolted onto the end of clauses.",
    ),
    (
        "§16 Sales / promotional language",
        re.compile(
            r"\b(?:breathtaking|groundbreaking|must-visit|stunning|nestled|in the heart of|"
            r"diverse array|exemplifies)\b",
            re.I,
        ),
        "Remove promotional puffery.",
    ),
    (
        "§18 Copula avoidance",
        re.compile(
            r"\b(?:serves as a|stands as a|functions as a|operates as a|boasts a|boasts over)\b",
            re.I,
        ),
        "Use 'is', 'are', or 'has' instead of 'serves as a' / 'stands as a' / 'boasts'.",
    ),
    (
        "§12/Filler Formulaic transition",
        re.compile(
            r"(?:^|[.?!]\s+)(?:Moreover|Furthermore|Additionally|In conclusion|It is important to note|"
            r"It is worth noting|In order to|Due to the fact that)\b",
        ),
        "Use natural transitions or state the next point directly.",
    ),
]

PROPER_OR_ALLOWED_CAPS = {
    "AI", "CIN", "IETF", "W3C", "NIST", "IEEE", "EU", "UK", "US", "USA", "UN",
    "QUIC", "COSE", "CBOR", "OAuth", "WIMSE", "DNS", "ICANN", "HTML", "CSS",
    "SVG", "JSON", "API", "LLM", "LLMs", "ASI", "AGI", "RLVR", "LoRA", "TIES",
    "BGP", "TLS", "HTTPS", "HTTP", "TCP", "UDP", "IP", "ID", "IDs", "PDF",
    "C2PA", "MCP", "A2A", "BCI", "EEG", "MEG", "ZK", "PSI", "MPC", "TEE",
    "VRAM", "GPU", "GPUs", "CPU", "CPUs", "RAM", "SQL", "SQLite", "RFC",
    "Shared", "Horizon", "Collective", "Intelligence", "Network", "Ottawa",
    "Canada", "Canadian", "Internet", "Web", "Data", "Shapley", "Ostrom",
    "Goodhart", "Baruch", "METR", "FAccT", "NeurIPS", "ICML", "ICLR",
    "ACM", "CCS", "CHI", "CSCW", "arXiv", "GitHub", "Wikipedia", "Commons",
    "Ascent", "Section", "Track", "Stage", "Phase", "Step", "Part", "Rule",
}
MINOR_WORDS = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet", "at",
    "by", "in", "of", "on", "to", "up", "as", "is", "it", "vs", "via", "with",
    "from", "into", "onto", "upon", "over", "under", "between", "without",
}


def strip_non_prose(raw_html: str) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, prose_html_without_footnotes_scripts_styles_code)."""
    meta: dict[str, str] = {}
    body = raw_html
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_html, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.split("  #")[0].strip()
        body = m.group(2)

    # Remove footnotes, scripts, styles, svg, code, pre
    cleaned = re.sub(r'<section class="footnotes">.*?</section>', " ", body, flags=re.S | re.I)
    cleaned = re.sub(r"<(script|style|svg|code|pre)\b[^>]*>.*?</\1>", " ", cleaned, flags=re.S | re.I)
    return meta, cleaned


def check_headings_sentence_case(rel_name: str, body_html: str) -> list[str]:
    issues: list[str] = []
    for m in re.finditer(r"<(h[23])\b[^>]*>(.*?)</\1>", body_html, flags=re.S | re.I):
        tag = m.group(1).lower()
        text = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
        if len(words) < 4:
            continue
        non_first = words[1:]
        content_words = [w for w in non_first if w.lower() not in MINOR_WORDS and w not in PROPER_OR_ALLOWED_CAPS]
        if len(content_words) >= 3:
            cap_count = sum(1 for w in content_words if w[0].isupper())
            if cap_count / len(content_words) >= 0.75:
                issues.append(f"{rel_name}: §20 Title-case <{tag}> heading '{text}' (use sentence case)")
    return issues


def audit_file(path: pathlib.Path, base_dir: pathlib.Path = CONTENT_DIR) -> list[str]:
    rel_name = path.relative_to(base_dir).as_posix()
    raw = path.read_text(encoding="utf-8")
    meta, cleaned = strip_non_prose(raw)
    issues: list[str] = []

    # Check frontmatter title/description/lede for em-dashes and AI words
    for fm_key in ("title", "description", "lede"):
        val = html.unescape(re.sub(r"<[^>]+>", " ", meta.get(fm_key, ""))).strip()
        if not val:
            continue
        for rule_name, rx, hint in PROSE_PATTERNS:
            for match in rx.finditer(val):
                snippet = match.group(0).strip()
                issues.append(f"{rel_name} [{fm_key}]: {rule_name} -> '{snippet}' ({hint})")

    # Check headings for Title Case
    issues.extend(check_headings_sentence_case(rel_name, cleaned))

    # Extract prose blocks (<p>, <li>, <blockquote>, <figcaption>, <summary>)
    for blk_m in re.finditer(r"<(p|li|blockquote|figcaption|summary)\b[^>]*>(.*?)</\1>", cleaned, flags=re.S | re.I):
        blk_text = html.unescape(re.sub(r"<[^>]+>", " ", blk_m.group(2)))
        blk_text = re.sub(r"\s+", " ", blk_text).strip()
        if not blk_text:
            continue
        for rule_name, rx, hint in PROSE_PATTERNS:
            for match in rx.finditer(blk_text):
                snippet = match.group(0).strip()
                start = max(0, match.start() - 25)
                end = min(len(blk_text), match.end() + 25)
                ctx = blk_text[start:end].strip()
                issues.append(f"{rel_name}: {rule_name} -> '{snippet}' in \"...{ctx}...\"")

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit cintnet.org HTML content for blader/humanizer AI writing tells.")
    ap.add_argument("paths", nargs="*", help="Specific files or directories to audit (defaults to site/content)")
    ap.add_argument("--blog-only", action="store_true", help="Only audit site/content/blog/*.html")
    args = ap.parse_args()

    targets: list[pathlib.Path] = []
    if args.paths:
        for p_str in args.paths:
            p = pathlib.Path(p_str)
            if p.is_dir():
                targets.extend(sorted(p.rglob("*.html")))
            elif p.is_file():
                targets.append(p)
    elif args.blog_only:
        targets = sorted((CONTENT_DIR / "blog").glob("*.html"))
    else:
        targets = sorted(CONTENT_DIR.rglob("*.html"))

    all_issues: list[str] = []
    files_with_issues = 0
    for f in targets:
        file_issues = audit_file(f, CONTENT_DIR if f.is_relative_to(CONTENT_DIR) else f.parent)
        if file_issues:
            files_with_issues += 1
            all_issues.extend(file_issues)

    for iss in all_issues:
        print("TELL ", iss)
    print(f"Audited {len(targets)} file(s): {len(all_issues)} humanizer tell(s) across {files_with_issues} file(s).")
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
